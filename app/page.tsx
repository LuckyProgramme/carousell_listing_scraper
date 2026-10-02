import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { DashboardShell } from "@/components/dashboard-shell";
import type { Evaluation, Listing, ScanRun, Target } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const supabase = await createClient();
  const { data: authData } = await supabase.auth.getUser();
  if (!authData.user) redirect("/login");

  const allowedEmail = (process.env.ALLOWED_USER_EMAIL ?? "dealfinder0322@gmail.com").toLowerCase();
  if ((authData.user.email ?? "").toLowerCase() !== allowedEmail) redirect("/auth/denied");

  const [{ data: targets }, { data: latestRows }, { data: completedRows }] = await Promise.all([
    supabase.from("targets").select("*").order("item_name"),
    supabase.from("scan_runs").select("*").order("created_at", { ascending: false }).limit(1),
    supabase.from("scan_runs").select("*").eq("status", "completed").order("completed_at", { ascending: false }).limit(1),
  ]);
  const latestScan = ((latestRows as ScanRun[] | null) ?? [])[0] ?? null;
  const latestCompletedScan = ((completedRows as ScanRun[] | null) ?? [])[0] ?? null;
  const scans = [latestScan, latestCompletedScan].filter(
    (scan, index, rows): scan is ScanRun => Boolean(scan) && rows.findIndex((row) => row?.id === scan?.id) === index,
  );
  let listings: Listing[] = [];
  let evaluations: Evaluation[] = [];

  if (latestCompletedScan) {
    const [listingResult, evaluationResult] = await Promise.all([
      supabase.from("listings").select("*").eq("scan_run_id", latestCompletedScan.id).order("created_at", { ascending: false }),
      supabase.from("evaluations").select("*").eq("scan_run_id", latestCompletedScan.id).order("created_at", { ascending: false }),
    ]);
    listings = (listingResult.data as Listing[] | null) ?? [];
    evaluations = (evaluationResult.data as Evaluation[] | null) ?? [];
  }

  return (
    <DashboardShell
      email={authData.user.email ?? "Personal account"}
      initialData={{
        targets: (targets as Target[] | null) ?? [],
        scans,
        listings,
        evaluations,
      }}
    />
  );
}
