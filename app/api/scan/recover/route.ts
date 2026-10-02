import { recoverQueuedScan } from "@/lib/scans/recovery";

export const runtime = "nodejs";

export async function POST(request: Request): Promise<Response> {
  return recoverQueuedScan(request);
}
