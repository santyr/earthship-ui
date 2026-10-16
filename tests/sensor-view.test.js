import { describe,it,expect } from 'vitest';
import { sensorView, counts } from '../src/lib/sensors/view.js';
const NOW=Date.parse('2026-10-13T18:00:00Z');
import {fixture} from './fixtures/sensorView.js';
describe('qualified sensor presentation',()=>{
 it('counts only current evidence and keeps last-known contact after expiry',()=>{
  const raw=JSON.stringify(fixture());const view=sensorView(raw,NOW,'live');
  expect(counts(view.sensors)).toMatchObject({windows:3,skylights:2,doors:3,closed:7,unknown:0});
  const stale=sensorView(raw,NOW+46000,'live');
  expect(counts(stale.sensors).closed).toBe(0);expect(counts(stale.sensors).unknown).toBe(15);
  expect(stale.sensors[0].contact_state).toBe('OPEN');
 });
 it('invalidates data when the OpenHAB stream is offline',()=>{
  expect(counts(sensorView(JSON.stringify(fixture()),NOW,'offline').sensors).unknown).toBe(15);
 });
 it('rejects malformed future and oversized source views',()=>{
  expect(sensorView('UNDEF',NOW,'live').available).toBe(false);
  const v=fixture();v.generated_at=new Date(NOW+1).toISOString();expect(sensorView(JSON.stringify(v),NOW,'live').available).toBe(false);
  v.generated_at=new Date(NOW).toISOString();v.sensors[0].current_state='BANANA';expect(sensorView(JSON.stringify(v),NOW,'live').available).toBe(false);
 });
});
