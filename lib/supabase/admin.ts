import "server-only";
import { createClient } from "@supabase/supabase-js";
import type { StorageConfig } from "@/lib/scans/config";
import { boundedFetch } from "@/lib/scans/http";

// Construct lazily at request time: builds and browser imports never receive keys.
export function createAdminClient(config: StorageConfig, options: { fetch?: typeof fetch } = {}) {
  const transport = boundedFetch(options.fetch ?? fetch, config.timeoutMs);
  const privilegedFetch: typeof fetch = (input, init) => {
    const headers = new Headers(init?.headers);
    // Some SDK versions copy opaque API keys into Bearer. They are not JWTs.
    if (headers.get("authorization") === `Bearer ${config.secretKey}`) headers.delete("authorization");
    return transport(input, { ...init, headers });
  };
  return createClient(config.url, config.secretKey, {
    auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false },
    db: { retry: false },
    global: { fetch: privilegedFetch },
  });
}
