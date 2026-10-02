import "server-only";
import type { createAdminClient } from "@/lib/supabase/admin";
import type { ScanStatus } from "@/lib/types";
import { ScanRequestError } from "./errors";

export class ActiveScanError extends ScanRequestError {
  constructor() { super("A scan is already queued or running.", 409); }
}
export class ScanStorageError extends ScanRequestError {
  constructor() { super("Saved data is temporarily unavailable. Please refresh scan status before trying again.", 503); }
}
export interface ScanRecord { id: string; owner_id: string; status: ScanStatus }
export interface ScanRepository {
  createQueuedScan(ownerId: string): Promise<ScanRecord>;
  failQueuedScan(scanId: string, ownerId: string, safeError: string): Promise<ScanRecord | null>;
  recoverStaleQueuedScan(ownerId: string, cutoff: Date): Promise<ScanRecord | null>;
}

const columns = "id,owner_id,status";
const statuses = new Set<ScanStatus>(["queued", "scanning", "evaluating", "saving", "completed", "failed"]);
export function assertUuid(value: string): void {
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value)) throw new ScanStorageError();
}
function record(value: unknown, ownerId: string, status: ScanStatus, scanId?: string): ScanRecord {
  if (!value || typeof value !== "object") throw new ScanStorageError();
  const row = value as ScanRecord;
  assertUuid(row.id ?? "");
  if (row.owner_id !== ownerId || row.status !== status || !statuses.has(row.status) || (scanId && row.id !== scanId)) throw new ScanStorageError();
  return { id: row.id, owner_id: row.owner_id, status: row.status };
}

export class SupabaseScanRepository implements ScanRepository {
  constructor(private readonly client: ReturnType<typeof createAdminClient>, private readonly now: () => Date = () => new Date()) {}

  async createQueuedScan(ownerId: string): Promise<ScanRecord> {
    assertUuid(ownerId);
    try {
      const { data, error } = await this.client.from("scan_runs")
        .insert({ owner_id: ownerId, status: "queued" }).select(columns).retry(false);
      if (error) {
        if (error.code === "23505" && error.message.includes('"scan_runs_one_active_per_owner_idx"')) throw new ActiveScanError();
        throw new ScanStorageError();
      }
      if (!Array.isArray(data) || data.length !== 1) throw new ScanStorageError();
      return record(data[0], ownerId, "queued");
    } catch (error) {
      if (error instanceof ActiveScanError) throw error;
      throw new ScanStorageError();
    }
  }

  private failureFields(safeError: string) {
    return { status: "failed", safe_error: safeError, completed_at: this.now().toISOString() };
  }

  async failQueuedScan(scanId: string, ownerId: string, safeError: string): Promise<ScanRecord | null> {
    assertUuid(scanId);
    assertUuid(ownerId);
    try {
      const { data, error } = await this.client.from("scan_runs").update(this.failureFields(safeError))
        .eq("id", scanId).eq("owner_id", ownerId).eq("status", "queued").select(columns).retry(false);
      if (error || !Array.isArray(data) || data.length > 1) throw new ScanStorageError();
      return data.length ? record(data[0], ownerId, "failed", scanId) : null;
    } catch { throw new ScanStorageError(); }
  }

  async recoverStaleQueuedScan(ownerId: string, cutoff: Date): Promise<ScanRecord | null> {
    assertUuid(ownerId);
    try {
      const { data, error } = await this.client.from("scan_runs")
        .update(this.failureFields("The queued scan did not start and was released. Please try again."))
        .eq("owner_id", ownerId).eq("status", "queued").lt("created_at", cutoff.toISOString()).select(columns).retry(false);
      if (error || !Array.isArray(data) || data.length > 1) throw new ScanStorageError();
      return data.length ? record(data[0], ownerId, "failed") : null;
    } catch { throw new ScanStorageError(); }
  }
}
