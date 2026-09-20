(function (data) {
  return JSON.stringify({
    version: 1,
    field: 'battery.dc_power_w',
    observedAt: Date.now(),
    value: String(data),
  });
})(input);
