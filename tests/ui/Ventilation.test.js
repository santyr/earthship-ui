// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import {render,screen,cleanup,fireEvent} from '@testing-library/svelte';
import {afterEach,it,expect,vi} from 'vitest';
vi.mock('svelte',async()=>import('../../node_modules/svelte/src/index-client.js'));
import {items,connection} from '../../src/lib/openhab/index.js';
import Ventilation from '../../src/screens/Ventilation.svelte';
import {fixture} from '../fixtures/sensorView.js';
afterEach(()=>{cleanup();vi.useRealTimers();items.set({});connection.set('offline');});
it('renders fifteen independent devices and updates through the shared Item store',async()=>{
 vi.useFakeTimers();vi.setSystemTime(Date.parse('2026-10-13T18:00:00Z'));connection.set('live');
 const value=fixture();items.set({Earthship_Sensor_Service:'online',Earthship_Sensor_View_JSON:JSON.stringify(value)});
 const {container}=render(Ventilation);expect(container.querySelectorAll('[data-sensor]')).toHaveLength(15);
 expect(screen.getByText('Synthetic demonstration')).toBeInTheDocument();
 const {tick}=await import('../../node_modules/svelte/src/index-client.js');
 value.sensors[0].current_state='CLOSED';value.sensors[0].contact_state='CLOSED';
 items.set({Earthship_Sensor_Service:'online',Earthship_Sensor_View_JSON:JSON.stringify(value)});await tick();
 expect(container.querySelector('[data-sensor="opening_1"]')).toHaveTextContent('Closed');
 vi.advanceTimersByTime(46000);await tick();
 expect(container.querySelector('[data-sensor="opening_1"]')).toHaveTextContent('Unknown');
 expect(container.querySelector('[data-sensor="opening_1"]')).toHaveTextContent('Last known closed');
});
it('has an explicit empty commissioning state without inventing assignments',()=>{
 items.set({});connection.set('live');render(Ventilation);
 expect(screen.getByText('Awaiting sensor commissioning')).toBeInTheDocument();
});
it('opens device diagnostics without issuing a control request',async()=>{
 vi.useFakeTimers();vi.setSystemTime(Date.parse('2026-10-13T18:00:00Z'));connection.set('live');
 const value=fixture();value.sensors[0].rssi=-90;value.sensors[0].snr=5;
 items.set({Earthship_Sensor_Service:'online',Earthship_Sensor_View_JSON:JSON.stringify(value)});
 render(Ventilation);await fireEvent.click(screen.getByRole('button',{name:'Details for Opening 1'}));
 expect(screen.getByRole('dialog',{name:'Details for Opening 1'})).toBeInTheDocument();
 expect(screen.getByText('-90 dBm')).toBeInTheDocument();
 await fireEvent.click(screen.getByRole('button',{name:'Close'}));
 expect(screen.queryByRole('dialog')).toBeNull();
});
