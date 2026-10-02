import "server-only";
import { createClient } from "@/lib/supabase/server";
import type { IdentityConfig, ScanEnvironment } from "./config";
import { ScanRequestError } from "./errors";
import { boundedFetch } from "./http";

export function guardScanRequest(request: Request, config: IdentityConfig, env: ScanEnvironment): void {
  if (env.VERCEL_ENV && env.VERCEL_ENV !== "production") {
    throw new ScanRequestError("Scanning is disabled on this deployment.", 403);
  }
  const site = request.headers.get("sec-fetch-site");
  if (request.headers.get("origin") !== config.origin || (site && site !== "same-origin")) {
    throw new ScanRequestError("This request is not allowed.", 403);
  }
}

export async function authenticateScan(config: IdentityConfig): Promise<string> {
  try {
    const client = await createClient({ fetch: boundedFetch(fetch, 10_000) });
    const { data, error } = await client.auth.getUser();
    if (error && (error.status === undefined || error.status >= 500)) {
      throw new ScanRequestError("Sign-in verification is temporarily unavailable.", 503);
    }
    if (error || !data.user) throw new ScanRequestError("Please sign in again.", 401);
    if (data.user.email?.toLowerCase() !== config.allowedEmail) {
      throw new ScanRequestError("This account is not allowed.", 403);
    }
    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(data.user.id)) {
      throw new ScanRequestError("Please sign in again.", 401);
    }
    return data.user.id;
  } catch (error) {
    if (error instanceof ScanRequestError) throw error;
    throw new ScanRequestError("Sign-in verification is temporarily unavailable.", 503);
  }
}
