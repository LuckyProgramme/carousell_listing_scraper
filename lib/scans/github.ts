import "server-only";
import type { GithubConfig } from "./config";
import { boundedFetch } from "./http";
import { assertUuid } from "./repository";

export type DispatchOutcome = "accepted" | "rejected" | "ambiguous";
const refusalStatuses = new Set([400, 401, 403, 404, 422, 429]);

export async function dispatchScan(
  config: GithubConfig,
  scanId: string,
  transport: typeof fetch = fetch,
  timeoutMs = 10_000,
): Promise<DispatchOutcome> {
  assertUuid(scanId);
  const [owner, repo] = config.repository.split("/");
  const url = `https://api.github.com/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/actions/workflows/${encodeURIComponent(config.workflow)}/dispatches`;
  try {
    const response = await boundedFetch(transport, timeoutMs)(url, {
      method: "POST",
      headers: {
        Accept: "application/vnd.github+json",
        Authorization: `Bearer ${config.token}`,
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2026-03-10",
      },
      body: JSON.stringify({ ref: config.ref, inputs: { scan_run_id: scanId } }),
    });
    if (refusalStatuses.has(response.status)) return "rejected";
    if (response.status !== 200) return "ambiguous";
    // Validate the documented acceptance envelope; do not store/use its run ID.
    const body: unknown = await response.json();
    if (!body || typeof body !== "object" || !("workflow_run_id" in body)
      || !Number.isSafeInteger(body.workflow_run_id) || Number(body.workflow_run_id) <= 0) return "ambiguous";
    return "accepted";
  } catch {
    // A lost response can mean GitHub accepted it. Never repeat this POST.
    return "ambiguous";
  }
}
