import "server-only";

export function boundedFetch(transport: typeof fetch, timeoutMs: number): typeof fetch {
  return (input, init) => {
    const timeout = AbortSignal.timeout(timeoutMs);
    const callerSignal = init?.signal ?? (input instanceof Request ? input.signal : undefined);
    const signal = callerSignal ? AbortSignal.any([callerSignal, timeout]) : timeout;
    return transport(input, { ...init, signal, redirect: "error", cache: "no-store" });
  };
}
