// Bound the entire GET (headers and response body), including transports that
// do not settle promptly on abort. This helper is never used to retry commands.
export const READ_TIMEOUT_MS = 15_000;

export async function withReadTimeout(read, { signal, timeoutMs = READ_TIMEOUT_MS } = {}) {
  const controller = new AbortController();
  const abort = () => controller.abort(signal.reason);
  if (signal?.aborted) abort();
  else signal?.addEventListener('abort', abort, { once: true });
  let rejectAbort;
  const aborted = new Promise((_, reject) => { rejectAbort = reject; });
  const onAbort = () => rejectAbort(controller.signal.reason ?? new DOMException('Read canceled', 'AbortError'));
  controller.signal.addEventListener('abort', onAbort, { once: true });
  const timer = setTimeout(() => controller.abort(new DOMException('Read timed out', 'TimeoutError')), timeoutMs);
  try {
    if (controller.signal.aborted) throw controller.signal.reason;
    return await Promise.race([read(controller.signal), aborted]);
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', abort);
    controller.signal.removeEventListener('abort', onAbort);
  }
}
