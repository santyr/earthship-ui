(function (data) {
  return JSON.stringify({
    version: 1,
    field: 'pv.output_power_w',
    observedAt: Date.now(),
    value: String(data),
  });
})(input);
