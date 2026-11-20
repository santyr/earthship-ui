const { items, rules, triggers } = require('openhab');
const viewItem = 'Earthship_Sensor_View_JSON';
const serviceItem = 'Earthship_Sensor_Service';
const gatewayId = '0016c001f13c1808';

function publish(name, value) {
  const item = items.getItem('LoRaWAN_' + name);
  if (String(item.state) !== String(value)) item.postUpdate(String(value));
}

function sensorSummary(sensors) {
  if (!sensors.length) return 'No sensors enrolled';
  return sensors.slice().sort((a, b) => String(a.project || a.zone).localeCompare(String(b.project || b.zone)) ||
    a.name.localeCompare(b.name)).map(s => {
    const details = [s.health, 'Last uplink: ' + (s.last_received_at || 'never')];
    if (s.battery?.percent != null) details.push(s.battery.percent + '% battery');
    else if (s.battery?.volts != null) details.push(s.battery.volts + ' V');
    if (s.rssi != null) details.push('RSSI ' + s.rssi + ' dBm');
    if (s.snr != null) details.push('SNR ' + s.snr + ' dB');
    return (s.project || s.zone || 'Earthship') + ' / ' + s.name + ' — ' + details.join(' · ');
  }).join('\n');
}

rules.JSRule({
  id: 'lorawan_gateway_health',
  name: 'LoRaWAN gateway health',
  triggers: [triggers.ItemStateUpdateTrigger(viewItem), triggers.ItemStateChangeTrigger(serviceItem),
    triggers.GenericCronTrigger('0/10 * * * * ?')],
  execute: () => {
    let view;
    try { view = JSON.parse(items.getItem(viewItem).state); } catch (_) {}
    const now = Date.now();
    const fresh = items.getItem(serviceItem).state === 'online' && view?.environment === 'production' &&
      Date.parse(view.generated_at) <= now && now < Date.parse(view.expires_at);
    const gateway = fresh && view.gateways.find(g => g.gateway_id === gatewayId);
    publish('Gateway_Status', gateway?.health || 'UNKNOWN');
    const last = gateway?.last_stats_received_at;
    const lastItem = items.getItem('LoRaWAN_Last_Statistics');
    if (last && Date.parse(lastItem.state) !== Date.parse(last)) lastItem.postUpdate(last);
    const op = fresh && view.operations;
    publish('Pipeline', op ? 'ChirpStack HTTP: ' + op.chirpstack + ' · MQTT: ' +
      (op.mqtt_connected ? 'connected' : 'disconnected') + ' · Decode failures: ' + op.decode_failures +
      ' · Integration failures: ' + op.integration_failures : 'Observation unavailable');
    publish('Sensors', fresh ? sensorSummary(view.sensors) : 'Observation unavailable');
  },
});
