"""Split-airflow dataset and five-minute identification seed, not a release.

Window, skylight and their joint-opening effect stay distinct. Unknown states
are not closed states; legacy vent observations never label either opening.
This seed is not the multihorizon fitter, artifact contract or live publisher.
"""
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from itertools import product
import math

import numpy as np

from .dataset import (CONFIRMED_SOURCES, STEP, ThermalDataset, _binary_state,
                      _ceil_five, _effective_action, _utc, build_samples, dataset_manifest)
from .dynamics import (AIR_BOUNDS, AIR_NAMES, GLAZING_BOUNDS as LEGACY_GLAZING_BOUNDS,
                       GLAZING_NAMES as LEGACY_GLAZING_NAMES,
                       MASS_BOUNDS as LEGACY_MASS_BOUNDS, MASS_NAMES as LEGACY_MASS_NAMES,
                       STABILITY_TOLERANCE,
                       _checked_output, _fit, _full_rank, _valid_glazing,
                       _fit_with_inactive_action_columns, _validate_gain_relationship)
from .joint_solar import SOLAR_NAMES, solar_terms as _solar_terms
from .schema import ThermalSample

AIRFLOW_FIELDS = ('window_open', 'skylight_open')
AIRFLOW_NAMES = ('window_exchange', 'skylight_exchange', 'joint_open_exchange')
SEED_AIR_NAMES = AIR_NAMES[:2] + SOLAR_NAMES + AIRFLOW_NAMES + ('bias',)
SEED_AIR_BOUNDS = (AIR_BOUNDS[0][:-2] + [0.0, 0.0, 0.0, 0.0, -0.20],
                   AIR_BOUNDS[1][:-2] + [0.010, 0.40, 0.40, 0.40, 0.20])
MASS_NAMES = LEGACY_MASS_NAMES + ('solar_both_closed',)
MASS_BOUNDS = (LEGACY_MASS_BOUNDS[0] + [0.0], LEGACY_MASS_BOUNDS[1] + [0.004])
GLAZING_NAMES = LEGACY_GLAZING_NAMES + ('solar_both_closed',)
GLAZING_BOUNDS = (LEGACY_GLAZING_BOUNDS[0] + [0.0], LEGACY_GLAZING_BOUNDS[1] + [0.003])
SUPPORTED_ACTIONS = {'window', 'skylight', 'indoor_shade', 'outdoor_shade', 'kiva'}


@dataclass(frozen=True)
class AirflowSample(ThermalSample):
    airflow_vocabulary_version: int = 2
    window_open: float | None = None
    window_confidence: float = 0.0
    window_event_id: str | None = None
    window_source: str | None = None
    skylight_open: float | None = None
    skylight_confidence: float = 0.0
    skylight_event_id: str | None = None
    skylight_source: str | None = None


@dataclass(frozen=True)
class AirflowSeed:
    version: int
    step_minutes: int
    air_coefficients: dict[str, float]
    mass_coefficients: dict[str, float]
    glazing_observation_coefficients: dict[str, float]


