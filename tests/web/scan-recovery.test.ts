import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { configureEnv, env, jsonResponse, ownerId, row, scanId, scanRequest } from "./fixtures";

const auth = vi.hoisted(() => ({ getUser: vi.fn(), getSession: vi.fn() }));
vi.mock("@/lib/supabase/server", () => ({ createClient: vi.fn(async () => ({ auth })) }));
import { POST } from "@/app/api/scan/recover/route";
import { recoverQueuedScan } from "@/lib/scans/recovery";
const post = POST as (request: Request) => Promise<Response>;
beforeEach(() => {
  configureEnv();
  auth.getUser.mockResolvedValue({ data: { user: { id: ownerId, email: env.ALLOWED_USER_EMAIL } }, error: null });
  auth.getSession.mockResolvedValue({ data: { session: { access_token: "cookie_token_test_only" } } });
});
afterEach(() => vi.useRealTimers());

describe("recovery route contracts", () => {
  it("requires validated identity, not just a cookie session", async () => {
    auth.getUser.mockResolvedValue({ data: { user: null }, error: { status: 401 } });
    expect((await post(scanRequest("/api/scan/recover"))).status).toBe(401);
    expect(fetch).not.toHaveBeenCalled();
  });
  it("rejects a foreign Origin before privileged access", async () => {
    expect((await post(scanRequest("/api/scan/recover", "https://evil.example"))).status).toBe(403);
    expect(auth.getUser).not.toHaveBeenCalled();
    expect(fetch).not.toHaveBeenCalled();
  });
  it("rejects preview deployments", async () => {
    vi.stubEnv("VERCEL_ENV", "preview");
    expect((await post(scanRequest("/api/scan/recover"))).status).toBe(403);
    expect(fetch).not.toHaveBeenCalled();
  });
  it("recovers stale queued owner work without needing a GitHub token", async () => {
    vi.stubEnv("GITHUB_ACTIONS_TOKEN", "");
    const transport = vi.fn().mockResolvedValue(jsonResponse([row("failed")]));
    vi.stubGlobal("fetch", transport);
    const response = await post(scanRequest("/api/scan/recover"));
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ data: { recovered: true, scan: { id: scanId, status: "failed" } } });
    expect(transport).toHaveBeenCalledOnce();
    const url = new URL(String(transport.mock.calls[0][0]));
    expect(url.searchParams.get("owner_id")).toBe(`eq.${ownerId}`);
    expect(url.searchParams.get("status")).toBe("eq.queued");
    expect(url.searchParams.get("created_at")).toMatch(/^lt\./);
  });
  it("does not release recent or already running work", async () => {
    const transport = vi.fn().mockResolvedValue(jsonResponse([]));
    vi.stubGlobal("fetch", transport);
    const response = await post(scanRequest("/api/scan/recover"));
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ data: { recovered: false, scan: null } });
    expect(transport).toHaveBeenCalledOnce();
  });
  it("rejects missing Origin before identity or storage", async () => {
    expect((await post(scanRequest("/api/scan/recover", null))).status).toBe(403);
    expect(auth.getUser).not.toHaveBeenCalled();
    expect(fetch).not.toHaveBeenCalled();
  });
  it("rejects cross-site requests even with the configured Origin", async () => {
    const request = scanRequest("/api/scan/recover");
    request.headers.set("Sec-Fetch-Site", "cross-site");
    expect((await post(request)).status).toBe(403);
    expect(auth.getUser).not.toHaveBeenCalled();
    expect(fetch).not.toHaveBeenCalled();
  });
  it("rejects another signed-in email before privileged access", async () => {
    auth.getUser.mockResolvedValue({ data: { user: { id: ownerId, email: "other@example.com" } }, error: null });
    expect((await post(scanRequest("/api/scan/recover"))).status).toBe(403);
    expect(fetch).not.toHaveBeenCalled();
  });
  it("handles auth transport failure safely without storage access", async () => {
    auth.getUser.mockRejectedValue(new Error("private auth credentials"));
    const response = await post(scanRequest("/api/scan/recover"));
    expect(response.status).toBe(503);
    expect(await response.text()).not.toContain("private");
    expect(fetch).not.toHaveBeenCalled();
  });
  it.each(["preview", "development"])("rejects %s even when secrets are absent", async (mode) => {
    configureEnv({ VERCEL_ENV: mode, FRONTEND_ORIGIN: "", SUPABASE_SECRET_KEY: "" });
    expect((await post(scanRequest("/api/scan/recover"))).status).toBe(403);
    expect(auth.getUser).not.toHaveBeenCalled();
    expect(fetch).not.toHaveBeenCalled();
  });
  it.each(["SUPABASE_SECRET_KEY", "NEXT_PUBLIC_SUPABASE_URL", "ALLOWED_USER_EMAIL", "FRONTEND_ORIGIN"])("fails closed for missing %s", async (key) => {
    vi.stubEnv(key, "");
    expect((await post(scanRequest("/api/scan/recover"))).status).toBe(503);
    expect(fetch).not.toHaveBeenCalled();
  });
  it.each(["4", "1441", "5.5", "abc"])("rejects invalid threshold %s before mutation", async (minutes) => {
    vi.stubEnv("STALE_QUEUED_SCAN_MINUTES", minutes);
    expect((await post(scanRequest("/api/scan/recover"))).status).toBe(503);
    expect(fetch).not.toHaveBeenCalled();
  });
  it.each([["", 15], ["5", 5], ["1440", 1440]])("uses UTC cutoff for threshold '%s'", async (configured, minutes) => {
    vi.useFakeTimers();
    const now = new Date("2026-10-02T04:00:00.000Z");
    vi.setSystemTime(now);
    configureEnv({ STALE_QUEUED_SCAN_MINUTES: String(configured), GITHUB_ACTIONS_TOKEN: "", GITHUB_REPOSITORY: "", GITHUB_WORKFLOW_FILE: "", GITHUB_WORKFLOW_REF: "" });
    const transport = vi.fn().mockResolvedValue(jsonResponse([row("failed")]));
    vi.stubGlobal("fetch", transport);
    const response = await post(scanRequest("/api/scan/recover"));
    expect(response.status).toBe(200);
    expect(response.headers.get("cache-control")).toBe("no-store");
    const url = new URL(String(transport.mock.calls[0][0]));
    expect(url.searchParams.get("created_at")).toBe(`lt.${new Date(now.getTime() - Number(minutes) * 60_000).toISOString()}`);
    expect(url.searchParams.get("owner_id")).toBe(`eq.${ownerId}`);
    expect(url.searchParams.get("status")).toBe("eq.queued");
    const init = transport.mock.calls[0][1];
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body)).toMatchObject({ status: "failed", completed_at: now.toISOString() });
    expect(transport).toHaveBeenCalledOnce();
    expect(auth.getSession).not.toHaveBeenCalled();
  });
  it("ignores browser-supplied owner, cutoff and dispatch settings", async () => {
    const recover = vi.fn().mockResolvedValue(null);
    const now = new Date("2026-10-02T04:00:00Z");
    const request = new Request(`${env.FRONTEND_ORIGIN}/api/scan/recover`, {
      method: "POST", headers: { Origin: env.FRONTEND_ORIGIN },
      body: JSON.stringify({ owner_id: "another", cutoff: "2100-01-01", staleQueuedMinutes: 0, token: "another" }),
    });
    const response = await recoverQueuedScan(request, { now: () => now, repository: () => ({
      createQueuedScan: vi.fn(), failQueuedScan: vi.fn(), recoverStaleQueuedScan: recover,
    }) });
    expect(response.status).toBe(200);
    expect(recover).toHaveBeenCalledExactlyOnceWith(ownerId, new Date("2026-10-02T03:45:00Z"));
    expect(fetch).not.toHaveBeenCalled();
  });
  it("redacts database failure and never retries the mutation", async () => {
    const transport = vi.fn().mockResolvedValue(jsonResponse({ message: "private provider detail" }, 503));
    vi.stubGlobal("fetch", transport);
    const response = await post(scanRequest("/api/scan/recover"));
    expect(response.status).toBe(503);
    expect(await response.text()).not.toContain("private");
    expect(transport).toHaveBeenCalledOnce();
  });
});
