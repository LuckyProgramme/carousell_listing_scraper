import "server-only";
import { createAdminClient } from "@/lib/supabase/admin";
import { authenticateScan, guardScanRequest } from "./auth";
import { readIdentityConfig, readStorageConfig, type ScanEnvironment, type StorageConfig } from "./config";
import { ScanRequestError } from "./errors";
import { SupabaseScanRepository, type ScanRepository } from "./repository";

interface RecoveryDependencies {
  environment?: ScanEnvironment;
  authenticate?: typeof authenticateScan;
  repository?: (storage: StorageConfig) => ScanRepository;
  now?: () => Date;
}

export async function recoverQueuedScan(request: Request, dependencies: RecoveryDependencies = {}): Promise<Response> {
  try {
    const environment = dependencies.environment ?? process.env;
    if (environment.VERCEL_ENV && environment.VERCEL_ENV !== "production") {
      throw new ScanRequestError("Scanning is disabled on this deployment.", 403);
    }
    const identity = readIdentityConfig(environment);
    guardScanRequest(request, identity, environment);
    const ownerId = await (dependencies.authenticate ?? authenticateScan)(identity);
    // Recovery must remain usable even if dispatch configuration is broken.
    const storage = readStorageConfig(environment);
    const now = dependencies.now ?? (() => new Date());
    const cutoff = new Date(now().getTime() - identity.staleQueuedMinutes * 60_000);
    const repository = dependencies.repository?.(storage) ?? new SupabaseScanRepository(createAdminClient(storage), now);
    const scan = await repository.recoverStaleQueuedScan(ownerId, cutoff);
    return Response.json({ data: { recovered: Boolean(scan), scan: scan ? { id: scan.id, status: scan.status } : null } },
      { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    return Response.json({ error: error instanceof ScanRequestError ? error.message : "The queued scan could not be checked. Please refresh scan status." },
      { status: error instanceof ScanRequestError ? error.status : 503, headers: { "Cache-Control": "no-store" } });
  }
}
