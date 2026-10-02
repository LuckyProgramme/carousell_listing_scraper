import { startScan } from "@/lib/scans/service";

export const runtime = "nodejs";

export async function POST(request: Request) {
  return startScan(request);
}
