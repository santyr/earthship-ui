"""Optional raw rain-counter capture for the existing Flask weather receiver.

This provides only volatile, localhost-only evidence. It does not write an
OpenHAB Item, persist history, or activate precipitation learning.
"""
from copy import deepcopy
from datetime import datetime, timezone
import math
import os
from threading import RLock
import time
from uuid import uuid4

from weather_rain_evidence import RainPolicy, rain_counter_receipt


# Temporary, bounded source diagnosis. Stops automatically after one day.
ANOMALY_DIAGNOSTIC_UNTIL = datetime(2026, 9, 30, 6, tzinfo=timezone.utc)


def _one(packet, key):
    if hasattr(packet, 'getlist'):
        values = packet.getlist(key)
        return values[0] if len(values) == 1 else None
    return packet.get(key)


def _metadata(packet):
    result = {'model': _one(packet, 'model')}
    for key, lower, upper in (('tempf', -60, 160), ('humidity', 0, 100),
                              ('solarradiation', 0, 1500), ('winddir', 0, 360),
                              ('windspeedmph', 0, 150), ('windgustmph', 0, 200),
                              ('uv', 0, 20)):
        raw = _one(packet, key)
        try:
            value = float(raw)
        except (TypeError, ValueError, OverflowError):
            value = None
        result[key] = value if value is not None and math.isfinite(value) and lower <= value <= upper else None
    battery = _one(packet, 'battery_ok')
    if isinstance(battery, str):
        battery = {'true': True, 'false': False, '1': True,
                   '0': False}.get(battery.lower())
    result['battery_ok'] = battery if type(battery) is bool else None
    return result


def _diagnostic(current, previous, delta, sensor_id):
    report = {'sensor_id': sensor_id, 'model': current['model'],
              'previous_model': previous.get('model'),
              'rain_delta_in': round(delta, 3)}
    for key in ('tempf', 'humidity', 'solarradiation', 'winddir',
                'windspeedmph', 'windgustmph', 'uv'):
        before, after = previous.get(key), current.get(key)
        report[key + '_delta'] = (round(after - before, 2)
                                  if before is not None and after is not None else None)
    before, after = previous.get('battery_ok'), current.get('battery_ok')
    report['battery_flip'] = (before != after if before is not None and after is not None else None)
    return report


class RainCollector:
    def __init__(self, policy, *, clock=None, monotonic=None, process_id=None,
                 on_jump=None):
        if not isinstance(policy, RainPolicy):
            raise ValueError('explicit rain policy required')
        self.policy = policy
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.monotonic = monotonic or time.monotonic
        self.process_id = process_id or os.getpid
        self.on_jump = on_jump
        self.lock = RLock()
        self.clear()

    def clear(self):
        with self.lock:
            self.epoch = str(uuid4())
            self.pid = self.process_id()
            self.record = None
            self.received_tick = None
            self.last_at = None
            self.last_tick = None
            self.packet_count = 0
            self.invalid_packets = 0
            self.counter_drops = 0
            self.counter_jumps = 0
            self.last_valid_counter = None
            self.last_good_metadata = None
            self.logged_spikes = set()

    def _now(self):
        if self.pid != self.process_id():
            self.clear()
        at, tick = self.clock(), self.monotonic()
        if (not isinstance(at, datetime) or at.tzinfo is None
                or at.utcoffset() is None or type(tick) not in (int, float)
                or not math.isfinite(tick)):
            raise ValueError('aware clock and finite monotonic tick required')
        at = at.astimezone(timezone.utc)
        if (self.last_at is not None and at < self.last_at) or (
                self.last_tick is not None and tick < self.last_tick):
            self.clear()
        self.last_at, self.last_tick = at, tick
        return at, tick

    def observe(self, packet):
        with self.lock:
            at, tick = self._now()
            record = rain_counter_receipt(packet, policy=self.policy,
                                          stream_epoch=self.epoch, received_at=at)
            if record is not None:
                self.packet_count += 1
                if record['status'] != 'valid':
                    self.invalid_packets += 1
                else:
                    value = record['totalRainIn']
                    if self.last_valid_counter is not None:
                        delta = value - self.last_valid_counter
                        if delta < 0:
                            self.counter_drops += 1
                        elif delta > 0.5:
                            self.counter_jumps += 1
                            self.invalid_packets += 1
                            # Match the existing weather app's physical jump
                            # guard: a rejected spike cannot become the next
                            # baseline or a qualified source observation.
                            record = {**record, 'status': 'invalid',
                                      'reason': 'counter_jump',
                                      'receivedAt': None, 'validUntil': None,
                                      'totalRainIn': None}
                            if (self.on_jump is not None and at < ANOMALY_DIAGNOSTIC_UNTIL
                                    and value not in self.logged_spikes
                                    and len(self.logged_spikes) < 8):
                                self.logged_spikes.add(value)
                                try:
                                    self.on_jump(_diagnostic(
                                        _metadata(packet), self.last_good_metadata or {},
                                        delta, self.policy.sensor_id))
                                except Exception:
                                    pass  # Diagnostics cannot affect acquisition.
                    if record['status'] == 'valid':
                        self.last_valid_counter = value
                        self.last_good_metadata = _metadata(packet)
                self.record = record
                self.received_tick = tick

    def snapshot(self):
        with self.lock:
            at, tick = self._now()
            record = self.record
            if record is not None and record['status'] == 'valid':
                deadline = datetime.fromisoformat(record['validUntil'])
                if (at >= deadline or tick - self.received_tick
                        >= self.policy.validity_seconds):
                    record = {**record, 'status': 'invalid', 'reason': 'expired',
                              'recordedAt': at.isoformat(), 'receivedAt': None,
                              'validUntil': None, 'totalRainIn': None}
                    self.record = record
            return {'version': 1, 'streamEpoch': self.epoch,
                    'record': deepcopy(record), 'packetCount': self.packet_count,
                    'invalidPackets': self.invalid_packets,
                    'counterDrops': self.counter_drops,
                    'counterJumps': self.counter_jumps}


def install_rain_evidence(app, *, enabled=False, policy=None, clock=None,
                          monotonic=None, process_id=None):
    """Add a localhost-only endpoint only when literally enabled.

    Capture errors clear the volatile record; the legacy /weather handler
    always runs normally. Call this before serving requests.
    """
    if enabled is not True:
        return None
    from flask import jsonify, request
    if ('rain_counter_evidence' in app.view_functions or
            any(rule.rule == '/rain_evidence' for rule in app.url_map.iter_rules())):
        raise ValueError('rain evidence already installed')
    collector = RainCollector(policy, clock=clock, monotonic=monotonic,
                              process_id=process_id,
                              on_jump=lambda report: app.logger.warning(
                                  'rain source anomaly metadata %s', report))

    @app.before_request
    def capture_rain_receipt():
        if (request.method == 'GET' and request.path == '/weather'
                and request.remote_addr in {'127.0.0.1', '::1'}):
            try:
                collector.observe(request.args)
            except Exception:
                collector.clear()
                app.logger.warning('rain evidence capture unavailable')
        return None

    def evidence_response():
        if request.remote_addr not in {'127.0.0.1', '::1'}:
            return '', 404
        try:
            response = jsonify(collector.snapshot())
        except Exception:
            collector.clear()
            response = jsonify({'error': 'rain evidence unavailable'})
            response.status_code = 503
        response.headers['Cache-Control'] = 'no-store'
        return response

    app.add_url_rule('/rain_evidence', 'rain_counter_evidence',
                     evidence_response, methods=['GET'])
    return collector
