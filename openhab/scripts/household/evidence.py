"""Frozen original-source references; a reference grants no action authority."""
from dataclasses import dataclass
from datetime import datetime, timezone
import math
import re
from uuid import UUID

ROLES = {
    'battery_soc': ('energy', 'percent'), 'pv_day_wh': ('energy', 'Wh'),
    'air_temperature': ('thermal', 'degF'), 'mass_temperature': ('thermal', 'degF'),
    'outdoor_temperature': ('weather', 'degF'), 'water_inventory': ('water', 'litre'),
}


def utc(value):
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError('aware clock required')
    return value.astimezone(timezone.utc)


def epoch(value):
    if not isinstance(value, str) or str(UUID(value)) != value or UUID(value).int == 0:
        raise ValueError('canonical nonzero source epoch required')
    return value


def digest(value):
    if not isinstance(value, str) or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise ValueError('exact SHA256 required')
    return value


@dataclass(frozen=True)
class EvidenceRef:
    source_role: str
    source_identity: str
    digest: str | None
    source_epoch: str | None
    hardware_epoch: str | None
    observed_at: datetime | None
    received_at: datetime | None
    available_at: datetime | None
    valid_until: datetime | None
    assessed_at: datetime
    quality: str
    reason: str | None
    parent_digests: tuple[str, ...] = ()

    def __post_init__(self):
        if self.source_role not in ROLES or not isinstance(self.source_identity, str) or not 1 <= len(self.source_identity) <= 256:
            raise ValueError('explicit bounded source identity and role required')
        for key in ('observed_at', 'received_at', 'available_at', 'valid_until', 'assessed_at'):
            value = getattr(self, key)
            if value is not None: object.__setattr__(self, key, utc(value))
        if self.digest is not None: digest(self.digest)
        for value in (self.source_epoch, self.hardware_epoch):
            if value is not None: epoch(value)
        if not isinstance(self.parent_digests, tuple) or len(self.parent_digests) > 8:
            raise ValueError('bounded immutable original parent references required')
        for value in self.parent_digests: digest(value)
        if self.quality == 'qualified':
            if self.reason is not None or any(getattr(self, key) is None for key in ('digest', 'source_epoch', 'received_at', 'available_at', 'valid_until')):
                raise ValueError('qualified source provenance required')
            if not self.received_at <= self.available_at <= self.assessed_at < self.valid_until:
                raise ValueError('qualified source clock order required')
            if self.observed_at is not None and self.observed_at > self.received_at:
                raise ValueError('future source observation refused')
        elif self.quality != 'unavailable' or not isinstance(self.reason, str) or not 1 <= len(self.reason) <= 80:
            raise ValueError('explicit unavailable reason required')


@dataclass(frozen=True)
class Observation:
    ref: EvidenceRef
    value: float | int | None
    unit: str

    def __post_init__(self):
        if not isinstance(self.ref, EvidenceRef) or self.unit != ROLES[self.ref.source_role][1]:
            raise ValueError('source-specific observation unit required')
        if self.ref.quality == 'qualified':
            if type(self.value) not in (int, float) or not math.isfinite(self.value):
                raise ValueError('finite qualified scalar required')
        elif self.value is not None:
            raise ValueError('unavailable evidence cannot supply a value')
