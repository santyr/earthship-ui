// Acquisition-adjacent receipt from the TP-Link switch channel. The timestamp
// is this host's transform time, not a device clock or a health assertion.
(function (data) {
  return JSON.stringify({
    version: 1,
    observedAt: Date.now(),
    value: String(data),
  });
})(input);
