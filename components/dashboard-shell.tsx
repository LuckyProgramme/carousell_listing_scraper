"use client";

import {
  AlertCircle,
  CheckCircle2,
  ChevronRight,
  Crosshair,
  ExternalLink,
  LayoutDashboard,
  ListFilter,
  LogOut,
  Pencil,
  Plus,
  ScanLine,
  ScanSearch,
  Trash2,
  X,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ListingThumbnail } from "@/components/listing-thumbnail";
import { performScanAction } from "@/lib/scans/client-actions";
import { loadDashboardData } from "@/lib/scans/dashboard-data";
import { createClient } from "@/lib/supabase/client";
import type { Evaluation, InitialData, Listing, ScanRun, SearchMode, Target, TargetType } from "@/lib/types";

type View = "dashboard" | "targets" | "results";
type ResultView = "deals" | "all";

interface TargetDraft {
  item_name: string;
  category: string;
  search_mode: SearchMode;
  retail_price: string;
  deal_price: string;
  downsizing_keywords: string;
  freebie_keywords: string;
  notes: string;
  target_type: TargetType;
  allow_bundle_check: boolean;
  enabled: boolean;
}

const emptyDraft: TargetDraft = {
  item_name: "",
  category: "",
  search_mode: "Item Name",
  retail_price: "",
  deal_price: "",
  downsizing_keywords: "",
  freebie_keywords: "",
  notes: "",
  target_type: "Hardware",
  allow_bundle_check: false,
  enabled: true,
};

const activeStatuses = new Set(["queued", "scanning", "evaluating", "saving"]);
const statusLabels: Record<string, string> = {
  queued: "Queued",
  scanning: "Scanning Carousell",
  evaluating: "Evaluating candidates",
  saving: "Saving results",
  completed: "Scan completed",
  failed: "Scan failed",
};
const statusProgress: Record<string, number> = { queued: 10, scanning: 42, evaluating: 72, saving: 90, completed: 100, failed: 100 };

function currency(value: number | null | undefined) {
  if (value == null) return "Price unavailable";
  return new Intl.NumberFormat("en-PH", { style: "currency", currency: "PHP", maximumFractionDigits: 0 }).format(value);
}

