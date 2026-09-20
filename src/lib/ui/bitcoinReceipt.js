// Local output receipt only; never provider quote age or historical coverage.
export const BITCOIN_RECEIPT_MAX_AGE_MS = 90_000;

export function bitcoinReceiptState(raw, displayedPrice, now) {
  const unknown = { status: 'unknown', label: 'Feed unknown', detail: 'No valid local feed receipt. The displayed price may be retained.' };
  if (typeof raw !== 'string' || raw.length > 512 || !Number.isSafeInteger(now) || now <= 0 || now > 8640000000000000) return unknown;
  let receipt;
  try { receipt = JSON.parse(raw); } catch { return unknown; }
  if (!receipt || Array.isArray(receipt) ||
      Object.keys(receipt).sort().join(',') !== 'field,price,receivedAt,version' ||
      receipt.version !== 1 || receipt.field !== 'bitcoin.usd' ||
      !Number.isSafeInteger(receipt.receivedAt) || receipt.receivedAt <= 0 || receipt.receivedAt > now ||
      (receipt.price !== null && (!Number.isSafeInteger(receipt.price) || receipt.price <= 0 || receipt.price > 9007199254740990))) return unknown;
  if (now - receipt.receivedAt >= BITCOIN_RECEIPT_MAX_AGE_MS) {
    return { status: 'stale', label: 'Feed stale', detail: 'No local feed receipt within 90 seconds. The displayed price may be retained.' };
  }
  if (receipt.price === null) return { status: 'invalid', label: 'Feed error', detail: 'The latest local feed output was invalid. The displayed price may be retained.' };
  if (receipt.price !== displayedPrice) return { status: 'mismatch', label: 'Price syncing', detail: 'The displayed price does not match the latest local feed receipt.' };
  return { status: 'recent', label: '', detail: `Valid local feed output received at ${new Date(receipt.receivedAt).toISOString()}. This is not the provider quote timestamp.` };
}
