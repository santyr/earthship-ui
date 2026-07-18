let echartsPromise;

export function getEcharts() {
  echartsPromise ||= import('./echarts.js').then((module) => module.echarts);
  return echartsPromise;
}
