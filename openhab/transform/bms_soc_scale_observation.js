(function (data) {
  return JSON.stringify({
    version: 1,
    field: 'scale',
    observedAt: Date.now(),
    value: String(data),
  });
})(input);
