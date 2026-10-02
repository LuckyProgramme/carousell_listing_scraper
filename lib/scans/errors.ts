import "server-only";

export class ScanRequestError extends Error {
  constructor(message: string, readonly status: number) { super(message); }
}
