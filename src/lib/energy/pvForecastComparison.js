export function pvForecastComparison(actualKwh, predictedKwh) {
  if (predictedKwh === null) return 'morning forecast unavailable';
  const amount = `${predictedKwh.toFixed(1)} kWh morning forecast`;
  return actualKwh !== null && actualKwh > predictedKwh
    ? `above ${amount}` : `of ${amount}`;
}
