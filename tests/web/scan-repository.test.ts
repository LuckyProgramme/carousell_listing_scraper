import { beforeEach, describe, expect, it, vi } from "vitest";
import { createAdminClient } from "@/lib/supabase/admin";
import { readStorageConfig } from "@/lib/scans/config";
import { ActiveScanError, ScanStorageError, SupabaseScanRepository } from "@/lib/scans/repository";
import { env, jsonResponse, ownerId, otherOwnerId, row, scanId } from "./fixtures";

let transport = vi.fn<typeof fetch>();
function repository() {
  return new SupabaseScanRepository(createAdminClient(readStorageConfig(env), { fetch: transport }), () => new Date("2026-10-02T03:30:00.000Z"));
}
function lastUrl() { return new URL(String(transport.mock.lastCall![0])); }
function lastBody() { return JSON.parse(String(transport.mock.lastCall![1]?.body)); }

beforeEach(() => { transport = vi.fn<typeof fetch>(); });

describe("owner-scoped scan storage", () => {
  it("inserts only the validated owner and queued state", async () => {
    transport.mockResolvedValue(jsonResponse([row()], 201));
    expect(await repository().createQueuedScan(ownerId)).toEqual(row());
    expect(lastBody()).toEqual({ owner_id: ownerId, status: "queued" });
    expect(new Headers(transport.mock.lastCall![1]?.headers).get("apikey")).toBe(env.SUPABASE_SECRET_KEY);
    expect(new Headers(transport.mock.lastCall![1]?.headers).get("authorization")).toBeNull();
  });

  it("maps only the named active-scan uniqueness error", async () => {
    transport.mockResolvedValue(jsonResponse({ code: "23505", message: 'duplicate key violates unique constraint "scan_runs_one_active_per_owner_idx"' }, 409));
    await expect(repository().createQueuedScan(ownerId)).rejects.toBeInstanceOf(ActiveScanError);
    expect(transport).toHaveBeenCalledOnce();
  });

  it("does not mislabel another constraint or disclose provider detail", async () => {
    transport.mockResolvedValue(jsonResponse({ code: "23505", message: 'secret detail: unique constraint "other_index"' }, 409));
    await expect(repository().createQueuedScan(ownerId)).rejects.toThrow(ScanStorageError);
    await expect(repository().createQueuedScan(ownerId)).rejects.not.toBeInstanceOf(ActiveScanError);
    await expect(repository().createQueuedScan(ownerId)).rejects.not.toThrow("secret detail");
  });

  it.each([503, 504, 409])("does not retry a failed insertion (HTTP %s)", async (status) => {
    transport.mockResolvedValue(jsonResponse({ message: "unavailable" }, status));
    await expect(repository().createQueuedScan(ownerId)).rejects.toThrow(ScanStorageError);
    expect(transport).toHaveBeenCalledOnce();
  });

  it("treats insertion transport loss as uncertainty and never inserts again", async () => {
    transport.mockRejectedValue(new Error("private transport exception"));
    await expect(repository().createQueuedScan(ownerId)).rejects.toThrow("refresh scan status");
    expect(transport).toHaveBeenCalledOnce();
  });

  it.each([{ rows: [] }, { rows: [row("scanning")] }, { rows: [row("queued", otherOwnerId)] }, { rows: [{ ...row(), id: "invalid" }] }])("rejects invalid insertion representation $rows", async ({ rows }) => {
    transport.mockResolvedValue(jsonResponse(rows, 201));
    await expect(repository().createQueuedScan(ownerId)).rejects.toThrow(ScanStorageError);
  });

  it("atomically fails only the specified owner's queued scan", async () => {
    transport.mockResolvedValue(jsonResponse([row("failed")]));
    expect(await repository().failQueuedScan(scanId, ownerId, "Safe failure.")).toEqual(row("failed"));
    expect(lastUrl().searchParams.get("id")).toBe(`eq.${scanId}`);
    expect(lastUrl().searchParams.get("owner_id")).toBe(`eq.${ownerId}`);
    expect(lastUrl().searchParams.get("status")).toBe("eq.queued");
    expect(lastBody()).toEqual({ status: "failed", safe_error: "Safe failure.", completed_at: "2026-10-02T03:30:00.000Z" });
  });

  it("leaves a claim/recovery race winner untouched when the conditional update returns no rows", async () => {
    transport.mockResolvedValue(jsonResponse([]));
    expect(await repository().failQueuedScan(scanId, ownerId, "Safe failure.")).toBeNull();
    expect(transport).toHaveBeenCalledOnce();
  });

  it("recovers only queued owner rows strictly older than the UTC cutoff", async () => {
    transport.mockResolvedValue(jsonResponse([row("failed")]));
    expect(await repository().recoverStaleQueuedScan(ownerId, new Date("2026-10-02T11:15:00+08:00"))).toEqual(row("failed"));
    expect(lastUrl().searchParams.get("owner_id")).toBe(`eq.${ownerId}`);
    expect(lastUrl().searchParams.get("status")).toBe("eq.queued");
    expect(lastUrl().searchParams.get("created_at")).toBe("lt.2026-10-02T03:15:00.000Z");
    expect(lastBody().completed_at).toBe("2026-10-02T03:30:00.000Z");
  });

  it("returns no recovery when the queue is recent or already running", async () => {
    transport.mockResolvedValue(jsonResponse([]));
    expect(await repository().recoverStaleQueuedScan(ownerId, new Date())).toBeNull();
  });

  it.each(["owner-1", "x&status=eq.scanning", ""]) ("rejects invalid owner IDs before storage: %s", async (owner) => {
    await expect(repository().createQueuedScan(owner)).rejects.toThrow();
    expect(transport).not.toHaveBeenCalled();
  });

  it("rejects invalid scan IDs and cutoff dates before mutation", async () => {
    await expect(repository().failQueuedScan("bad", ownerId, "Safe failure.")).rejects.toThrow();
    await expect(repository().recoverStaleQueuedScan(ownerId, new Date("bad"))).rejects.toThrow();
    expect(transport).not.toHaveBeenCalled();
  });
});
