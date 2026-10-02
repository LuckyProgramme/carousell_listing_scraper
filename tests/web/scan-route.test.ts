import { beforeEach, describe, expect, it, vi } from "vitest";
import { configureEnv, env, jsonResponse, ownerId, row, scanId, scanRequest } from "./fixtures";

const auth = vi.hoisted(() => ({ getUser: vi.fn(), getSession: vi.fn() }));
vi.mock("@/lib/supabase/server", () => ({ createClient: vi.fn(async () => ({ auth })) }));
import { POST } from "@/app/api/scan/route";

const post = POST as (request: Request) => Promise<Response>;

beforeEach(() => {
  configureEnv();
  auth.getUser.mockResolvedValue({ data: { user: { id: ownerId, email: env.ALLOWED_USER_EMAIL } }, error: null });
  auth.getSession.mockResolvedValue({ data: { session: { access_token: "cookie_token_test_only" } } });
});

describe("Scan Now route contract", () => {
  it("uses validated identity, creates one queue, then dispatches only its ID", async () => {
    const transport = vi.fn().mockResolvedValueOnce(jsonResponse([row()], 201))
      .mockResolvedValueOnce(jsonResponse({ workflow_run_id: 123 }));
    vi.stubGlobal("fetch", transport);
    const response = await post(scanRequest());
    expect(response.status).toBe(202);
    expect(await response.json()).toEqual({ data: { scan: { id: scanId, status: "queued" } } });
    expect(auth.getUser).toHaveBeenCalledOnce();
    expect(auth.getSession).not.toHaveBeenCalled();
    expect(transport).toHaveBeenCalledTimes(2);
    expect(JSON.parse(transport.mock.calls[0][1].body)).toEqual({ owner_id: ownerId, status: "queued" });
    expect(String(transport.mock.calls[1][0])).toContain("https://api.github.com/repos/LuckyProgramme/carousell_listing_scraper/");
    expect(JSON.parse(transport.mock.calls[1][1].body)).toEqual({ ref: "main", inputs: { scan_run_id: scanId } });
  });

  it("does not accept a cookie session without a validated user", async () => {
    auth.getUser.mockResolvedValue({ data: { user: null }, error: { status: 401 } });
    expect((await post(scanRequest())).status).toBe(401);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("rejects a different validated account before privileged access", async () => {
    auth.getUser.mockResolvedValue({ data: { user: { id: ownerId, email: "other@example.com" } }, error: null });
    expect((await post(scanRequest())).status).toBe(403);
    expect(fetch).not.toHaveBeenCalled();
  });

  it.each([null, "https://evil.example"])("rejects absent/cross-origin requests: %s", async (origin) => {
    expect((await post(scanRequest("/api/scan", origin))).status).toBe(403);
    expect(auth.getUser).not.toHaveBeenCalled();
    expect(fetch).not.toHaveBeenCalled();
  });

  it.each(["preview", "development"])("disables Vercel %s dispatch", async (deployment) => {
    vi.stubEnv("VERCEL_ENV", deployment);
    expect((await post(scanRequest())).status).toBe(403);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("requires complete launch configuration before queue insertion", async () => {
    vi.stubEnv("GITHUB_ACTIONS_TOKEN", "");
    expect((await post(scanRequest())).status).toBe(503);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("returns 409 for the active-scan constraint and never dispatches", async () => {
    const transport = vi.fn().mockResolvedValue(jsonResponse({ code: "23505", message: 'duplicate key violates unique constraint "scan_runs_one_active_per_owner_idx"' }, 409));
    vi.stubGlobal("fetch", transport);
    expect((await post(scanRequest())).status).toBe(409);
    expect(transport).toHaveBeenCalledOnce();
  });

  it("conditionally fails only its queued scan after definitive rejection", async () => {
    const transport = vi.fn().mockResolvedValueOnce(jsonResponse([row()], 201))
      .mockResolvedValueOnce(jsonResponse({ message: "provider internals" }, 403))
      .mockResolvedValueOnce(jsonResponse([row("failed")]));
    vi.stubGlobal("fetch", transport);
    const response = await post(scanRequest());
    expect(response.status).toBe(503);
    expect(await response.text()).not.toContain("provider internals");
    const url = new URL(String(transport.mock.calls[2][0]));
    expect(url.searchParams.get("owner_id")).toBe(`eq.${ownerId}`);
    expect(url.searchParams.get("id")).toBe(`eq.${scanId}`);
    expect(url.searchParams.get("status")).toBe("eq.queued");
  });

  it("keeps uncertain dispatch queued without retry or status overwrite", async () => {
    const transport = vi.fn().mockResolvedValueOnce(jsonResponse([row()], 201))
      .mockRejectedValueOnce(new Error("lost response contains token"));
    vi.stubGlobal("fetch", transport);
    const response = await post(scanRequest());
    expect(response.status).toBe(202);
    const body = await response.json();
    expect(body.data.scan.status).toBe("queued");
    expect(body.data.notice).toContain("could not be confirmed");
    expect(JSON.stringify(body)).not.toContain("contains token");
    expect(transport).toHaveBeenCalledTimes(2);
  });

  it("does not fail a runner that claimed the scan during dispatch checking", async () => {
    const transport = vi.fn().mockResolvedValueOnce(jsonResponse([row()], 201))
      .mockResolvedValueOnce(jsonResponse({}, 422)).mockResolvedValueOnce(jsonResponse([]));
    vi.stubGlobal("fetch", transport);
    const response = await post(scanRequest());
    expect(response.status).toBe(202);
    expect((await response.json()).data.notice).toBeTruthy();
    expect(transport).toHaveBeenCalledTimes(3);
  });

  it("ignores browser-supplied owner and launch settings", async () => {
    const transport = vi.fn().mockResolvedValueOnce(jsonResponse([row()], 201))
      .mockResolvedValueOnce(jsonResponse({ workflow_run_id: 123 }));
    vi.stubGlobal("fetch", transport);
    const request = new Request(`${env.FRONTEND_ORIGIN}/api/scan`, {
      method: "POST", headers: { Origin: env.FRONTEND_ORIGIN, "Content-Type": "application/json" },
      body: JSON.stringify({ owner_id: "attacker", repository: "evil/repo", ref: "evil", scan_run_id: "attacker" }),
    });
    expect((await post(request)).status).toBe(202);
    expect(JSON.parse(transport.mock.calls[0][1].body).owner_id).toBe(ownerId);
    expect(String(transport.mock.calls[1][0])).not.toContain("evil");
    expect(JSON.parse(transport.mock.calls[1][1].body)).toEqual({ ref: "main", inputs: { scan_run_id: scanId } });
  });

  it("rejects cross-site fetch metadata even with a matching Origin", async () => {
    const request = scanRequest();
    request.headers.set("Sec-Fetch-Site", "cross-site");
    expect((await post(request)).status).toBe(403);
    expect(auth.getUser).not.toHaveBeenCalled();
    expect(fetch).not.toHaveBeenCalled();
  });

  it.each(["network", "server"])("does not expose auth %s errors or create a scan", async (kind) => {
    if (kind === "network") auth.getUser.mockRejectedValue(new Error("private auth credentials"));
    else auth.getUser.mockResolvedValue({ data: { user: null }, error: { status: 503, message: "private auth credentials" } });
    const response = await post(scanRequest());
    expect(response.status).toBe(503);
    expect(await response.text()).not.toContain("private auth credentials");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("rejects invalid validated user IDs and ignores user metadata for access", async () => {
    auth.getUser.mockResolvedValue({ data: { user: { id: "bad-id", email: env.ALLOWED_USER_EMAIL } }, error: null });
    expect((await post(scanRequest())).status).toBe(401);
    auth.getUser.mockResolvedValue({ data: { user: { id: ownerId, email: "other@example.com", user_metadata: { email: env.ALLOWED_USER_EMAIL } } }, error: null });
    expect((await post(scanRequest())).status).toBe(403);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("does not dispatch or retry when insertion response is lost", async () => {
    const transport = vi.fn().mockRejectedValue(new Error("secret insertion detail"));
    vi.stubGlobal("fetch", transport);
    const response = await post(scanRequest());
    expect(response.status).toBe(503);
    expect(await response.text()).toContain("refresh scan status");
    expect(transport).toHaveBeenCalledOnce();
  });

  it("preserves the queue if recording definitive rejection is unavailable", async () => {
    const transport = vi.fn().mockResolvedValueOnce(jsonResponse([row()], 201))
      .mockResolvedValueOnce(jsonResponse({}, 401)).mockRejectedValueOnce(new Error("private storage detail"));
    vi.stubGlobal("fetch", transport);
    const response = await post(scanRequest());
    expect(response.status).toBe(202);
    const text = await response.text();
    expect(text).toContain("could not be confirmed");
    expect(text).not.toContain("private storage detail");
    expect(transport).toHaveBeenCalledTimes(3);
  });
});