def build_airflow_samples(series_by_role, events, modes, start, end, *, known_by=None):
    events, modes = tuple(events), tuple(modes)
    if known_by is not None:
        cutoff = _utc(known_by, 'knowledge cutoff')
        if _utc(end, 'end') > cutoff:
            raise ValueError('training sample end exceeds knowledge cutoff')
        # Receipt time is not the journal commit time: the operational reader
        # must additionally qualify created_at before any as-issued claim.
        events = tuple(e for e in events if _utc(e.received_at, 'event received_at') <= cutoff)
        modes = tuple(e for e in modes if _utc(e.received_at, 'mode received_at') <= cutoff)
        series_by_role = {role: [(at, value) for at, value in points
            if _utc(at, 'series point at') <= cutoff] for role, points in series_by_role.items()}
    legacy = build_samples(series_by_role, events, modes, start, end)
    rows = []
    for sample in legacy:
        extra = {}
        for action in ('window', 'skylight'):
            event = _effective_action(events, action, sample.at)
            value = _binary_state(event, {'open'}, {'closed'})
            extra[action + '_open'] = value
            extra[action + '_confidence'] = event.confidence if value is not None else 0.0
            extra[action + '_event_id'] = event.event_id if event is not None else None
            extra[action + '_source'] = event.source if event is not None else None
        # Historical vent reconstruction and labels are intentionally not v2 inputs.
        values = {**asdict(sample), 'vent_open': None, 'vent_confidence': 0.0, **extra}
        confidences = [extra['window_confidence'], extra['skylight_confidence'],
                       sample.indoor_shade_confidence, sample.outdoor_shade_confidence]
        values['action_confidence'] = min(confidences)
        rows.append(AirflowSample(**values))
    result = ThermalDataset(rows, start=legacy.start, end=legacy.end,
        rejected_counts=legacy.rejected_counts,
        auxiliary_exclusion_counts=legacy.auxiliary_exclusion_counts,
        # This candidate is not eligible to supply the legacy promotion counter.
        confirmed_action_rows=(), interpolation_counts=legacy.interpolation_counts,
        hold_forward_counts=legacy.hold_forward_counts,
        radiation_provenance_by_at=legacy.radiation_provenance_by_at)
    result.airflow_vocabulary_version = 2
    sample_times = {sample.at for sample in result}
    result.split_action_observation_rows = tuple(sorted({
        _ceil_five(event.effective_at) for event in events
        if event.source in CONFIRMED_SOURCES and event.action in SUPPORTED_ACTIONS
        and _ceil_five(event.effective_at) in sample_times}))
    return result


def airflow_manifest(samples, events, modes):
    if any(not isinstance(row, AirflowSample) for row in samples):
        raise ValueError('split-airflow manifest requires v2 samples')
    for row in samples:
        _split_contract(row)
    return {'schema': 'earthship-split-airflow-dataset/v2',
            'legacy_promotion_eligible': False,
            'dataset': dataset_manifest(samples, events, modes),
            'state_counts': {name: {
                state: sum(getattr(row, name) == value for row in samples)
                for state, value in (('unknown', None), ('closed', 0.0), ('open', 1.0))}
                for name in AIRFLOW_FIELDS}}


def _field(row, name):
    return row[name] if isinstance(row, dict) else getattr(row, name)


def _optional_field(row, name):
    return row.get(name) if isinstance(row, dict) else getattr(row, name, None)


def _split_contract(row):
    version = _optional_field(row, 'airflow_vocabulary_version')
    has_version = 'airflow_vocabulary_version' in row if isinstance(row, dict) \
        else hasattr(row, 'airflow_vocabulary_version')
    if has_version and (type(version) is not int or version != 2):
        raise ValueError('invalid split-airflow vocabulary version')
    if _optional_field(row, 'vent_open') is not None:
        raise ValueError('split-airflow cannot contain legacy vent forcing')
    for name in AIRFLOW_FIELDS:
        value = _optional_field(row, name)
        if value is not None and (type(value) not in (int, float)
                or not math.isfinite(value) or value not in (0, 1)):
            raise ValueError('window and skylight states must be independently known binary values')
    for name in ('window_confidence', 'skylight_confidence'):
        confidence = _optional_field(row, name)
        present = name in row if isinstance(row, dict) else hasattr(row, name)
        if present and (type(confidence) not in (int, float)
                or not math.isfinite(confidence) or not 0 <= confidence <= 1):
            raise ValueError('invalid split-airflow confidence')


def airflow_features(row):
    _split_contract(row)
    values = [_field(row, name) for name in AIRFLOW_FIELDS]
    if any(type(v) not in (int, float) or not math.isfinite(v) or v not in (0, 1)
           for v in values):
        raise ValueError('window and skylight states must be independently known binary values')
    window, skylight = values
    return window, skylight, window * skylight


