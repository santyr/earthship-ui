export function observeElementSize(element, onSize, {
  debounceMs = 100,
  minDeltaPx = 8,
  ResizeObserverImpl = globalThis.ResizeObserver,
} = {}) {
  if (!element || typeof onSize !== 'function' || typeof ResizeObserverImpl !== 'function') {
    return () => {};
  }
  let timer;
  let pending;
  let delivered;
  const observer = new ResizeObserverImpl((entries) => {
    const rect = entries[0]?.contentRect;
    if (!rect) return;
    pending = { width: rect.width, height: rect.height };
    clearTimeout(timer);
    timer = setTimeout(() => {
      const next = pending;
      pending = null;
      if (!next) return;
      if (delivered
        && Math.abs(next.width - delivered.width) < minDeltaPx
        && Math.abs(next.height - delivered.height) < minDeltaPx) return;
      delivered = next;
      onSize(next);
    }, debounceMs);
  });
  observer.observe(element);
  return () => {
    clearTimeout(timer);
    observer.disconnect();
  };
}
