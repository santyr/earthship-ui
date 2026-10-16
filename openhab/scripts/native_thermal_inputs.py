"""Separately versioned native-solar installed-shade development dataset.

Original training receipts remain mandatory replay dependencies. Native solar
positions change only calculated features and explicitly inferred night zeros;
measured radiation and receipt/quality/action barriers keep their authority.
This module never fits, publishes, or authorizes equipment.
"""
from collections import Counter
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime
import json
import astro_geometry as geometry_contract
from astro_geometry_series import NativeGeometrySeries
from thermal_model import dataset as original
from thermal_model.actions import reconstruct_events, reconstruct_state
from thermal_model.installed_shade_inputs import (
    DevelopmentInputs, DevelopmentWeather, build_development_inputs,
    select_development_endpoints)
from thermal_model.schema import ThermalSample, SOURCE_WEIGHTS
from thermal_model.solar import (SITE_LATITUDE, SITE_LONGITUDE,
    CLEAR_SKY_IRRADIANCE_WM2, CLEAR_SKY_EXPONENT, CLEAR_SKY_MAX_FRACTION)
from thermal_model.graduation_policy import _utc, _sha

SCHEMA = 'earthship-native-solar-development-data/v1'
NIGHT_ZERO = 'native_solar_night_zero'
MAX_BYTES = 8 * 1024 * 1024
FLAGS = dict(release_authorized=False, as_issued_forecast=False, automatic_actuation=False)


def solar_feature_contract():
    return dict(rule='earthship-native-clear-sky-fraction/v2',
        geometry_rule=geometry_contract.SOLAR_RULE,
        night_when_elevation_degrees_lte=0.0,
        clear_sky_irradiance_wm2=CLEAR_SKY_IRRADIANCE_WM2,
        exponent=CLEAR_SKY_EXPONENT, maximum_fraction=CLEAR_SKY_MAX_FRACTION,
        measured_radiation_source='original_station_radiation',
        inferred_night_provenance=NIGHT_ZERO)


def native_clear_sky_fraction(radiation_wm2, at, *, geometry):
    if type(geometry) is not NativeGeometrySeries:
        raise ValueError('validated complete native geometry required')
    radiation = geometry_contract._number(radiation_wm2, 0, 1600)
    # Even a zero observation requires the declared exact geometry coverage.
    sine = geometry.elevation_sin(at)
    if radiation <= 0 or sine <= 0: return 0.0
    return min(CLEAR_SKY_MAX_FRACTION,
        radiation / (CLEAR_SKY_IRRADIANCE_WM2 * sine**CLEAR_SKY_EXPONENT))


def _project_actions(at, radiation, outdoor, events, regimes, cooldowns, geometry):
    # Regime-free delegation preserves direct/unknown events, heat exclusions,
    # cooldowns and original precedence without calling the legacy daylight rule.
    values, confidences, _, passive = original._project_actions(
        at, radiation, outdoor, events, (), cooldowns)
    regime = original._regime_at(regimes, at)
    if regime is not None:
        daylight = not geometry.is_thermal_night(at)
        reconstructed = reconstruct_state(regime, is_daylight=daylight,
            sunny=daylight and radiation > 150, cold_cloudy=daylight and radiation < 100 and outdoor < 40)
        actions = {'vent_open': 'vent', 'indoor_shade_closed': 'indoor_shade',
                   'outdoor_shade_present': 'outdoor_shade'}
        for field, value in reconstructed.items():
            if original._effective_action(events, actions[field], at) is None:
                values[field] = value
                if value is not None: confidences[field] = SOURCE_WEIGHTS['historical_reconstruction']
    joined = [confidences[field] for field, value in values.items() if value is not None]
    return values, confidences, min(joined) if joined else 0.0, passive


def _encode_row(row):
    return {key: _utc(value).isoformat() if isinstance(value, datetime) else value
            for key, value in asdict(row).items()}


@dataclass(frozen=True)
class NativeDevelopmentEndpoint:
    """Native dataset lineage deliberately incompatible with the legacy fitter."""
    origin: ThermalSample
    target: ThermalSample
    forcings: tuple
    source_snapshot_sha256: str
    dataset_sha256: str
    series_sha256: str


class NativeDevelopmentData:
    """Immutable frozen data with copied serialization and pinned solar coverage."""
    __slots__ = ('_encoded', '_development', '_geometry', '_sha256')
    release_authorized = False
    as_issued_forecast = False
    automatic_actuation = False

    def __init__(self, *args, **kwargs):
        raise TypeError('construct native data through original input validation')

    def __setattr__(self, key, value): raise AttributeError('native development data is immutable')
    @property
    def sha256(self): return self._sha256
    @property
    def development(self): return self._development
    @property
    def geometry(self): return self._geometry
    def to_dict(self): return json.loads(self._encoded)