def predict_airflow_step(model, row):
    window, skylight, joint = airflow_features(row)
    air, mass, outdoor = (float(_field(row, k)) for k in ('air_f', 'mass_f', 'outdoor_f'))
    solar = _solar_terms(row)
    a, m = model.air_coefficients, model.mass_coefficients
    exchange = a['window_exchange'] * window + a['skylight_exchange'] * skylight \
        + a['joint_open_exchange'] * joint
    next_air = air + (a['outside_exchange'] + exchange) * (outdoor - air) \
        + a['mass_exchange'] * (mass - air) \
        + sum(a[k] * s for k, s in zip(SOLAR_NAMES, solar)) + a['bias']
    next_mass = mass + m['air_exchange'] * (air - mass) \
        + m['outside_exchange'] * (outdoor - mass) \
        + sum(m[k] * s for k, s in zip(MASS_NAMES[2:], solar))
    glazing = None
    g = model.glazing_observation_coefficients
    if g:
        glazing = g['intercept'] + g['air'] * next_air + g['outdoor'] * outdoor \
            + sum(g[k] * s for k, s in zip(GLAZING_NAMES[3:], solar))
    return (_checked_output(next_air, 'air'), _checked_output(next_mass, 'mass'),
            _checked_output(glazing, 'glazing') if glazing is not None else None)


def simulate_airflow(model, initial, forcings):
    # Model validation is the caller's bounded artifact boundary, not repeated
    # on every five-minute step. No legacy vent forcing is constructed here.
    air = _checked_output(float(_field(initial, 'air_f')), 'initial air')
    mass = _checked_output(float(_field(initial, 'mass_f')), 'initial mass')
    result = []
    previous_at = None
    for forcing in forcings:
        _split_contract(forcing)
        row = {k: _field(forcing, k) for k in ('at', 'outdoor_f', 'radiation_wm2',
                   'window_open', 'skylight_open', 'indoor_shade_closed', 'outdoor_shade_present')}
        if (not isinstance(row['at'], datetime) or row['at'].utcoffset() is None
                or (previous_at is not None and row['at'] - previous_at != STEP)):
            raise ValueError('split-airflow forecast must have consecutive aware five-minute times')
        previous_at = row['at']
        row.update(air_f=air, mass_f=mass)
        air, mass, glazing = predict_airflow_step(model, row)
        result.append({'air_f': air, 'mass_f': mass, 'glazing_f': glazing})
    return result


def validate_airflow_physics(model):
    if (type(model) is not AirflowSeed or type(model.version) is not int or model.version != 2
            or type(model.step_minutes) is not int or model.step_minutes != 5):
        raise ValueError('invalid split-airflow seed contract')
    for coefficients, names, bounds in (
        (model.air_coefficients, SEED_AIR_NAMES, SEED_AIR_BOUNDS),
        (model.mass_coefficients, MASS_NAMES, MASS_BOUNDS),
        (model.glazing_observation_coefficients, GLAZING_NAMES, GLAZING_BOUNDS)):
        if not coefficients and names == GLAZING_NAMES:
            continue
        if set(coefficients) != set(names) or any(
            type(coefficients[name]) not in (int, float)
            or not math.isfinite(coefficients[name])
            or not bounds[0][i] <= coefficients[name] <= bounds[1][i]
            for i, name in enumerate(names)):
            raise ValueError('split-airflow coefficient contract violated')
        _validate_gain_relationship(coefficients)
    a, m = model.air_coefficients, model.mass_coefficients
    if sum(a[k] for k in AIRFLOW_NAMES) > 0.80:
        raise ValueError('combined opening exchange exceeds physical bound')
    for window, skylight in product((0.0, 1.0), repeat=2):
        exchange = a['window_exchange'] * window + a['skylight_exchange'] * skylight \
            + a['joint_open_exchange'] * window * skylight
        matrix = np.array([[1-a['outside_exchange']-a['mass_exchange']-exchange,
                            a['mass_exchange']],
                           [m['air_exchange'], 1-m['air_exchange']-m['outside_exchange']]])
        if max(abs(np.linalg.eigvals(matrix))) >= 1.0 - STABILITY_TOLERANCE:
            raise ValueError('split-airflow transition is not stable')
        air, mass = 90.0, 50.0
        at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for step in range(72 * 12):
            air, mass, _ = predict_airflow_step(model, {
                'at': at + step * STEP, 'air_f': air, 'mass_f': mass,
                'outdoor_f': 70.0, 'radiation_wm2': 0.0,
                'window_open': window, 'skylight_open': skylight,
                'indoor_shade_closed': 0.0, 'outdoor_shade_present': 0.0})
    return model


