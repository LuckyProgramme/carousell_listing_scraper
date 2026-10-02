import { describe, expect, it, vi } from "vitest";
import { performScanAction } from "@/lib/scans/client-actions";
import { jsonResponse, scanId } from "./fixtures";

function harness() {
  const events: string[] = [];
  let busy = false;
  let required = false;
  let notice = "";
  const fetch = vi.fn();
  const refresh = vi.fn(async () => { events.push("refresh"); return true; });
  const dependencies = {
    fetch, refresh,
    setBusy: (value: boolean) => { busy = value; events.push(`busy:${value}`); },
    setRefreshRequired: (value: boolean) => { required = value; events.push(`required:${value}`); },
    setNotice: (value: string) => { notice = value; },
  };
  return { dependencies, fetch, refresh, events, state: () => ({ busy, required, notice }) };
}

describe("dashboard scan action feedback", () => {
  it("renders the ambiguous startup notice and refreshes before releasing the button", async () => {
    const h = harness();
    const notice = "Startup could not be confirmed. Check progress; release only if stuck.";
    h.fetch.mockResolvedValue(jsonResponse({ data: { scan: { id: scanId, status: "queued" }, notice } }, 202));
    await performScanAction("start", h.dependencies);
    expect(h.state()).toEqual({ busy: false, required: false, notice });
    expect(h.events).toEqual(["busy:true", "required:true", "refresh", "required:false", "busy:false"]);
    expect(h.fetch).toHaveBeenCalledOnce();
    expect(h.fetch.mock.calls[0]).toMatchObject(["/api/scan", { method: "POST", cache: "no-store", signal: expect.any(AbortSignal) }]);
  });
  it("shows successful queuing when there is no notice", async () => {
    const h = harness();
    h.fetch.mockResolvedValue(jsonResponse({ data: { scan: { id: scanId, status: "queued" } } }, 202));
    await performScanAction("start", h.dependencies);
    expect(h.state().notice).toBe("Your scan was queued successfully.");
  });
  it.each(["start", "recover"] as const)("clears busy after %s transport failure and still refreshes", async (action) => {
    const h = harness();
    h.fetch.mockRejectedValue(new TypeError("private network details"));
    await performScanAction(action, h.dependencies);
    expect(h.state()).toMatchObject({ busy: false, required: false });
    expect(h.state().notice).not.toContain("private");
    expect(h.state().notice).toMatch(/could not be/);
    expect(h.refresh).toHaveBeenCalledOnce();
    expect(h.fetch).toHaveBeenCalledOnce();
  });
  it.each(["start", "recover"] as const)("handles %s HTML/invalid JSON without falsely reporting success", async (action) => {
    const h = harness();
    h.fetch.mockResolvedValue(new Response("<html>login</html>", { status: 200 }));
    await performScanAction(action, h.dependencies);
    expect(h.state().busy).toBe(false);
    expect(h.state().notice).toMatch(/could not be/);
    expect(h.refresh).toHaveBeenCalledOnce();
  });
  it.each([{}, null, { data: {} }, { data: { scan: { id: scanId, status: "invalid" } } }, { data: { scan: { id: "wrong", status: "queued" } } }])("validates startup envelope %#", async (payload) => {
    const h = harness();
    h.fetch.mockResolvedValue(jsonResponse(payload));
    await performScanAction("start", h.dependencies);
    expect(h.state().notice).toMatch(/could not be confirmed/);
    expect(h.state().busy).toBe(false);
    expect(h.refresh).toHaveBeenCalledOnce();
  });
  it.each([409, 503])("displays safe %s error then reloads potentially changed status", async (status) => {
    const h = harness();
    h.fetch.mockResolvedValue(jsonResponse({ error: "A scan is already queued or running." }, status));
    await performScanAction("start", h.dependencies);
    expect(h.state().notice).toBe("A scan is already queued or running.");
    expect(h.refresh).toHaveBeenCalledOnce();
  });
  it.each([false, true])("reports recovered=%s and refreshes", async (recovered) => {
    const h = harness();
    h.fetch.mockResolvedValue(jsonResponse({ data: { recovered, scan: recovered ? { id: scanId, status: "failed" } : null } }));
    await performScanAction("recover", h.dependencies);
    expect(h.fetch.mock.calls[0][0]).toBe("/api/scan/recover");
    expect(h.state().notice).toMatch(recovered ? /was released/ : /No changes were made/);
    expect(h.state()).toMatchObject({ busy: false, required: false });
  });
  it.each([{ recovered: "true" }, { recovered: true, scan: null }, { recovered: false }, { recovered: true, scan: { id: scanId, status: "scanning" } }])("rejects malformed recovery %#", async (data) => {
    const h = harness();
    h.fetch.mockResolvedValue(jsonResponse({ data }));
    await performScanAction("recover", h.dependencies);
    expect(h.state().notice).toMatch(/could not be checked/);
    expect(h.state().busy).toBe(false);
  });
  it.each(["false", "throw"])("clears busy but requires status check when refresh returns %s", async (outcome) => {
    const h = harness();
    h.fetch.mockRejectedValue(new Error("offline"));
    if (outcome === "throw") h.refresh.mockRejectedValue(new Error("offline"));
    else h.refresh.mockResolvedValue(false);
    await performScanAction("start", h.dependencies);
    expect(h.state()).toMatchObject({ busy: false, required: true });
    expect(h.fetch).toHaveBeenCalledOnce();
  });
  it("holds the busy lock until the post-action refresh finishes", async () => {
    const h = harness();
    let complete!: (value: boolean) => void;
    h.refresh.mockReturnValue(new Promise<boolean>((resolve) => { complete = resolve; }));
    h.fetch.mockResolvedValue(jsonResponse({ data: { scan: { id: scanId, status: "queued" } } }, 202));
    const pending = performScanAction("start", h.dependencies);
    await vi.waitFor(() => expect(h.refresh).toHaveBeenCalledOnce());
    expect(h.state()).toMatchObject({ busy: true, required: true });
    complete(true);
    await pending;
    expect(h.state()).toMatchObject({ busy: false, required: false });
  });
});
