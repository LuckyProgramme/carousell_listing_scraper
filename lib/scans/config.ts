import "server-only";
import { ScanRequestError } from "./errors";

export type ScanEnvironment = Readonly<Record<string, string | undefined>>;
export class ScanConfigurationError extends ScanRequestError {
  constructor() { super("The scanner configuration is incomplete or invalid.", 503); }
}

export interface IdentityConfig {
  origin: string;
  allowedEmail: string;
  staleQueuedMinutes: number;
}
export interface StorageConfig {
  url: string;
  secretKey: string;
  timeoutMs: number;
}
export interface GithubConfig {
  repository: string;
  workflow: string;
  ref: string;
  token: string;
}
export interface StartConfig extends IdentityConfig {
  storage: StorageConfig;
  github: GithubConfig;
}

function required(env: ScanEnvironment, key: string): string {
  const value = env[key]?.trim();
  if (!value || /[\r\n]/.test(value)) throw new ScanConfigurationError();
  return value;
}

function originUrl(value: string): URL {
  try {
    const url = new URL(value);
    if (url.username || url.password || url.search || url.hash || url.pathname !== "/") throw new Error();
    return url;
  } catch { throw new ScanConfigurationError(); }
}

export function readIdentityConfig(env: ScanEnvironment = process.env): IdentityConfig {
  const url = originUrl(required(env, "FRONTEND_ORIGIN"));
  const local = env.VERCEL_ENV !== "production" && ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
  if (url.protocol !== "https:" && !(url.protocol === "http:" && local)) throw new ScanConfigurationError();
  const email = required(env, "ALLOWED_USER_EMAIL").toLowerCase();
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) throw new ScanConfigurationError();
  const minutes = Number(env.STALE_QUEUED_SCAN_MINUTES?.trim() || "15");
  if (!Number.isInteger(minutes) || minutes < 5 || minutes > 1440) throw new ScanConfigurationError();
  return { origin: url.origin, allowedEmail: email, staleQueuedMinutes: minutes };
}

export function readStorageConfig(env: ScanEnvironment = process.env): StorageConfig {
  const url = originUrl(required(env, "NEXT_PUBLIC_SUPABASE_URL"));
  const secretKey = required(env, "SUPABASE_SECRET_KEY");
  if (url.protocol !== "https:" || !secretKey.startsWith("sb_secret_")) throw new ScanConfigurationError();
  return { url: url.origin, secretKey, timeoutMs: 10_000 };
}

export function readStartConfig(env: ScanEnvironment = process.env): StartConfig {
  const identity = readIdentityConfig(env);
  const storage = readStorageConfig(env);
  const repository = required(env, "GITHUB_REPOSITORY");
  const workflow = required(env, "GITHUB_WORKFLOW_FILE");
  const ref = required(env, "GITHUB_WORKFLOW_REF");
  const token = required(env, "GITHUB_ACTIONS_TOKEN");
  if (!/^[A-Za-z0-9][A-Za-z0-9_.-]*\/[A-Za-z0-9][A-Za-z0-9_.-]*$/.test(repository)
    || !/^[A-Za-z0-9][A-Za-z0-9_.-]*\.ya?ml$/.test(workflow)
    || !/^[A-Za-z0-9][A-Za-z0-9_./-]*$/.test(ref)
    || ref.includes("..") || ref.includes("//") || ref.endsWith("/")) throw new ScanConfigurationError();
  return { ...identity, storage, github: { repository, workflow, ref, token } };
}
