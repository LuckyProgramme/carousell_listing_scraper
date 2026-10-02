import { describe, expect, it } from "vitest";
import { readIdentityConfig, readStartConfig, readStorageConfig, ScanConfigurationError } from "@/lib/scans/config";
import { env } from "./fixtures";

describe("runtime scan configuration", () => {
  it("validates full start settings with a 15-minute queue threshold", () => {
    const config = readStartConfig(env);
    expect(config.staleQueuedMinutes).toBe(15);
    expect(config.github.repository).toBe(env.GITHUB_REPOSITORY);
    expect(config.origin).toBe(env.FRONTEND_ORIGIN);
  });
  it("allows storage/recovery config without a GitHub token", () => {
    expect(readStorageConfig({ ...env, GITHUB_ACTIONS_TOKEN: "" }).url).toBe(env.NEXT_PUBLIC_SUPABASE_URL);
  });
  it.each(["GITHUB_ACTIONS_TOKEN", "GITHUB_REPOSITORY", "GITHUB_WORKFLOW_FILE", "GITHUB_WORKFLOW_REF", "SUPABASE_SECRET_KEY", "ALLOWED_USER_EMAIL", "FRONTEND_ORIGIN"])("requires %s before starting", (key) => {
    expect(() => readStartConfig({ ...env, [key]: "" })).toThrow(ScanConfigurationError);
  });
  it.each(["4", "1441", "15.5", "NaN"])("rejects invalid recovery threshold %s", (value) => {
    expect(() => readIdentityConfig({ ...env, STALE_QUEUED_SCAN_MINUTES: value })).toThrow(ScanConfigurationError);
  });
  it.each(["http://example.supabase.co", "https://user:pass@example.supabase.co", "https://example.supabase.co/?key=private"])("rejects unsafe project URLs %s", (url) => {
    expect(() => readStorageConfig({ ...env, NEXT_PUBLIC_SUPABASE_URL: url })).toThrow(ScanConfigurationError);
  });
  it("rejects publishable credentials for privileged storage without echoing them", () => {
    expect(() => readStorageConfig({ ...env, SUPABASE_SECRET_KEY: "sb_publishable_private_example" })).toThrow(ScanConfigurationError);
    try { readStorageConfig({ ...env, SUPABASE_SECRET_KEY: "sb_publishable_private_example" }); }
    catch (error) { expect(String(error)).not.toContain("private_example"); }
  });
  it.each(["https://dealfinder.example/path", "https://evil@dealfinder.example", "http://dealfinder.example", "https://dealfinder.example?q=1"])("rejects unsafe production origins %s", (origin) => {
    expect(() => readIdentityConfig({ ...env, FRONTEND_ORIGIN: origin })).toThrow(ScanConfigurationError);
  });
  it.each(["owner/../repo", "owner/repo/extra"])("rejects invalid repository paths %s", (repository) => {
    expect(() => readStartConfig({ ...env, GITHUB_REPOSITORY: repository })).toThrow(ScanConfigurationError);
  });
  it("allows explicitly configured localhost only outside Vercel production", () => {
    expect(readIdentityConfig({ ...env, VERCEL_ENV: "", FRONTEND_ORIGIN: "http://localhost:3000" }).origin).toBe("http://localhost:3000");
    expect(() => readIdentityConfig({ ...env, FRONTEND_ORIGIN: "http://localhost:3000" })).toThrow();
  });
});