def build_native_development(record, *, expected_snapshot_sha256, sensor_epochs,
                             geometry, expected_series_sha256, assessed_at):
    if type(geometry) is not NativeGeometrySeries or geometry.sha256 != _sha(expected_series_sha256):
        raise ValueError('original complete native geometry series pin required')
    record = deepcopy(record); assessed = _utc(assessed_at)
    legacy = build_development_inputs(record, expected_snapshot_sha256=expected_snapshot_sha256,
                                     sensor_epochs=sensor_epochs, assessed_at=assessed)
    descriptor = geometry.descriptor()
    if (_utc(descriptor['available_at']) > assessed or
            descriptor['site']['latitude'] != SITE_LATITUDE or
            descriptor['site']['longitude'] != SITE_LONGITUDE or
            descriptor['timezone'] != 'America/Denver'):
        raise ValueError('native geometry unavailable or outside thermal site/timezone')
    times = []; at = original._floor_five(legacy.start)
    if at < legacy.start: at += original.STEP
    while at < legacy.end: times.append(at); at += original.STEP
    if geometry.to_dict()['request']['instants'] != [at.isoformat() for at in times]:
        raise ValueError('complete exact native dataset geometry coverage required')
    native = {role: {_utc(at): receipt for at, receipt in rows}
              for role, rows in record['temperature_grids'].items()}
    raw = {role: tuple((_utc(at), value) for at, value in rows)
           for role, rows in record['series_by_role'].items()}
    buckets, invalid, interpolation, held, observed, provenance = original._bucket_series(raw, legacy.start, legacy.end)
    # The old snapshot/measurement helper is a replay dependency, never the
    # native night authority. Discard ALL its inferred zeros before rebuilding.
    for at, kind in tuple(provenance.items()):
        if kind == 'astronomical_night_zero':
            del buckets['radiation'][at]; del provenance[at]
    for at in times:
        if at not in buckets['radiation'] and at not in invalid['radiation'] and geometry.is_thermal_night(at):
            buckets['radiation'][at] = 0.0; provenance[at] = NIGHT_ZERO
    ranges = original._range_failures(buckets, ('air', 'mass', 'outdoor'), include_radiation=True)
    jumps = original._jump_failures(observed, ('air', 'mass', 'outdoor'))
    gaps = original._large_gap_buckets(observed, legacy.start, legacy.end)
    weather_jumps = original._jump_failures(observed, ('outdoor',))
    # Decode through the validated original journal rather than interpreting a
    # second action vocabulary. Its constructor performs no reads or writes.
    from thermal_model.training_inputs import _Journal
    journal = _Journal(record)
    events = journal.effective_events(legacy.start, legacy.end)
    modes = journal.effective_modes(legacy.start, legacy.end)
    regimes = reconstruct_events(legacy.start, legacy.end, modes)
    cooldowns = original._confirmed_kiva_cooldowns(events)
    auxiliary = Counter(); rejected = Counter(); samples = []
    optional = {role: (original._range_failures(buckets, (role,), include_radiation=False),
        original._jump_failures(observed, (role,)),
        original._large_gap_buckets(observed, legacy.start, legacy.end, (role,)))
        for role in ('glazing', 'living_office')}
    def extra(role, at):
        arguments = (at, buckets[role], invalid[role], *optional[role], auxiliary)
        if role == 'glazing': return original._glazing_value(*arguments)
        return original._optional_temperature_value(role, *arguments)
    for at in times:
        if any(at not in buckets[role] for role in original.REQUIRED_ROLES):
            rejected['missing_required'] += 1
            if at in gaps: rejected['source_gap'] += 1
            continue
        if at in ranges: rejected['range'] += 1; continue
        if at in jumps: rejected['jump'] += 1; continue
        values, confidences, confidence, passive = _project_actions(at,
            buckets['radiation'][at], buckets['outdoor'][at], events, regimes, cooldowns, geometry)
        samples.append(ThermalSample(at=at, air_f=buckets['air'][at], mass_f=buckets['mass'][at],
            glazing_f=extra('glazing', at), outdoor_f=buckets['outdoor'][at], radiation_wm2=buckets['radiation'][at],
            vent_open=values['vent_open'], vent_confidence=confidences.get('vent_open', 0.0),
            indoor_shade_closed=values['indoor_shade_closed'], indoor_shade_confidence=confidences.get('indoor_shade_closed', 0.0),
            outdoor_shade_present=values['outdoor_shade_present'], outdoor_shade_confidence=confidences.get('outdoor_shade_present', 0.0),
            action_confidence=confidence, passive_fit_allowed=passive, mode=original._regime_at(regimes, at),
            living_office_f=extra('living_office', at)))
    samples = tuple(row for row in original._observe_latent_mass(samples)
        if all(native[role].get(row.at) is not None for role, _ in legacy.sensor_epochs))
    weather = []
    for at, receipt in sorted(native['outdoor'].items()):
        radiation = buckets['radiation'].get(at); kind = provenance.get(at)
        if (receipt is None or at in weather_jumps or kind not in ('observed', NIGHT_ZERO) or
                radiation is None or not 0 <= radiation <= 1600 or not -40 <= receipt['temperatureF'] <= 140): continue
        values, _, _, passive = _project_actions(at, radiation, receipt['temperatureF'], events, regimes, cooldowns, geometry)
        weather.append(DevelopmentWeather(at, receipt['temperatureF'], radiation, kind, receipt['sensorEpoch'],
            receipt['streamEpoch'], receipt['snapshotSha256'], passive, values['outdoor_shade_present']))
    development = DevelopmentInputs(samples, tuple(weather), legacy.sensor_epochs,
        legacy.ineligible_action_times, legacy.unavailable_origin_intervals,
        legacy.start, legacy.end, legacy.captured_at, legacy.source_snapshot_sha256)
    sample_rows = []
    for row in samples:
        sample_rows.append({**_encode_row(row), 'radiation_provenance': provenance[row.at],
            'native_elevation_degrees': geometry.elevation_degrees(row.at),
            'native_clear_sky_fraction': native_clear_sky_fraction(row.radiation_wm2, row.at, geometry=geometry)})
    value = dict(schema=SCHEMA, source_snapshot_sha256=legacy.source_snapshot_sha256,
        sensor_epochs=dict(legacy.sensor_epochs), assessed_at=assessed.isoformat(),
        captured_at=legacy.captured_at.isoformat(), start=legacy.start.isoformat(), end=legacy.end.isoformat(),
        geometry=descriptor, solar_feature=solar_feature_contract(), samples=sample_rows,
        weather=[_encode_row(row) for row in weather],
        ineligible_action_times=[at.isoformat() for at in legacy.ineligible_action_times],
        unavailable_origin_intervals=[[left.isoformat(), right.isoformat()] for left, right in legacy.unavailable_origin_intervals],
        quality=dict(rejected_counts=dict(rejected), auxiliary_exclusion_counts=dict(auxiliary),
                     interpolation_counts=interpolation, hold_forward_counts=held), **FLAGS)
    value['dataset_sha256'] = geometry_contract._digest(value, 'dataset_sha256')
    if len(geometry_contract._canonical(value)) > MAX_BYTES: raise ValueError('bounded native development dataset required')
    # Construct only here, after independently rederiving the complete sealed
    # payload and freezing every sample/weather/geometry dependency.
    result = object.__new__(NativeDevelopmentData)
    object.__setattr__(result, '_encoded', geometry_contract._canonical(value))
    object.__setattr__(result, '_development', development)
    object.__setattr__(result, '_geometry', geometry)
    object.__setattr__(result, '_sha256', value['dataset_sha256'])
    return result


