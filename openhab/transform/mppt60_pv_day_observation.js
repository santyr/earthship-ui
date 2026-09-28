// Acquisition-adjacent observation of the native MPPT daily PV Wh counter.
// Preserve the exact channel text. This host timestamp is not a device clock.
(function (data) {
  return JSON.stringify({
    version: 1,
    field: 'mppt60.pv_day_wh',
    observedAt: Date.now(),
    value: String(data),
  });
})(input);
