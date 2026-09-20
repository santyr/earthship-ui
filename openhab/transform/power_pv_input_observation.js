(function (data) {
  return JSON.stringify({
    version: 1,
    field: 'pv.input_power_w',
    observedAt: Date.now(),
    value: String(data),
  });
})(input);
