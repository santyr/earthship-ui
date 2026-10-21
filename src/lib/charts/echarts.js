import * as echarts from 'echarts/core';
import { BarChart, CandlestickChart, CustomChart, LineChart } from 'echarts/charts';
import {
  GridComponent,
  LegendComponent,
  MarkPointComponent,
  TooltipComponent,
} from 'echarts/components';
import { SVGRenderer } from 'echarts/renderers';

echarts.use([
  LineChart,
  BarChart,
  CandlestickChart,
  CustomChart,
  GridComponent,
  LegendComponent,
  MarkPointComponent,
  TooltipComponent,
  SVGRenderer,
]);

export { echarts };
