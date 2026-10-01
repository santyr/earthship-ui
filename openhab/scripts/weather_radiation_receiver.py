"""Default-off, volatile, localhost-only radiation receipt capture."""
from copy import deepcopy
from datetime import datetime, timezone
import math
import os
from threading import RLock
import time
from uuid import uuid4

from weather_radiation_evidence import RadiationPolicy, invalid, radiation_receipt


class RadiationCollector:
    def __init__(self, policy, *, clock=None, monotonic=None, process_id=None):
        if not isinstance(policy, RadiationPolicy):
            raise ValueError('explicit radiation policy required')
        self.policy = policy
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.monotonic = monotonic or time.monotonic
        self.process_id = process_id or os.getpid
        self.lock = RLock()
        self.highwater = None
        self.fingerprint = None
        self.clear()

    def clear(self):
        with self.lock:
            self.epoch = str(uuid4())
            self.pid = self.process_id()
            self.record = None
            self.received_tick = None
            self.expires_tick = None
            self.last_at = self.last_tick = None
            self.sequence = 0
            # Preserve the source high-water mark across capture/clock faults:
            # an old HTTP replay cannot recover a previously invalidated value.

    def _now(self):
        if self.pid != self.process_id():
            self.clear()
        at, tick = self.clock(), self.monotonic()
        if (not isinstance(at, datetime) or at.tzinfo is None or at.utcoffset() is None
                or type(tick) not in (int, float) or not math.isfinite(tick)):
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
            record = radiation_receipt(packet, policy=self.policy,
                                       stream_epoch=self.epoch, received_at=at)
            if record is None:
                return
            if record['status'] == 'valid':
                source = record['radioDecodedAt']
                fingerprint = (record['lightLux'], record['irradianceWm2'])
                if self.highwater is not None and source < self.highwater:
                    record = invalid(record, 'source_time_regressed')
                elif source == self.highwater:
                    if fingerprint == self.fingerprint:
                        return  # Never renew expiry or recover a fault barrier.
                    record = invalid(record, 'source_time_conflict')
                else:
                    self.highwater, self.fingerprint = source, fingerprint
            elif (self.record is not None and self.record['reason'] == 'expired'
                  and record['reason'] == 'source_time_expired'
                  and record['radioDecodedAt'] == self.highwater):
                return
            self.sequence += 1
            self.record = {**record, 'sequence': self.sequence}
            self.received_tick = tick
            self.expires_tick = (tick + (datetime.fromisoformat(record['validUntil']) - at).total_seconds()
                                 if record['status'] == 'valid' else None)

    def snapshot(self):
        with self.lock:
            at, tick = self._now()
            if self.record is not None and self.record['status'] == 'valid':
                deadline = datetime.fromisoformat(self.record['validUntil'])
                if at >= deadline or tick >= self.expires_tick:
                    self.record = invalid(self.record, 'expired')
            return {'version': 1, 'streamEpoch': self.epoch, 'sequence': self.sequence,
                    'record': deepcopy(self.record)}


def install_radiation_evidence(app, *, enabled=False, policy=None, clock=None,
                                monotonic=None, process_id=None):
    if enabled is not True:
        return None
    from flask import jsonify, request
    if ('radiation_evidence' in app.view_functions or
            any(rule.rule == '/radiation_evidence' for rule in app.url_map.iter_rules())):
        raise ValueError('radiation evidence already installed')
    collector = RadiationCollector(policy, clock=clock, monotonic=monotonic,
                                    process_id=process_id)

    @app.before_request
    def capture_radiation():
        if (request.method == 'GET' and request.path == '/weather'
                and request.remote_addr in {'127.0.0.1', '::1'}):
            try:
                collector.observe(request.args)
            except Exception:
                collector.clear()
                app.logger.warning('radiation evidence capture unavailable')
        return None

    def evidence_response():
        if request.remote_addr not in {'127.0.0.1', '::1'}:
            return '', 404
        try:
            response = jsonify(collector.snapshot())
        except Exception:
            collector.clear()
            response = jsonify({'error': 'radiation evidence unavailable'})
            response.status_code = 503
        response.headers['Cache-Control'] = 'no-store'
        return response

    app.add_url_rule('/radiation_evidence', 'radiation_evidence', evidence_response,
                     methods=['GET'])
    return collector
