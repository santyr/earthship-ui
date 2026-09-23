// Acquisition-adjacent observation only. Preserve invalid source text for a
// downstream validator; do not interpret this as household-load authority.
(function (data) {
  return JSON.stringify({
    version: 1,
    field: 'inverter.ac_output_w',
    observedAt: Date.now(),
    value: String(data),
  });
})(input);