function relativeDate(value: string | null | undefined) {
  if (!value) return "No completed scans yet";
  return new Intl.DateTimeFormat("en-PH", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function keywords(value: string) {
  return value.split(",").map((item) => item.trim().toLowerCase()).filter(Boolean);
}

function targetToDraft(target: Target): TargetDraft {
  return {
    item_name: target.item_name,
    category: target.category,
    search_mode: target.search_mode,
    retail_price: target.retail_price?.toString() ?? "",
    deal_price: target.deal_price.toString(),
    downsizing_keywords: target.downsizing_keywords.join(", "),
    freebie_keywords: target.freebie_keywords.join(", "),
    notes: target.notes,
    target_type: target.target_type,
    allow_bundle_check: target.allow_bundle_check,
    enabled: target.enabled,
  };
}

export function DashboardShell({ email, initialData }: { email: string; initialData: InitialData }) {
  const [view, setView] = useState<View>("dashboard");
  const [resultView, setResultView] = useState<ResultView>("deals");
  const [targets, setTargets] = useState(initialData.targets);
  const [scans, setScans] = useState(initialData.scans);
  const [listings, setListings] = useState(initialData.listings);
  const [evaluations, setEvaluations] = useState(initialData.evaluations);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [refreshRequired, setRefreshRequired] = useState(false);
  const scanActionInFlight = useRef(false);
  const refreshInFlight = useRef<Promise<boolean> | null>(null);
  const [editing, setEditing] = useState<Target | null | "new">(null);
  const [draft, setDraft] = useState<TargetDraft>(emptyDraft);
  const [formError, setFormError] = useState("");
  const supabase = useMemo(() => createClient(), []);

  const latestScan = scans[0] ?? null;
  const latestCompletedScan = scans.find((scan) => scan.status === "completed") ?? null;
  const isActive = Boolean(latestScan && activeStatuses.has(latestScan.status));
  const enabledCount = targets.filter((target) => target.enabled).length;
  const listingById = useMemo(() => new Map(listings.map((listing) => [listing.id, listing])), [listings]);
  const deals = useMemo(
    () => evaluations.filter((evaluation) => evaluation.accepted).map((evaluation) => ({ evaluation, listing: listingById.get(evaluation.listing_id) })).filter((row): row is { evaluation: Evaluation; listing: Listing } => Boolean(row.listing)),
    [evaluations, listingById],
  );
  const reload = useCallback(async (): Promise<boolean> => {
    // An action needs a fresh read AFTER its POST, not a pre-action poll result.
    while (refreshInFlight.current) await refreshInFlight.current;
    const pending = (async () => {
      const data = await loadDashboardData(supabase);
      if (!data) return false;
      setTargets(data.targets);
      setScans(data.scans);
      setListings(data.listings);
      setEvaluations(data.evaluations);
      return true;
    })();
    refreshInFlight.current = pending;
    try { return await pending; }
    finally { refreshInFlight.current = null; }
  }, [supabase]);

  useEffect(() => {
    if (!isActive && !refreshRequired) return;
    const timer = window.setInterval(() => {
      if (scanActionInFlight.current || refreshInFlight.current) return;
      void reload().then((refreshed) => setRefreshRequired(!refreshed));
    }, 3500);
    return () => window.clearInterval(timer);
  }, [isActive, refreshRequired, reload]);

  const scanDisabled = busy || isActive || refreshRequired || enabledCount === 0;

  async function runScanAction(action: "start" | "recover") {
    if (scanActionInFlight.current || busy || (action === "start" ? scanDisabled : latestScan?.status !== "queued")) return;
    scanActionInFlight.current = true;
    try {
      await performScanAction(action, { refresh: reload, setBusy, setNotice, setRefreshRequired });
    } finally { scanActionInFlight.current = false; }
  }

  async function startScan() { await runScanAction("start"); }
  async function recoverQueuedScan() {
    await runScanAction("recover");
  }
  async function refreshStatus() {
    if (scanActionInFlight.current || busy) return;
    scanActionInFlight.current = true;
    setBusy(true);
    try { setRefreshRequired(!await reload()); }
    finally { setBusy(false); scanActionInFlight.current = false; }
  }

  function openTarget(target?: Target) {
    setFormError("");
    setEditing(target ?? "new");
    setDraft(target ? targetToDraft(target) : emptyDraft);
  }

  async function saveTarget(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const dealPrice = Number(draft.deal_price);
    const retailPrice = draft.retail_price ? Number(draft.retail_price) : null;
    if (!draft.item_name.trim() || !draft.category.trim() || !Number.isFinite(dealPrice) || dealPrice <= 0 || (retailPrice != null && (!Number.isFinite(retailPrice) || retailPrice <= 0))) {
      setFormError("Add an item name, category, and valid positive prices.");
      return;
    }
    setBusy(true);
    const payload = {
      item_name: draft.item_name.trim(),
      category: draft.category.trim(),
      search_mode: draft.search_mode,
      retail_price: retailPrice,
      deal_price: dealPrice,
      downsizing_keywords: keywords(draft.downsizing_keywords),
      freebie_keywords: keywords(draft.freebie_keywords),
      notes: draft.notes.trim(),
      target_type: draft.target_type,
      allow_bundle_check: draft.allow_bundle_check,
      enabled: draft.enabled,
    };
    let error;
    if (editing === "new") {
      const { data: userData } = await supabase.auth.getUser();
      ({ error } = await supabase.from("targets").insert({ ...payload, owner_id: userData.user?.id }));
    } else if (editing) {
      ({ error } = await supabase.from("targets").update(payload).eq("id", editing.id));
    }
    if (error) {
      setFormError("The target could not be saved. Check the values and try again.");
      setBusy(false);
      return;
    }
    setEditing(null);
    await reload();
    setBusy(false);
  }

  async function toggleTarget(target: Target) {
    await supabase.from("targets").update({ enabled: !target.enabled }).eq("id", target.id);
    await reload();
  }

  async function deleteTarget(target: Target) {
    if (!window.confirm(`Delete ${target.item_name}? Previous scan snapshots will remain until they expire.`)) return;
    await supabase.from("targets").delete().eq("id", target.id);
    await reload();
  }

  const latestStatus = latestScan ? statusLabels[latestScan.status] ?? latestScan.status : "Ready to scan";
  const progress = latestScan ? statusProgress[latestScan.status] ?? 0 : 0;

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand"><span className="brand-mark"><ScanSearch aria-hidden="true" /></span><span>Deal Finder</span></div>
        <nav aria-label="Main navigation">
          <button type="button" className={view === "dashboard" ? "active" : ""} onClick={() => setView("dashboard")}><LayoutDashboard aria-hidden="true" />Dashboard</button>
          <button type="button" className={view === "targets" ? "active" : ""} onClick={() => setView("targets")}><Crosshair aria-hidden="true" />Targets</button>
          <button type="button" className={view === "results" ? "active" : ""} onClick={() => setView("results")}><ListFilter aria-hidden="true" />Results</button>
        </nav>
        <div className="account"><span className="avatar">D</span><span className="account-email">{email}</span><form action="/auth/signout" method="post"><button className="icon-button" type="submit" aria-label="Sign out"><LogOut aria-hidden="true" /></button></form></div>
      </header>

      <main className="page-shell">
        {view === "dashboard" ? (
          <>
            <PageHeading eyebrow="Dashboard" title="Ready for a fresh scan" subtitle={`${enabledCount} target${enabledCount === 1 ? "" : "s"} enabled · Last scan ${relativeDate(latestCompletedScan?.completed_at)}`} action={<button className="primary-button" type="button" onClick={startScan} disabled={scanDisabled}><ScanLine aria-hidden="true" />{busy ? "Checking…" : isActive ? latestStatus : "Scan Now"}</button>} />
            {notice ? <div className="notice" role="status">{notice}</div> : null}
            {refreshRequired && !busy ? <div className="notice" role="status">Scan status could not be refreshed. Your previous results are still shown. Check status before starting another scan. <button className="text-button" type="button" onClick={refreshStatus}>Refresh status</button></div> : null}
            <div className="dashboard-layout">
              <StatusPanel scan={latestScan} progress={progress} enabledCount={enabledCount} onRetry={startScan} onRecover={recoverQueuedScan} busy={busy} retryDisabled={scanDisabled} />
              <section className="results-section" aria-labelledby="recent-deals-heading">
                <SectionHeading id="recent-deals-heading" title="Recent deals" subtitle={latestCompletedScan ? `From the newest completed scan · ${relativeDate(latestCompletedScan.completed_at)}` : "From your newest completed scan."} action={<button className="text-button" type="button" onClick={() => setView("results")}>All results <ChevronRight aria-hidden="true" /></button>} />
                {deals.length ? deals.slice(0, 5).map((row) => <DealRow key={row.evaluation.id} {...row} />) : <EmptyState icon={latestScan?.status === "failed" ? AlertCircle : CheckCircle2} title={latestScan?.status === "completed" ? "No qualifying deals found" : "Your deals will appear here"} body={latestScan?.status === "completed" ? "The scan completed successfully, but nothing passed all deal checks." : "Press Scan Now to check every enabled target."} />}
              </section>
            </div>
          </>
        ) : null}

        {view === "targets" ? (
          <>
            <PageHeading eyebrow="Search setup" title="Targets" subtitle="Changes apply to your next scan." action={<button className="primary-button" type="button" onClick={() => openTarget()}><Plus aria-hidden="true" />Add target</button>} />
            <section className="target-list" aria-label="Search targets">
              {targets.length ? targets.map((target) => (
                <article className="target-row" key={target.id}>
                  <span className="target-icon"><Crosshair aria-hidden="true" /></span>
                  <div className="target-main"><strong>{target.item_name}</strong><span>{target.target_type} · {target.search_mode} search · {target.category}</span></div>
                  <div className="target-price"><span>Deal price</span><strong>{currency(target.deal_price)}</strong></div>
                  <button className={`status-toggle ${target.enabled ? "enabled" : ""}`} type="button" onClick={() => toggleTarget(target)}>{target.enabled ? "Enabled" : "Disabled"}</button>
                  <div className="row-actions"><button className="icon-button" type="button" onClick={() => openTarget(target)} aria-label={`Edit ${target.item_name}`}><Pencil aria-hidden="true" /></button><button className="icon-button danger" type="button" onClick={() => deleteTarget(target)} aria-label={`Delete ${target.item_name}`}><Trash2 aria-hidden="true" /></button></div>
                </article>
              )) : <EmptyState icon={Crosshair} title="Add your first target" body="Targets tell the scanner what item and price should count as a deal." />}
            </section>
          </>
        ) : null}

        {view === "results" ? (
          <>
            <PageHeading eyebrow="Newest completed scan" title="Results" subtitle={latestCompletedScan ? `Completed ${relativeDate(latestCompletedScan.completed_at)} · older stored data is cleaned up automatically after 72 hours.` : "Complete a scan to see its results."} />
            <div className="result-tabs" role="tablist" aria-label="Result type"><button type="button" role="tab" aria-selected={resultView === "deals"} className={resultView === "deals" ? "active" : ""} onClick={() => setResultView("deals")}>Deals {deals.length}</button><button type="button" role="tab" aria-selected={resultView === "all"} className={resultView === "all" ? "active" : ""} onClick={() => setResultView("all")}>All listings {listings.length}</button></div>
            <section className="results-section full-results" aria-label={resultView === "deals" ? "Accepted deals" : "All listings"}>
              {resultView === "deals" ? deals.map((row) => <DealRow key={row.evaluation.id} {...row} />) : listings.map((listing) => <ListingRow key={listing.id} listing={listing} />)}
              {resultView === "deals" && !deals.length ? <EmptyState icon={ListFilter} title="No deals in the newest completed scan" body="The scan completed successfully, but no listing passed every deal check." /> : null}
              {resultView === "all" && !listings.length ? <EmptyState icon={ListFilter} title="No listings in the newest completed scan" body="Complete a scan to populate this view." /> : null}
            </section>
          </>
        ) : null}
      </main>

      {editing ? <TargetDialog draft={draft} setDraft={setDraft} error={formError} busy={busy} title={editing === "new" ? "Add target" : `Edit ${editing.item_name}`} onClose={() => setEditing(null)} onSubmit={saveTarget} /> : null}
    </div>
  );
}

function PageHeading({ eyebrow, title, subtitle, action }: { eyebrow: string; title: string; subtitle: string; action?: React.ReactNode }) {
  return <header className="page-heading"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p className="supporting">{subtitle}</p></div>{action}</header>;
}

function SectionHeading({ id, title, subtitle, action }: { id: string; title: string; subtitle: string; action?: React.ReactNode }) {
  return <header className="section-heading"><div><h2 id={id}>{title}</h2><p>{subtitle}</p></div>{action}</header>;
}

function StatusPanel({ scan, progress, enabledCount, onRetry, onRecover, busy, retryDisabled }: { scan: ScanRun | null; progress: number; enabledCount: number; onRetry: () => void; onRecover: () => void; busy: boolean; retryDisabled: boolean }) {
  const label = scan ? statusLabels[scan.status] ?? scan.status : "Ready to scan";
  return <aside className={`status-panel ${scan?.status === "failed" ? "failed" : ""}`} aria-label="Latest scan status">
    <span className="status-dot"></span><h2>{label}</h2>
    <p>{scan?.status === "failed" ? scan.safe_error ?? "The scan stopped before it finished." : scan?.status === "completed" ? `Completed ${relativeDate(scan.completed_at)}.` : scan && activeStatuses.has(scan.status) ? "A second scan cannot start until this one finishes." : `The next scan will use ${enabledCount} enabled target${enabledCount === 1 ? "" : "s"}.`}</p>
    <div className="progress-track" role="progressbar" aria-label="Scan progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress}><span style={{ width: `${progress}%` }} /></div>
    <div className="scan-counts"><span><small>Checked</small><strong>{scan?.listings_count ?? 0}</strong></span><span><small>Candidates</small><strong>{scan?.candidates_count ?? 0}</strong></span><span><small>Deals</small><strong>{scan?.deals_count ?? 0}</strong></span></div>
    {scan?.status === "failed" ? <button className="secondary-button" type="button" onClick={onRetry} disabled={retryDisabled}>Try Again</button> : null}
    {scan?.status === "queued" ? <button className="secondary-button" type="button" onClick={onRecover} disabled={busy}>{busy ? "Checking…" : "Release if stuck"}</button> : null}
  </aside>;
}

function DealRow({ evaluation, listing }: { evaluation: Evaluation; listing: Listing }) {
  return <article className="listing-row"><ListingThumbnail src={listing.thumbnail_url} title={listing.title} /><div className="listing-main"><div className="listing-labels"><span className="target-chip">{evaluation.matched_item ?? "Matched target"}</span><span className="confidence">{evaluation.confidence ?? Math.round(evaluation.local_match_score ?? 0)}% match</span></div><h3>{listing.title}</h3><p>{[evaluation.final_condition || listing.condition, listing.location, evaluation.freebies.length ? `Includes ${evaluation.freebies.join(", ")}` : ""].filter(Boolean).join(" · ")}</p></div><div className="listing-price"><strong>{currency(evaluation.evaluated_price ?? listing.price)}</strong>{evaluation.savings != null ? <span>Save {currency(evaluation.savings)}</span> : null}<a href={listing.link} target="_blank" rel="noreferrer">View on Carousell <ExternalLink aria-hidden="true" /></a></div></article>;
}

function ListingRow({ listing }: { listing: Listing }) {
  return <article className="listing-row"><ListingThumbnail src={listing.thumbnail_url} title={listing.title} /><div className="listing-main"><div className="listing-labels"><span className="target-chip">{listing.category || "Carousell"}</span><span className="confidence">{listing.price_flag || "Normal"}</span></div><h3>{listing.title}</h3><p>{[listing.condition, listing.seller, listing.location].filter(Boolean).join(" · ")}</p></div><div className="listing-price"><strong>{currency(listing.price)}</strong><a href={listing.link} target="_blank" rel="noreferrer">View on Carousell <ExternalLink aria-hidden="true" /></a></div></article>;
}

function EmptyState({ icon: Icon, title, body }: { icon: typeof Crosshair; title: string; body: string }) {
  return <div className="empty-state"><Icon aria-hidden="true" /><h3>{title}</h3><p>{body}</p></div>;
}

function TargetDialog({ draft, setDraft, error, busy, title, onClose, onSubmit }: { draft: TargetDraft; setDraft: React.Dispatch<React.SetStateAction<TargetDraft>>; error: string; busy: boolean; title: string; onClose: () => void; onSubmit: (event: FormEvent<HTMLFormElement>) => void }) {
  const set = <K extends keyof TargetDraft>(key: K, value: TargetDraft[K]) => setDraft((current) => ({ ...current, [key]: value }));
  return <div className="dialog-backdrop" role="presentation"><section className="target-dialog" role="dialog" aria-modal="true" aria-labelledby="target-dialog-title"><header><div><p className="eyebrow">Search target</p><h2 id="target-dialog-title">{title}</h2></div><button className="icon-button" type="button" onClick={onClose} aria-label="Close"><X aria-hidden="true" /></button></header><form onSubmit={onSubmit}>
    <div className="form-grid"><label>Item name<input value={draft.item_name} onChange={(event) => set("item_name", event.target.value)} required /></label><label>Category<input value={draft.category} onChange={(event) => set("category", event.target.value)} required /></label><label>Search mode<select value={draft.search_mode} onChange={(event) => set("search_mode", event.target.value as SearchMode)}><option>Item Name</option><option>Category</option></select></label><label>Target type<select value={draft.target_type} onChange={(event) => set("target_type", event.target.value as TargetType)}><option>Hardware</option><option>Game</option></select></label><label>Deal price (PHP)<input inputMode="decimal" value={draft.deal_price} onChange={(event) => set("deal_price", event.target.value)} required /></label><label>Retail price (PHP)<input inputMode="decimal" value={draft.retail_price} onChange={(event) => set("retail_price", event.target.value)} /></label></div>
    <label>Condition downsizing keywords<input value={draft.downsizing_keywords} onChange={(event) => set("downsizing_keywords", event.target.value)} placeholder="scratches, issue, repair" /></label><label>Freebie keywords<input value={draft.freebie_keywords} onChange={(event) => set("freebie_keywords", event.target.value)} placeholder="case, charger, games" /></label><label>Notes<textarea value={draft.notes} onChange={(event) => set("notes", event.target.value)} rows={3} /></label><div className="check-row"><label><input type="checkbox" checked={draft.allow_bundle_check} onChange={(event) => set("allow_bundle_check", event.target.checked)} />Allow bundle checks</label><label><input type="checkbox" checked={draft.enabled} onChange={(event) => set("enabled", event.target.checked)} />Enabled for next scan</label></div>{error ? <p className="form-error" role="alert">{error}</p> : null}<footer><button className="secondary-button" type="button" onClick={onClose}>Cancel</button><button className="primary-button" type="submit" disabled={busy}>{busy ? "Saving…" : "Save target"}</button></footer>
  </form></section></div>;
}
