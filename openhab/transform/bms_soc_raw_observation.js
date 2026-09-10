(function (data) {
  return JSON.stringify({
    version: 1,
    field: 'raw',
    observedAt: Date.now(),
    value: String(data),
  });
})(input);
