import { vi } from "vitest";

export const ownerId = "749743db-c366-47c9-9373-bec966857b32";
export const scanId = "11111111-1111-4111-8111-111111111111";
export const otherOwnerId = "22222222-2222-4222-8222-222222222222";
export const env = {
  NEXT_PUBLIC_SUPABASE_URL: "https://example.supabase.co",
  NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: "sb_publishable_test_only",
  SUPABASE_SECRET_KEY: "sb_secret_test_only",
  ALLOWED_USER_EMAIL: "dealfinder0322@gmail.com",
  FRONTEND_ORIGIN: "https://dealfinder.example",
  GITHUB_REPOSITORY: "LuckyProgramme/carousell_listing_scraper",
  GITHUB_WORKFLOW_FILE: "scan.yml",
  GITHUB_WORKFLOW_REF: "main",
  GITHUB_ACTIONS_TOKEN: "github_test_token_only",
  STALE_QUEUED_SCAN_MINUTES: "15",
  VERCEL_ENV: "production",
};

export function configureEnv(overrides: Record<string, string> = {}) {
  for (const [key, value] of Object.entries({ ...env, ...overrides })) vi.stubEnv(key, value);
}

export function scanRequest(path = "/api/scan", origin: string | null = env.FRONTEND_ORIGIN) {
  return new Request(`${env.FRONTEND_ORIGIN}${path}`, {
    method: "POST",
    headers: origin ? { Origin: origin, "Sec-Fetch-Site": "same-origin" } : {},
  });
}

export function row(status = "queued", owner = ownerId) {
  return { id: scanId, owner_id: owner, status };
}

export function jsonResponse(body: unknown, status = 200) {
  return Response.json(body, { status });
}
