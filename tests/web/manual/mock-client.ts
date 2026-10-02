import { createClient as createSupabaseClient } from "@supabase/supabase-js";
import type { InitialData, ScanRun } from "@/lib/types";

const owner = "749743db-c366-47c9-9373-bec966857b32";
const completedId = "33333333-3333-4333-8333-333333333333";
const queuedId = "11111111-1111-4111-8111-111111111111";
const time = "2026-10-02T04:00:00Z";
export const scenario = new URLSearchParams(location.search).get("scenario") ?? "ambiguous";
const completion: ScanRun = { id: completedId, owner_id: owner, status: "completed", listings_count: 1, candidates_count: 1, deals_count: 1, safe_error: null, target_snapshot: [], created_at: time, started_at: time, completed_at: time, updated_at: time };
let latest: ScanRun = { ...completion };
if (["recent", "recovered", "race", "queued", "running"].includes(scenario)) {
  latest = { ...completion, id: queuedId, status: scenario === "running" ? "scanning" : "queued", completed_at: null, created_at: "2026-10-02T05:00:00Z" };
}
if (scenario === "failed") latest = { ...completion, id: queuedId, status: "failed", safe_error: "The scan could not be started." };
let failedReads = false;
export const requests: string[] = [];
export function restoreConnection() { failedReads = false; }
export function advanceScan() {
  if (latest.status === "queued") latest = { ...latest, status: "scanning" };
}
export const initialData: InitialData = {
  targets: [{ id: "target", owner_id: owner, item_name: "legion 5", category: "computers-tech", search_mode: "Item Name", retail_price: 70000, deal_price: 60000, downsizing_keywords: [], freebie_keywords: [], notes: "", target_type: "Hardware", allow_bundle_check: true, enabled: scenario !== "no-targets", created_at: time, updated_at: time }],
  scans: latest.id === completion.id ? [latest] : [latest, completion],
  listings: [{ id: "listing", scan_run_id: completedId, owner_id: owner, source_listing_id: "example", title: "Mock Legion 5 — previous completed deal", price: 45000, condition: "Like new", description: "Offline browser fixture", link: "https://www.carousell.ph/", seller: "Example", category: "computers-tech", thumbnail_url: null, seller_rating: null, seller_rating_count: null, like_count: null, location: null, listing_timestamp: null, price_flag: "", created_at: time }],
  evaluations: [{ id: "evaluation", scan_run_id: completedId, listing_id: "listing", owner_id: owner, target_id: "target", target_snapshot_id: "target", target_snapshot: {}, accepted: true, matched_item: "legion 5", confidence: 95, specs_matched: true, issues: [], freebies: [], final_condition: "Like new", deal_price: 60000, retail_price: 70000, evaluated_price: 45000, savings: 15000, audit_source: "Mock", local_match_score: 100, acceptance_reason: "Offline example", is_bundle: false, individual_price: null, price_evidence: null, condition_overridden: false, created_at: time }],
};
function json(value: unknown, status = 200) { return Response.json(value, { status }); }
export async function mockFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const url = new URL(String(input), location.origin);
  requests.push(`${init?.method ?? "GET"} ${url.pathname}${url.search}`);
  if (url.pathname === "/api/scan") {
    latest = { ...completion, id: queuedId, status: "queued", completed_at: null };
    if (scenario === "refresh-failure") { failedReads = true; throw new TypeError("offline fixture"); }
    if (scenario === "offline") throw new TypeError("lost response fixture");
    if (scenario === "invalid") return new Response("<html>invalid fixture</html>");
    return json({ data: { scan: { id: latest.id, status: latest.status }, ...(scenario === "ambiguous" ? { notice: "Startup could not be confirmed. Check scan progress before trying again; release the queue only if it remains stuck." } : {}) } }, 202);
  }
  if (url.pathname === "/api/scan/recover") {
    if (scenario === "recovered") { latest = { ...latest, status: "failed", safe_error: "The queue was released.", completed_at: time }; return json({ data: { recovered: true, scan: { id: latest.id, status: latest.status } } }); }
    if (scenario === "race") latest = { ...latest, status: "scanning" };
    return json({ data: { recovered: false, scan: null } });
  }
  if (url.origin !== "https://example.supabase.co") throw new Error("Unexpected fixture request blocked");
  if (failedReads) return json({ message: "offline fixture" }, 503);
  const table = url.pathname.split("/").pop();
  if (table === "scan_runs") return json([url.searchParams.has("status") ? completion : latest]);
  if (table === "targets") {
    if (init?.method === "PATCH") Object.assign(initialData.targets[0], JSON.parse(String(init.body)));
    return json(initialData.targets);
  }
  if (table === "listings") return json(initialData.listings);
  if (table === "evaluations") return json(initialData.evaluations);
  throw new Error("Unexpected fixture request blocked");
}
export function createClient() {
  return createSupabaseClient("https://example.supabase.co", "sb_publishable_test_only", {
    auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false }, global: { fetch: mockFetch },
  });
}