def select_native_endpoints(data, *, horizon_hours, start, end):
    if type(data) is not NativeDevelopmentData: raise ValueError('validated native development data required')
    points = select_development_endpoints(data.development, horizon_hours=horizon_hours, start=start, end=end)
    return tuple(NativeDevelopmentEndpoint(point.origin, point.target, point.forcings,
        point.source_snapshot_sha256, data.sha256, data.geometry.sha256) for point in points)


def replay_native_development(raw, *, record, expected_dataset_sha256, expected_snapshot_sha256,
                              sensor_epochs, geometry, expected_series_sha256):
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_BYTES:
        raise ValueError('bounded retained native development data required')
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value: raise ValueError('duplicate native development field')
            value[key] = item
        return value
    def nonfinite(_): raise ValueError('nonfinite native development JSON')
    try: value = json.loads(raw, object_pairs_hook=unique, parse_constant=nonfinite)
    except (UnicodeError, json.JSONDecodeError): raise ValueError('retained native development JSON required') from None
    if not isinstance(value, dict) or value.get('dataset_sha256') != _sha(expected_dataset_sha256):
        raise ValueError('native development dataset differs from original pin')
    restored = build_native_development(record, expected_snapshot_sha256=expected_snapshot_sha256,
        sensor_epochs=sensor_epochs, geometry=geometry, expected_series_sha256=expected_series_sha256,
        assessed_at=value['assessed_at'])
    if geometry_contract._canonical(value) != geometry_contract._canonical(restored.to_dict()):
        raise ValueError('native development data differ from original measurement/geometry replay')
    return restored
