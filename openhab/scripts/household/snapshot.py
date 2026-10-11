"""Canonical immutable state; completeness is descriptive, never authority."""
from dataclasses import dataclass, asdict
from hashlib import sha256
import re
from .codec import canonical, loads
from .evidence import ROLES, Observation, utc, digest


@dataclass(frozen=True)
class HouseholdSnapshot:
    content: bytes

    def __post_init__(self):
        if not isinstance(self.content, bytes) or len(self.content) > 262144:
            raise ValueError('bounded immutable snapshot required')

    @property
    def snapshot_id(self):
        return sha256(self.content).hexdigest()

    def to_dict(self):
        return {**loads(self.content), 'snapshot_id': self.snapshot_id}


def build_snapshot(observations, *, as_of, created_at, code_revision, config_revision,
                   requirements, max_age_seconds, max_skew_seconds):
    as_of, created_at = utc(as_of), utc(created_at)
    if created_at < as_of: raise ValueError('snapshot creation precedes as-of clock')
    if not isinstance(code_revision, str) or not re.fullmatch('[0-9a-f]{40}', code_revision):
        raise ValueError('explicit code revision required')
    digest(config_revision)
    if not isinstance(observations, (list, tuple)) or len(observations) > len(ROLES):
        raise ValueError('bounded original observation list required')
    if type(max_skew_seconds) is not int or not 0 <= max_skew_seconds <= 300:
        raise ValueError('explicit bounded source skew required')
    if not isinstance(max_age_seconds, dict) or any(
        role not in ROLES or type(age) is not int or not 1 <= age <= 86400
        for role, age in max_age_seconds.items()):
        raise ValueError('explicit source age limits required')
    if not isinstance(requirements, dict) or not 1 <= len(requirements) <= 32:
        raise ValueError('explicit capability requirements required')
    for name, roles in requirements.items():
        if not isinstance(name, str) or not re.fullmatch('[a-z][a-z0-9_]{0,63}', name) or not isinstance(roles, (list, tuple)) or not roles or len(roles) != len(set(roles)) or any(role not in ROLES for role in roles):
            raise ValueError('nonempty explicit capability source requirements required')
    rows = {}
    for observation in observations:
        if not isinstance(observation, Observation): raise ValueError('validated original observation required')
        ref = observation.ref; role = ref.source_role
        if role in rows: raise ValueError('duplicate source role refused')
        if role not in max_age_seconds: raise ValueError('observed role lacks explicit age policy')
        reason = ref.reason
        clock = ref.observed_at or ref.received_at
        if ref.quality == 'qualified':
            if ref.assessed_at > as_of or ref.available_at > as_of: reason = 'future_source'
            elif as_of >= ref.valid_until: reason = 'expired_source'
            elif (as_of-clock).total_seconds() > max_age_seconds[role]: reason = 'source_too_old'
        rows[role] = dict(value=observation.value if reason is None else None,
                          unit=observation.unit, reason=reason, evidence=asdict(ref))
    completeness, reasons = {}, {}
    for name, roles in requirements.items():
        valid = all(role in rows and rows[role]['reason'] is None for role in roles)
        reason = None if valid else 'required_source_unavailable'
        if valid:
            clocks = [(rows[role]['evidence']['observed_at'] or rows[role]['evidence']['received_at']) for role in roles]
            if (max(clocks)-min(clocks)).total_seconds() > max_skew_seconds:
                valid=False; reason='source_skew'
        completeness[name]=valid; reasons[name]=reason
    domains = {name: {} for name in ('energy', 'thermal', 'weather', 'water')}
    for role, (domain, unit) in ROLES.items():
        domains[domain][role] = rows.get(role, dict(value=None, unit=unit, reason='missing_source', evidence=None))
    content = dict(schema='earthship-household-snapshot/v1', as_of=as_of, created_at=created_at,
                   code_revision=code_revision, config_revision=config_revision, domains=domains,
                   completeness=completeness, capability_reasons=reasons, planner_authority='none',
                   temporal_policy=dict(max_age_seconds=dict(max_age_seconds), max_skew_seconds=max_skew_seconds,
                                        requirements={name:sorted(roles) for name,roles in requirements.items()}))
    return HouseholdSnapshot(canonical(content))
