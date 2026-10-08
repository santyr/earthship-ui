"""Original native inputs for installed-shade development conditional hindcasts.

Observed future weather is permitted only for development. These immutable
records provide neither as-issued evidence nor artifact/release authority.
Missing interior readings remain missing; original forcing and real endpoint
support are checked separately. Future action labels affect eligibility only.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import ClassVar

from .actions import DENVER, reconstruct_events
from .dataset import (_bucket_series, _confirmed_kiva_cooldowns,
                      _jump_failures, _project_actions)
from .graduation_policy import _sha, _utc
from .installed_shade_dynamics import InstalledShadeForcing, STEP
from .schema import ThermalSample
from .temperature_history import _sensor_bindings
from .training_inputs import ITEMS, restore_training_inputs_v2


@dataclass(frozen=True)
class DevelopmentWeather:
    at: datetime
    outdoor_f: float
    radiation_wm2: float
    radiation_provenance: str
    sensor_epoch: str
    stream_epoch: str
    outdoor_snapshot_sha256: str
    passive_fit_allowed: bool
    outdoor_shade_present: float | None


@dataclass(frozen=True)
class DevelopmentInputs:
    samples: tuple[ThermalSample, ...]
    weather: tuple[DevelopmentWeather, ...]
    sensor_epochs: tuple[tuple[str, str], ...]
    ineligible_action_times: tuple[datetime, ...]
    start: datetime
    end: datetime
    captured_at: datetime
    source_snapshot_sha256: str
    release_authorized: ClassVar[bool] = False
    as_issued_forecast: ClassVar[bool] = False


@dataclass(frozen=True)
class DevelopmentEndpoint:
    origin: ThermalSample
    target: ThermalSample
    forcings: tuple[InstalledShadeForcing, ...]
    source_snapshot_sha256: str
    release_authorized: ClassVar[bool] = False
    as_issued_forecast: ClassVar[bool] = False


def build_development_inputs(record, *, expected_snapshot_sha256,
                             sensor_epochs, assessed_at):
    """Validate the pinned native-v2 capture and preserve its source identities."""
    pin = _sha(expected_snapshot_sha256)
    phases = _sensor_bindings(sensor_epochs)
    if not isinstance(record, dict) or record.get('snapshot_sha256') != pin:
        raise ValueError('pinned original input snapshot required')
    frozen = restore_training_inputs_v2(record)
    captured = _utc(record['captured_at'])
    if captured > _utc(assessed_at):
        raise ValueError('input capture unavailable at assessment')
    roles = record['temperature_evidence']['roles']
    if any(roles[role]['sensor_epoch'] != epoch for role, epoch in phases.items()):
        raise ValueError('input sensor phases differ from declared native phases')

    grids = frozen.series_reader.temperature_grids()
    native = {role: {_utc(at): receipt for at, receipt in grid}
              for role, grid in grids.items()}
    # Require genuine original receipts at both endpoints, even if the existing
    # dataset builder could interpolate some interior sensor rows.
    samples = tuple(row for row in frozen.samples
                    if all(native[role].get(row.at) is not None for role in phases))
    raw = {role: frozen.series_reader(item, frozen.start, frozen.end)
           for role, item in ITEMS.items()}
    buckets, _, _, _, observed, provenance = _bucket_series(raw, frozen.start, frozen.end)
    jumps = _jump_failures(observed, ('outdoor',))
    events = frozen.journal.effective_events(frozen.start, frozen.end)
    modes = frozen.journal.effective_modes(frozen.start, frozen.end)
    regimes = reconstruct_events(frozen.start, frozen.end, modes)
    cooldowns = _confirmed_kiva_cooldowns(events)
    # Conservative eligibility barriers retain every recorded domain/heat
    # event, including episodes shorter than one five-minute forcing step.
    # These labels only exclude windows; they never authorize advice or enter
    # the predictor. The original snapshot retains their source/confidence.
    barriers = tuple(sorted({_utc(event.effective_at) for event in events
        if (event.action == 'outdoor_shade' and
            event.state not in ('installed', 'present')) or
           (event.action == 'kiva' and
            (event.state in ('on', 'exceptional_heat_unknown') or
             'exceptional_heat_unknown' in event.note))}))
    weather = []
    for at, receipt in sorted(native['outdoor'].items()):
        radiation = buckets['radiation'].get(at)
        kind = provenance.get(at)
        if (receipt is None or at in jumps or
                kind not in ('observed', 'astronomical_night_zero') or
                radiation is None or not 0 <= radiation <= 1600):
            continue
        outdoor = receipt['temperatureF']
        if not -40 <= outdoor <= 140:
            continue
        values, _, _, passive = _project_actions(
            at, radiation, outdoor, events, regimes, cooldowns)
        weather.append(DevelopmentWeather(
            at, outdoor, radiation, kind, receipt['sensorEpoch'],
            receipt['streamEpoch'], receipt['snapshotSha256'], passive,
            values['outdoor_shade_present']))
    return DevelopmentInputs(samples, tuple(weather), tuple(sorted(phases.items())), barriers,
                             frozen.start, frozen.end, captured, pin)


def select_development_endpoints(data, *, horizon_hours, start, end):
    """Choose at most one eligible origin per Denver date for one horizon.

    Dates are a sampling convention, not a claim of independent evidence.
    Callers must separately count non-overlapping windows and enforce all
    qualification gates. No future action state enters predictive forcings.
    """
    if not isinstance(data, DevelopmentInputs):
        raise ValueError('validated native development inputs required')
    if type(horizon_hours) is not int or not 1 <= horizon_hours <= 72:
        raise ValueError('bounded integer development horizon required')
    start, end = _utc(start), _utc(end)
    if not data.start <= start < end <= data.end:
        raise ValueError('selection interval outside original capture')
    samples = {row.at: row for row in data.samples}
    weather = {row.at: row for row in data.weather}
    duration = timedelta(hours=horizon_hours)
    selected = []
    days = set()
    for origin in sorted(data.samples, key=lambda row: row.at):
        date = origin.at.astimezone(DENVER).date()
        target_at = origin.at + duration
        target = samples.get(target_at)
        if (date in days or not start <= origin.at < target_at < end or
                target is None or not origin.passive_fit_allowed or
                not target.passive_fit_allowed or origin.outdoor_shade_present != 1 or
                target.outdoor_shade_present != 1 or
                origin.indoor_shade_closed is None or
                not 0 <= origin.indoor_shade_closed <= 1 or
                origin.vent_open is None or not 0 <= origin.vent_open <= 2):
            continue
        if any(origin.at < at <= target_at for at in data.ineligible_action_times):
            continue
        prefix = tuple(weather.get(origin.at + STEP * index)
                       for index in range(1, horizon_hours * 12 + 1))
        if any(row is None or not row.passive_fit_allowed or
               row.outdoor_shade_present != 1 for row in prefix):
            continue
        forcings = tuple(InstalledShadeForcing(
            row.at, row.outdoor_f, row.radiation_wm2,
            origin.indoor_shade_closed, 1., origin.vent_open) for row in prefix)
        selected.append(DevelopmentEndpoint(origin, target, forcings,
                                             data.source_snapshot_sha256))
        days.add(date)
    return tuple(selected)