def fit_airflow_seed_with_evidence(samples, *, allow_inactive_action_forcing=False):
    """Bounded one-step identification; full-rank independent openings required.

    Unknown openings, exceptional heat and nonconsecutive pairs cannot fit.
    This is an initialization experiment, NOT a replacement for the accepted
    multihorizon trainer or evidence of causal effects on household data.
    """
    rows = tuple(sorted(samples, key=lambda row: row.at))
    if any(not isinstance(row, AirflowSample) for row in rows):
        raise ValueError('split-airflow fitter requires v2 samples')
    for row in rows:
        _split_contract(row)
    if len({row.at for row in rows}) != len(rows):
        raise ValueError('duplicate split-airflow sample timestamp')
    pairs = []
    for left, right in zip(rows, rows[1:]):
        if right.at - left.at != STEP or not left.passive_fit_allowed or not right.passive_fit_allowed:
            continue
        if any(getattr(right, name) is None for name in
               (*AIRFLOW_FIELDS, 'indoor_shade_closed', 'outdoor_shade_present')):
            continue
        if (type(right.action_confidence) not in (int, float)
                or not math.isfinite(right.action_confidence) or not 0 <= right.action_confidence <= 1):
            raise ValueError('invalid split-airflow confidence')
        if min(right.action_confidence, right.window_confidence, right.skylight_confidence) > 0:
            pairs.append((left, right))
    air_x, air_y, mass_x, mass_y = [], [], [], []
    for left, right in pairs:
        solar = _solar_terms(right)
        openings = airflow_features(right)
        delta = right.outdoor_f - left.air_f
        weight = math.sqrt(min(right.action_confidence, right.window_confidence,
                               right.skylight_confidence))
        air_x.append(np.asarray((delta, left.mass_f-left.air_f, *solar,
                                *(value*delta for value in openings), 1.0)) * weight)
        air_y.append((right.air_f-left.air_f) * weight)
        mass_x.append(np.asarray((left.air_f-left.mass_f,
                                  right.outdoor_f-left.mass_f, *solar)) * weight)
        mass_y.append((right.mass_f-left.mass_f) * weight)
    if allow_inactive_action_forcing:
        matrix = np.asarray(air_x)
        if (matrix.size and np.any(matrix[:, SEED_AIR_NAMES.index('solar_both_closed')] != 0)
                and any(np.all(matrix[:, SEED_AIR_NAMES.index(name)] == 0)
                        for name in ('solar_indoor_closed', 'solar_outdoor'))):
            raise ValueError('joint shade requires independently identified single-shade gains')
        air, inactive_air = _fit_with_inactive_action_columns(air_x, air_y,
            SEED_AIR_BOUNDS, SEED_AIR_NAMES,
            frozenset((*AIRFLOW_NAMES, *SOLAR_NAMES[1:])))
        mass, inactive_mass = _fit_with_inactive_action_columns(mass_x, mass_y,
            MASS_BOUNDS, MASS_NAMES, frozenset(SOLAR_NAMES[1:]))
    else:
        air = _fit(air_x, air_y, SEED_AIR_BOUNDS, SEED_AIR_NAMES, ordered_solar=True)
        mass = _fit(mass_x, mass_y, MASS_BOUNDS, MASS_NAMES, ordered_solar=True)
        inactive_air = inactive_mass = ()
    glazing_x, glazing_y = [], []
    for _, right in pairs:
        if _valid_glazing(right):
            weight = math.sqrt(min(right.action_confidence, right.window_confidence,
                                   right.skylight_confidence))
            glazing_x.append(np.asarray((1.0, right.air_f, right.outdoor_f, *_solar_terms(right)))*weight)
            glazing_y.append(right.glazing_f*weight)
    glazing = _fit(glazing_x, glazing_y, GLAZING_BOUNDS, GLAZING_NAMES,
                   ordered_solar=True) if _full_rank(glazing_x, GLAZING_NAMES) else {}
    model = validate_airflow_physics(AirflowSeed(2, 5, air, mass, glazing))
    inactive = tuple(name for name in (*SEED_AIR_NAMES, *MASS_NAMES)
                     if name in set(inactive_air) | set(inactive_mass))
    return model, tuple(dict.fromkeys(inactive))


def fit_airflow_seed(samples):
    return fit_airflow_seed_with_evidence(samples)[0]
