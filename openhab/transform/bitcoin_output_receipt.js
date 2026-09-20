// Source-only: transform receipt time, not provider quote time or execution ID.
// Never copy raw stderr into persistence; it may contain sensitive details.
(function (data) {
  const receivedAt = Date.now();
  if (!Number.isSafeInteger(receivedAt) || receivedAt <= 0) throw new Error('invalid receipt clock');
  const raw = typeof data === 'string' ? data : '';
  const amount = /^[1-9][0-9]{0,15}$/.test(raw) && !raw.includes('\n') ? Number(raw) : NaN;
  const price = Number.isSafeInteger(amount) && String(amount) === raw && amount <= 9007199254740990 ? amount : null;
  return JSON.stringify({ version: 1, field: 'bitcoin.usd', receivedAt, price });
})(input);
