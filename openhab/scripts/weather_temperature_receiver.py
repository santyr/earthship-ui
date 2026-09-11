"""Optional Flask receipt collector. No persistence or learning activation."""
from copy import deepcopy
from datetime import datetime, timezone
import math
import os
import re
from threading import RLock
import time
from uuid import uuid4

from weather_temperature_evidence import TemperaturePolicy, temperature_receipt


class TemperatureCollector:
    def __init__(self, policies, *, clock=None, monotonic=None, process_id=None):
        if not isinstance(policies, dict) or not 1 <= len(policies) <= 3:
            raise ValueError('one to three explicit stream policies required')
        if any(not isinstance(k, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,31}', k)
               or not isinstance(v, TemperaturePolicy) for k, v in policies.items()):
            raise ValueError('invalid named stream policy')
        identities = {(p.model, p.sensor_id) for p in policies.values()}
        if len(identities) != len(policies):
            raise ValueError('duplicate stream identity')
        self.policies = dict(policies)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.monotonic = monotonic or time.monotonic
        self.process_id = process_id or os.getpid
        self.lock = RLock()
        self.clear()

    def clear(self):
        with self.lock:
            self.epoch = str(uuid4())
            self.pid = self.process_id()
            self.records = dict.fromkeys(self.policies)
            self.received_ticks = {}
            self.last_at = None
            self.last_tick = None

    def _now(self):
        if self.pid != self.process_id():
            self.clear()  # Also covers a preloaded app forked into a new worker.
        at, tick = self.clock(), self.monotonic()
        if not isinstance(at, datetime) or at.tzinfo is None or at.utcoffset() is None:
            raise ValueError('aware receipt clock required')
        if type(tick) not in (int, float) or not math.isfinite(tick):
            raise ValueError('finite monotonic clock required')
        at = at.astimezone(timezone.utc)
        if (self.last_at is not None and at < self.last_at) or (self.last_tick is not None and tick < self.last_tick):
            self.clear()  # Never revive prior evidence across a clock rollback.
        self.last_at, self.last_tick = at, tick
        return at, tick

    def observe(self, packet):
        with self.lock:
            at, tick = self._now()
            for name, policy in self.policies.items():
                record = temperature_receipt(packet, policy=policy, stream_epoch=self.epoch, received_at=at)
                if record is not None:
                    self.records[name] = record
                    self.received_ticks[name] = tick

    def snapshot(self):
        with self.lock:
            at, tick = self._now()
            for name, record in self.records.items():
                if record is None or record['status'] != 'valid':
                    continue
                deadline = datetime.fromisoformat(record['validUntil'])
                if at >= deadline or tick - self.received_ticks[name] >= self.policies[name].validity_seconds:
                    record.update(status='invalid', reason='expired', recordedAt=at.isoformat(),
                                  receivedAt=None, validUntil=None, temperatureF=None)
            return {'version': 1, 'streamEpoch': self.epoch, 'records': deepcopy(self.records)}


def install_temperature_evidence(app, *, enabled=False, policies=None, clock=None, monotonic=None, process_id=None):
    """Install only with literal True and explicit policy; disabled means no hooks.

    Call during application setup, before serving any request. Existing receiver
    routes and persisted fallback state are neither read nor modified here.
    """
    if enabled is not True:
        return None
    from flask import jsonify, request
    if 'temperature_receipt_evidence' in app.view_functions or any(rule.rule == '/temperature_evidence' for rule in app.url_map.iter_rules()):
        raise ValueError('temperature evidence already installed')
    collector = TemperatureCollector(policies, clock=clock, monotonic=monotonic, process_id=process_id)

    @app.before_request
    def capture_temperature_receipt():
        if request.method == 'GET' and request.path == '/weather':
            try:
                collector.observe(request.args)
            except Exception:
                collector.clear()
                app.logger.warning('temperature evidence capture unavailable')
        return None

    def evidence_response():
        try:
            response = jsonify(collector.snapshot())
        except Exception:
            collector.clear()
            response = jsonify({'error': 'temperature evidence unavailable'})
            response.status_code = 503
        response.headers['Cache-Control'] = 'no-store'
        return response

    app.add_url_rule('/temperature_evidence', 'temperature_receipt_evidence', evidence_response, methods=['GET'])
    return collector
