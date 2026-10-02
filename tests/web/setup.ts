import http from "node:http";
import https from "node:https";
import net from "node:net";
import { beforeEach, vi } from "vitest";

beforeEach(() => {
  // Vite may load .env before setup. Clear credentials rather than trusting it.
  for (const key of Object.keys(process.env)) {
    if (/^(SUPABASE_|NEXT_PUBLIC_SUPABASE_|GITHUB_|GEMINI_|CLOUD_RUN_|ALLOWED_USER_|FRONTEND_ORIGIN$|VERCEL_|STALE_QUEUED_)/.test(key)) {
      vi.stubEnv(key, "");
    }
  }
  const blocked = () => { throw new Error("Real network access is blocked in web tests."); };
  vi.stubGlobal("fetch", vi.fn(blocked));
  vi.spyOn(http, "request").mockImplementation(blocked);
  vi.spyOn(https, "request").mockImplementation(blocked);
  vi.spyOn(net.Socket.prototype, "connect").mockImplementation(blocked);
});
