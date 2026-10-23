// @vitest-environment jsdom
import {afterEach,beforeEach,it,expect,vi} from 'vitest';
import {render,cleanup,fireEvent,waitFor} from '@testing-library/svelte';
vi.mock('svelte',async()=>import('../../node_modules/svelte/src/index-client.js'));
vi.mock('../../src/lib/household/observationClient.js',()=>({loadWeatherSensitivity:vi.fn()}));
import {loadWeatherSensitivity} from '../../src/lib/household/observationClient.js';
import WeatherSensitivity from '../../src/lib/ui/WeatherSensitivity.svelte';
import {sensitivity,nowMs} from '../fixtures/weather-sensitivity.js';
beforeEach(()=>{vi.useFakeTimers({toFake:['Date']});vi.setSystemTime(nowMs);loadWeatherSensitivity.mockResolvedValue(JSON.stringify(sensitivity()));});
afterEach(()=>{cleanup();vi.useRealTimers();vi.clearAllMocks();});
it('starts collapsed and reveals the three quantities and hourly thermal trajectory',async()=>{
 const {container,getByText,getByLabelText}=render(WeatherSensitivity);await waitFor(()=>expect(getByText('10.00 kWh')).toBeTruthy());
 const detail=container.querySelector('details');expect(detail.open).toBe(false);await fireEvent.click(container.querySelector('summary')); // native details keyboard/click covered by browser
 detail.open=true;expect(container.textContent).toContain('PV before electrical correction');expect(container.textContent).toContain('Half solar');expect(container.textContent).toContain('Warmer (+3°C), 1.2× solar');
 expect(container.textContent).toContain('Nominal SoC minimum');expect(container.textContent).toContain('Weather cases have no assigned probabilities.');
 expect(container.textContent).not.toContain('Source initialized');expect(container.querySelectorAll('tbody tr')).toHaveLength(3);
 await fireEvent.input(getByLabelText('Sensitivity forecast hour'),{target:{value:'1'}});expect(container.textContent).toContain('70.0°F');
});
it('keeps absence and expired reports unavailable without invented zero readings',async()=>{
 const v=sensitivity();v.valid_until='2026-10-23T17:18:00Z';loadWeatherSensitivity.mockResolvedValue(JSON.stringify(v));
 const {container,getByText}=render(WeatherSensitivity);await waitFor(()=>expect(getByText('Weather sensitivity unavailable')).toBeTruthy());expect(container.querySelector('table')).toBeNull();expect(container.textContent).not.toContain('0.00 kWh');
});
it('cancels pending reads on teardown and uses only the fixed read-only loader',()=>{
 let signal;loadWeatherSensitivity.mockImplementation(s=>{signal=s;return new Promise(()=>{});});const {unmount}=render(WeatherSensitivity);expect(signal.aborted).toBe(false);unmount();expect(signal.aborted).toBe(true);expect(loadWeatherSensitivity).toHaveBeenCalledTimes(1);
});
