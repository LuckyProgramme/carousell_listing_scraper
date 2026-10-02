import { describe, expect, it, vi } from "vitest";
import { dispatchScan } from "@/lib/scans/github";
import { readStartConfig } from "@/lib/scans/config";
import { env, jsonResponse, scanId } from "./fixtures";

const config = readStartConfig(env).github;
describe("fixed GitHub dispatch boundary", () => {
  it("sends one authenticated bounded request with only trusted inputs", async () => {
    const transport = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse({ workflow_run_id: 456 }));
    expect(await dispatchScan(config, scanId, transport)).toBe("accepted");
    expect(transport).toHaveBeenCalledOnce();
    const [url, init] = transport.mock.lastCall!;
    expect(url).toBe("https://api.github.com/repos/LuckyProgramme/carousell_listing_scraper/actions/workflows/scan.yml/dispatches");
    expect(init).toMatchObject({ method: "POST", cache: "no-store", redirect: "error" });
    expect(new Headers(init?.headers).get("authorization")).toBe(`Bearer ${config.token}`);
    expect(new Headers(init?.headers).get("x-github-api-version")).toBe("2026-03-10");
    expect(init?.signal).toBeInstanceOf(AbortSignal);
    expect(JSON.parse(String(init?.body))).toEqual({ ref: "main", inputs: { scan_run_id: scanId } });
  });
  it.each([400, 401, 403, 404, 422, 429])("recognizes definite refusal %s without reading provider detail", async (status) => {
    const response = jsonResponse({ secret: "private provider body" }, status);
    const read = vi.spyOn(response, "json");
    const transport = vi.fn<typeof fetch>().mockResolvedValue(response);
    expect(await dispatchScan(config, scanId, transport)).toBe("rejected");
    expect(read).not.toHaveBeenCalled();
    expect(transport).toHaveBeenCalledOnce();
  });
  it.each([202, 204, 301, 408, 409, 500, 502, 503, 504])("preserves uncertainty on unexpected HTTP %s", async (status) => {
    const transport = vi.fn<typeof fetch>().mockResolvedValue(new Response(null, { status }));
    expect(await dispatchScan(config, scanId, transport)).toBe("ambiguous");
    expect(transport).toHaveBeenCalledOnce();
  });
  it.each([{ body: {} }, { body: null }, { body: { workflow_run_id: -1 } }, { body: { workflow_run_id: "123" } }])("rejects malformed acceptance $body without retry", async ({ body }) => {
    const transport = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(body));
    expect(await dispatchScan(config, scanId, transport)).toBe("ambiguous");
    expect(transport).toHaveBeenCalledOnce();
  });
  it("treats invalid JSON acceptance as ambiguous", async () => {
    const transport = vi.fn<typeof fetch>().mockResolvedValue(new Response("invalid json"));
    expect(await dispatchScan(config, scanId, transport)).toBe("ambiguous");
    expect(transport).toHaveBeenCalledOnce();
  });
  it("does not retry a timed-out launch", async () => {
    const transport = vi.fn<typeof fetch>((_url, init) => new Promise((_resolve, reject) => {
      init!.signal!.addEventListener("abort", () => reject(new Error("private timeout detail")));
    }));
    expect(await dispatchScan(config, scanId, transport, 10)).toBe("ambiguous");
    expect(transport).toHaveBeenCalledOnce();
  });
  it("does not dispatch an invalid scan ID", async () => {
    const transport = vi.fn<typeof fetch>();
    await expect(dispatchScan(config, "bad-input", transport)).rejects.toThrow();
    expect(transport).not.toHaveBeenCalled();
  });
});
