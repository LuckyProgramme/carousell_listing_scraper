import "server-only";
import { createAdminClient } from "@/lib/supabase/admin";
import { authenticateScan, guardScanRequest } from "./auth";
import { readIdentityConfig, readStartConfig, type ScanEnvironment, type StartConfig } from "./config";
import { ScanRequestError } from "./errors";
import { dispatchScan, type DispatchOutcome } from "./github";
import { SupabaseScanRepository, type ScanRecord, type ScanRepository } from "./repository";

interface StartDependencies {
  environment?: ScanEnvironment;
  authenticate?: typeof authenticateScan;
  repository?: (config: StartConfig) => ScanRepository;
  dispatch?: (config: StartConfig["github"], scanId: string) => Promise<DispatchOutcome>;
}
const dispatchFailure = "The scan could not be started. Please check the scanner setup before trying again.";
const uncertainNotice = "Startup could not be confirmed. Check scan progress before trying again; release the queue only if it remains stuck.";

function accepted(scan: ScanRecord, notice?: string): Response {
  return Response.json({ data: { scan: { id: scan.id, status: scan.status }, ...(notice ? { notice } : {}) } },
    { status: 202, headers: { "Cache-Control": "no-store" } });
}

export async function startScan(request: Request, dependencies: StartDependencies = {}): Promise<Response> {
  try {
    const environment = dependencies.environment ?? process.env;
    // Fail closed even if a preview is deliberately missing production secrets.
    if (environment.VERCEL_ENV && environment.VERCEL_ENV !== "production") {
      throw new ScanRequestError("Scanning is disabled on this deployment.", 403);
    }
    const identity = readIdentityConfig(environment);
    guardScanRequest(request, identity, environment);
    const ownerId = await (dependencies.authenticate ?? authenticateScan)(identity);
    const config = readStartConfig(environment);
    const repository = dependencies.repository?.(config) ?? new SupabaseScanRepository(createAdminClient(config.storage));
    const scan = await repository.createQueuedScan(ownerId);
    const outcome = await (dependencies.dispatch ?? dispatchScan)(config.github, scan.id);
    if (outcome === "accepted") return accepted(scan);
    if (outcome === "ambiguous") return accepted(scan, uncertainNotice);
    let failed: ScanRecord | null;
    try {
      failed = await repository.failQueuedScan(scan.id, ownerId, dispatchFailure);
    } catch {
      return accepted(scan, uncertainNotice);
    }
    if (!failed) return accepted(scan, "The scan state changed while startup was being checked. Refresh progress before trying again.");
    throw new ScanRequestError(dispatchFailure, 503);
  } catch (error) {
    return Response.json({ error: error instanceof ScanRequestError ? error.message : "The scanner is temporarily unavailable." },
      { status: error instanceof ScanRequestError ? error.status : 503, headers: { "Cache-Control": "no-store" } });
  }
}
