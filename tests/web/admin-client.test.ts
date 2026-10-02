import { describe, expect, it, vi } from "vitest";
import { createAdminClient } from "@/lib/supabase/admin";
import { readStorageConfig } from "@/lib/scans/config";
import { boundedFetch } from "@/lib/scans/http";
import { env, jsonResponse } from "./fixtures";
import * as sdk from "@supabase/supabase-js";
vi.mock("@supabase/supabase-js", { spy: true });

describe("server-only client boundary", () => {
  it("creates no browser session and makes no request during construction", async () => {
    const create = vi.mocked(sdk.createClient);
    const client = createAdminClient(readStorageConfig(env));
    expect(create).toHaveBeenCalledWith(env.NEXT_PUBLIC_SUPABASE_URL, env.SUPABASE_SECRET_KEY, expect.objectContaining({
      auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false },
      db: { retry: false },
    }));
    expect((await client.auth.getSession()).data.session).toBeNull();
    expect(fetch).not.toHaveBeenCalled();
  });
  it("bounds fetch and refuses redirects while respecting a caller abort", async () => {
    const controller = new AbortController();
    const transport = vi.fn().mockResolvedValue(jsonResponse([]));
    await boundedFetch(transport, 1000)("https://example.supabase.co", { signal: controller.signal });
    const options = transport.mock.lastCall![1];
    expect(options.redirect).toBe("error");
    expect(options.cache).toBe("no-store");
    controller.abort();
    expect(options.signal.aborted).toBe(true);
  });
  it("abort timeout reaches the actual transport", async () => {
    const transport = vi.fn((_url, init) => new Promise<Response>((_resolve, reject) => {
      init.signal.addEventListener("abort", () => reject(new Error("aborted")));
    }));
    await expect(boundedFetch(transport, 10)("https://example.supabase.co")).rejects.toThrow("aborted");
    expect(transport).toHaveBeenCalledOnce();
  });
  it("test harness rejects unintended network access", async () => {
    expect(() => fetch("https://real-service.example")).toThrow("blocked");
  });
});
