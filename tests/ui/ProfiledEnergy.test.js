// @vitest-environment jsdom
import { cleanup, render, waitFor, fireEvent } from '@testing-library/svelte';
import { afterEach, expect, it, vi } from 'vitest';
vi.mock('svelte', async () => import('../../node_modules/svelte/src/index-client.js'));
import ProfiledEnergy from '../../src/lib/ui/ProfiledEnergy.svelte';
import { profiledObservation, profiledPerformance, PROFILE_NOW } from '../fixtures/household-profiled-energy.js';
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
function serve(view = profiledObservation(), report = profiledPerformance(), at = PROFILE_NOW) {
  vi.spyOn(Date, 'now').mockReturnValue(at);
  vi.stubGlobal('fetch', async url => new Response(JSON.stringify(url === '/api/household-profiled-energy-observation' ? view : report)));
}
it('shows learned load alongside the original constant assumption and matched errors', async () => {
  serve(); const { container, getByLabelText } = render(ProfiledEnergy);
  await waitFor(() => expect(container.textContent).toContain('9.60 kWh'));
  expect(container.textContent).toContain('500 W'); expect(container.textContent).toContain('400 W');
  expect(container.textContent).toContain('Training data through'); expect(container.textContent).toContain('0.050');
  expect(container.textContent).toContain('Collecting'); expect(container.textContent).toContain('Constant power'); expect(container.textContent).toContain('Hold SoC'); expect(container.querySelectorAll('svg[aria-label]')).toHaveLength(2);
  await fireEvent.input(getByLabelText('Demand forecast hour'), { target: { value: '6' } });
  expect(container.textContent).toContain('Hour 6'); expect(container.querySelector('form')).toBeNull();
});
it('labels old forecasts and reports stale without changing the original source dates', async () => {
  serve(profiledObservation(), profiledPerformance(), PROFILE_NOW + 40 * 60000); const { container } = render(ProfiledEnergy);
  await waitFor(() => expect(container.textContent).toContain('Demand forecast is stale'));
  expect(container.textContent).toContain('Demand accuracy report is stale');
});
it('withholds a different algorithm cohort rather than mixing its errors', async () => {
  const report = profiledPerformance(); report.cohort_id = 'f'.repeat(64); serve(profiledObservation(), report);
  const { container } = render(ProfiledEnergy);
  await waitFor(() => expect(container.textContent).toContain('Collecting comparisons for this model'));
  expect(container.textContent).not.toContain('0.050');
});
it('displays calibrated PV and learned-load storage without reusing original accuracy scores', async () => {
 const { calibratedEnergy } = await import('../fixtures/calibrated-energy.js');
 const v=calibratedEnergy();vi.spyOn(Date,'now').mockReturnValue(PROFILE_NOW);
 vi.stubGlobal('fetch', async url=>new Response(JSON.stringify(url==='/api/household-calibrated-energy-observation'?v:url==='/api/household-profiled-energy-observation'?profiledObservation():profiledPerformance())));
 const { container }=render(ProfiledEnergy);
 await waitFor(()=>expect(container.textContent).toContain('14.00 kWh'));
 expect(container.textContent).toContain('20.00 kWh');expect(container.textContent).toContain('6.40 kWh');expect(container.textContent).toContain('9.60 kWh');
 expect(container.querySelector('svg[aria-label="Battery SoC with calibrated and uncalibrated PV"]')).not.toBeNull();
 expect(container.textContent).not.toContain('0.050');expect(container.textContent).toContain('Calibrated scenario accuracy is collecting');
});

it.each([true,false])('shows accuracy only for the same numerical model and policy (matching=%s)',async matching=>{
 const {calibratedEnergy,calibratedPerformance,CALIBRATED_NOW}=await import('../fixtures/calibrated-energy.js');
 const v=calibratedEnergy(),r=calibratedPerformance();v.schema='earthship-household-calibrated-energy-observation/v3';v.calibration_policy_sha256='b'.repeat(64);
 r.schema='earthship-household-calibrated-energy-performance/v2';r.calibration_policy_sha256=(matching?'b':'c').repeat(64);
 vi.spyOn(Date,'now').mockReturnValue(CALIBRATED_NOW);
 vi.stubGlobal('fetch',async url=>new Response(JSON.stringify(url==='/api/household-calibrated-energy-observation'?v:url==='/api/household-calibrated-energy-performance'?r:url==='/api/household-profiled-energy-observation'?profiledObservation():profiledPerformance())));
 const {container}=render(ProfiledEnergy);await waitFor(()=>expect(container.textContent).toContain('14.00 kWh'));
 if(matching)expect(container.querySelector('table')).not.toBeNull();
 else expect(container.textContent).toContain('Calibrated scenario accuracy is collecting');
});

it.each([true,false])('shows the component model and matches its procedure (matching=%s)',async matching=>{
 const {componentEnergy,componentPerformance,CALIBRATED_NOW}=await import('../fixtures/calibrated-energy.js');
 const v=componentEnergy(),r=componentPerformance();if(!matching)r.procedure_sha256='c'.repeat(64);
 vi.spyOn(Date,'now').mockReturnValue(CALIBRATED_NOW);
 vi.stubGlobal('fetch',async url=>new Response(JSON.stringify(url==='/api/household-calibrated-energy-observation'?v:url==='/api/household-calibrated-energy-performance'?r:url==='/api/household-profiled-energy-observation'?profiledObservation():profiledPerformance())));
 const {container}=render(ProfiledEnergy);await waitFor(()=>expect(container.textContent).toContain('14.00 kWh'));
 expect(container.textContent).toContain('native solar components');expect(container.textContent).toContain('13 raw fallback source intervals');
 expect(container.textContent).toContain('Conditional nominal storage');
 if(matching)expect(container.querySelector('table')).not.toBeNull();
 else expect(container.textContent).toContain('Calibrated scenario accuracy is collecting');
});
