// Explicit disposable component entrypoint. The retired app route stays retired.
import { mount } from 'svelte';
import '../../src/app.css';
import Ventilation from '../../src/screens/Ventilation.svelte';
import { initOpenhab, stopOpenhab } from '../../src/lib/openhab/index.js';
await initOpenhab({ openhabUrl: '', apiToken: '' });
mount(Ventilation, { target: document.getElementById('sensor-qualification') });
window.addEventListener('pagehide', stopOpenhab, { once: true });
