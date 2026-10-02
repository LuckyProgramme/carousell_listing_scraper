import type { SupabaseClient } from "@supabase/supabase-js";
import type { InitialData, ScanRun } from "@/lib/types";

// Publish only a complete, successful snapshot; failed reads keep visible deals.
export async function loadDashboardData(client: SupabaseClient): Promise<InitialData | null> {
  try {
    const signal = AbortSignal.timeout(10_000);
    const [targets, latest, completed] = await Promise.all([
      client.from("targets").select("*").order("item_name").abortSignal(signal).retry(false),
      client.from("scan_runs").select("*").order("created_at", { ascending: false }).limit(1).abortSignal(signal).retry(false),
      client.from("scan_runs").select("*").eq("status", "completed").order("completed_at", { ascending: false }).limit(1).abortSignal(signal).retry(false),
    ]);
    if ([targets, latest, completed].some((result) => result.error || !Array.isArray(result.data))) return null;
    const newestScan = (latest.data as ScanRun[])[0] ?? null;
    const newestCompletedScan = (completed.data as ScanRun[])[0] ?? null;
    const scans = [newestScan, newestCompletedScan].filter(
      (scan, index, rows): scan is ScanRun => Boolean(scan) && rows.findIndex((row) => row?.id === scan?.id) === index,
    );
    if (!newestCompletedScan) return { targets: targets.data!, scans, listings: [], evaluations: [] };
    const [listings, evaluations] = await Promise.all([
      client.from("listings").select("*").eq("scan_run_id", newestCompletedScan.id).order("created_at", { ascending: false }).abortSignal(signal).retry(false),
      client.from("evaluations").select("*").eq("scan_run_id", newestCompletedScan.id).order("created_at", { ascending: false }).abortSignal(signal).retry(false),
    ]);
    if ([listings, evaluations].some((result) => result.error || !Array.isArray(result.data))) return null;
    return { targets: targets.data!, scans, listings: listings.data!, evaluations: evaluations.data! };
  } catch { return null; }
}
