import { createClient } from "@supabase/supabase-js";
import { describe, expect, it, vi } from "vitest";
import { loadDashboardData } from "@/lib/scans/dashboard-data";
import { env, jsonResponse, row, scanId } from "./fixtures";

describe("dashboard refresh preserves newest-completed results", () => {
  function harness(failure?: string) {
    const completedId = "33333333-3333-4333-8333-333333333333";
    const transport = vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input));
      const table = url.pathname.split("/").pop();
      if (table === failure) return jsonResponse({ message: "unavailable" }, 503);
      const data = table === "targets" ? [{ id: "target" }]
        : table === "scan_runs" ? [url.searchParams.has("status") ? { ...row("completed"), id: completedId } : row("queued")]
        : [{ id: `${table}-row`, scan_run_id: completedId }];
      return jsonResponse(data);
    });
    const client = createClient(env.NEXT_PUBLIC_SUPABASE_URL, env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY, {
      auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false }, global: { fetch: transport },
    });
    return { client, transport, completedId };
  }
  it("keeps newest active status separate from newest completed data, without an age window", async () => {
    const h = harness();
    const data = await loadDashboardData(h.client);
    expect(data?.scans.map((scan) => scan.id)).toEqual([scanId, h.completedId]);
    expect(data?.listings).toEqual([{ id: "listings-row", scan_run_id: h.completedId }]);
    expect(data?.evaluations).toEqual([{ id: "evaluations-row", scan_run_id: h.completedId }]);
    expect(h.transport).toHaveBeenCalledTimes(5);
    for (const call of h.transport.mock.calls) {
      const url = new URL(String(call[0]));
      expect(url.searchParams.has("created_at")).toBe(false);
      if (/\/(listings|evaluations)$/.test(url.pathname)) expect(url.searchParams.get("scan_run_id")).toBe(`eq.${h.completedId}`);
    }
  });
  it.each(["targets", "scan_runs", "listings", "evaluations"])("does not publish an empty replacement on %s failure", async (table) => {
    const h = harness(table);
    expect(await loadDashboardData(h.client)).toBeNull();
    expect(h.transport.mock.calls.length).toBe(table === "targets" || table === "scan_runs" ? 3 : 5);
  });
  it("catches thrown reads without clearing existing state", async () => {
    const h = harness();
    h.transport.mockRejectedValue(new Error("offline"));
    expect(await loadDashboardData(h.client)).toBeNull();
    expect(h.transport).toHaveBeenCalledTimes(3);
  });
  it("deduplicates a newest scan that is also the newest completion", async () => {
    const h = harness();
    h.transport.mockImplementation(async () => jsonResponse([{ ...row("completed"), id: h.completedId }]));
    expect((await loadDashboardData(h.client))?.scans).toHaveLength(1);
  });
  it("clears expired results only after successful confirmation of no completed scan", async () => {
    const h = harness();
    h.transport.mockImplementation(async () => jsonResponse([]));
    expect(await loadDashboardData(h.client)).toEqual({ targets: [], scans: [], listings: [], evaluations: [] });
    expect(h.transport).toHaveBeenCalledTimes(3);
  });
});
