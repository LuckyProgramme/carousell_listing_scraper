type ScanAction = "start" | "recover";
interface ActionDependencies {
  fetch?: typeof fetch;
  refresh: () => Promise<boolean>;
  setBusy: (busy: boolean) => void;
  setNotice: (notice: string) => void;
  setRefreshRequired: (required: boolean) => void;
}

function object(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
}
function message(value: unknown): string | null {
  return typeof value === "string" && value.trim() && value.length <= 1000 ? value : null;
}
function scan(value: unknown): Record<string, unknown> | null {
  const row = object(value);
  return row && typeof row.id === "string" && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(row.id)
    && ["queued", "scanning", "evaluating", "saving", "completed", "failed"].includes(String(row.status)) ? row : null;
}

export async function performScanAction(action: ScanAction, dependencies: ActionDependencies): Promise<void> {
  const uncertain = action === "start"
    ? "Startup could not be confirmed. Check scan progress before trying again."
    : "The queued scan could not be checked. Refresh scan status before trying again.";
  dependencies.setBusy(true);
  dependencies.setRefreshRequired(true);
  dependencies.setNotice("");
  try {
    const response = await (dependencies.fetch ?? fetch)(action === "start" ? "/api/scan" : "/api/scan/recover", {
      method: "POST", cache: "no-store", signal: AbortSignal.timeout(30_000),
    });
    const payload = object(await response.json());
    if (!response.ok) {
      dependencies.setNotice(message(payload?.error) ?? uncertain);
    } else {
      const data = object(payload?.data);
      if (action === "start") {
        if (!scan(data?.scan)) throw new Error("Invalid scan response");
        dependencies.setNotice(message(data?.notice) ?? "Your scan was queued successfully.");
      } else {
        if (typeof data?.recovered !== "boolean" || (data.recovered ? scan(data.scan)?.status !== "failed" : data.scan !== null)) {
          throw new Error("Invalid recovery response");
        }
        dependencies.setNotice(data.recovered
          ? "The stuck queued scan was released. You can try Scan Now again."
          : "This queued scan is still recent or has already started. No changes were made.");
      }
    }
  } catch {
    dependencies.setNotice(uncertain);
  } finally {
    // Even an error/timeout can follow a committed write. Never retry the POST.
    try {
      dependencies.setRefreshRequired(!await dependencies.refresh());
    } catch {
      dependencies.setRefreshRequired(true);
    } finally {
      dependencies.setBusy(false);
    }
  }
}
