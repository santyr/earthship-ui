"""Pure household-transition fitting and bounded shadow schedule comparison.

This module is deliberately non-actuating.  It consumes already-labelled samples,
uses the existing dynamics simulator, and returns modeled schedule comparisons.
"""

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import math

import numpy as np
from scipy.optimize import minimize

from .dynamics import simulate
from .schema import BehaviorModel, SOURCE_WEIGHTS


STEP = timedelta(minutes=5)
RIDGE_LAMBDA = 1.0
MIN_POSITIVES = 10
MIN_TRAINING_CONFIDENCE = SOURCE_WEIGHTS["historical_reconstruction"]
INSUFFICIENT_DATA = "insufficient_data"
FEATURE_NAMES = (
    "intercept",
    "sin_time",
    "cos_time",
    "sin_year",
    "cos_year",
    "outdoor_minus_air",
    "mass_minus_air",
    "radiation_norm",
    "solar_elevation_sin",
    "is_daylight",
)
TRANSITIONS = (
    "vent_open",
    "vent_close",
    "indoor_shade_open",
    "indoor_shade_close",
    "outdoor_shade_installed",
    "outdoor_shade_removed",
)
AIRFLOW_LEVELS = {"closed": 0.0, "baseline": 1.0, "boosted": 2.0}
SITE_LATITUDE = 38.3739919
SITE_LONGITUDE = -105.7744609
SITE_TIMEZONE = ZoneInfo("America/Denver")
SUNNY_RADIATION_WM2 = 150.0
MINIMUM_IMPROVEMENT = 0.25

_TRANSITION_STATES = {
    "vent_open": ("vent_open", False, True),
    "vent_close": ("vent_open", True, False),
    "indoor_shade_open": ("indoor_shade_closed", True, False),
    "indoor_shade_close": ("indoor_shade_closed", False, True),
    "outdoor_shade_installed": ("outdoor_shade_present", False, True),
    "outdoor_shade_removed": ("outdoor_shade_present", True, False),
}
_MISSING = object()


def _value(row, name, default=_MISSING):
    if isinstance(row, Mapping):
        value = row.get(name, _MISSING)
    else:
        value = getattr(row, name, _MISSING)
    if value is _MISSING:
        if default is _MISSING:
            raise ValueError(f"missing required field: {name}")
        return default
    return value


def _first_value(row, names, default=_MISSING):
    for name in names:
        try:
            return _value(row, name)
        except ValueError:
            continue
    if default is _MISSING:
        raise ValueError(f"missing required field: {' or '.join(names)}")
    return default


def _aware(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must include timezone information")
    return value


def _local_at(value):
    return _aware(value).astimezone(SITE_TIMEZONE)


def _minute_of_day(value):
    local = _local_at(value)
    return local.hour * 60.0 + local.minute + local.second / 60.0


def _solar_elevation_sin(at):
    """NOAA fractional-year approximation, returned as sin(elevation)."""
    at = _aware(at).astimezone(timezone.utc)
    day = at.timetuple().tm_yday
    hour = at.hour + at.minute / 60.0 + at.second / 3600.0
    gamma = 2.0 * math.pi / 365.0 * (day - 1 + (hour - 12.0) / 24.0)
    equation_minutes = 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2.0 * gamma)
        - 0.040849 * math.sin(2.0 * gamma)
    )
    declination = (
        0.006918
        - 0.399912 * math.cos(gamma)
        + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2.0 * gamma)
        + 0.000907 * math.sin(2.0 * gamma)
        - 0.002697 * math.cos(3.0 * gamma)
        + 0.00148 * math.sin(3.0 * gamma)
    )
    solar_minutes = hour * 60.0 + equation_minutes + 4.0 * SITE_LONGITUDE
    hour_angle = math.radians(solar_minutes / 4.0 - 180.0)
    latitude = math.radians(SITE_LATITUDE)
    return float(
        math.sin(latitude) * math.sin(declination)
        + math.cos(latitude) * math.cos(declination) * math.cos(hour_angle)
    )


def feature_vector(row):
    """Build the fixed, finite feature vector from one contemporaneous row."""
    at = _aware(_value(row, "at"))
    local = _local_at(at)
    minute = _minute_of_day(at)
    day = local.timetuple().tm_yday - 1 + minute / 1440.0
    air = float(_first_value(row, ("air_f", "air_baseline_f")))
    mass = float(_first_value(row, ("mass_f", "mass_baseline_f")))
    outdoor = float(_value(row, "outdoor_f"))
    radiation = float(_value(row, "radiation_wm2"))
    solar_sin = _solar_elevation_sin(at)
    values = (
        1.0,
        math.sin(2.0 * math.pi * minute / 1440.0),
        math.cos(2.0 * math.pi * minute / 1440.0),
        math.sin(2.0 * math.pi * day / 365.2425),
        math.cos(2.0 * math.pi * day / 365.2425),
        outdoor - air,
        mass - air,
        radiation / 1000.0,
        solar_sin,
        float(solar_sin > 0.0),
    )
    if not all(math.isfinite(value) for value in values):
        raise ValueError("behavior features must be finite")
    return values


def _binary(value):
    if value is None:
        return None
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError("action states must be finite when known")
    return numeric > 0.0


def _transition_rows(samples, transition):
    field, at_risk_state, target_state = _TRANSITION_STATES[transition]
    ordered = sorted(samples, key=lambda row: _aware(_value(row, "at")))
    design = []
    labels = []
    weights = []
    for left, right in zip(ordered, ordered[1:]):
        if _value(right, "at") - _value(left, "at") != STEP:
            continue
        left_state = _binary(_value(left, field))
        right_state = _binary(_value(right, field))
        if left_state is None or right_state is None:
            continue
        confidence = float(_value(right, "action_confidence"))
        if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
            raise ValueError("action confidence must be finite and within [0, 1]")
        # Same-fold model-inferred labels are intentionally excluded.  Historical
        # reconstruction (0.35) is the lowest accepted source in this task.
        if confidence < MIN_TRAINING_CONFIDENCE:
            continue
        design.append(feature_vector(left))
        labels.append(float(left_state == at_risk_state and right_state == target_state))
        weights.append(confidence)
    return (
        np.asarray(design, dtype=float),
        np.asarray(labels, dtype=float),
        np.asarray(weights, dtype=float),
    )


def _sigmoid(values):
    values = np.asarray(values, dtype=float)
    result = np.empty_like(values)
    positive = values >= 0.0
    result[positive] = 1.0 / (1.0 + np.exp(-values[positive]))
    exp_values = np.exp(values[~positive])
    result[~positive] = exp_values / (1.0 + exp_values)
    return result


def _fit_coefficients(design, labels, weights):
    if len(labels) == 0 or int(np.count_nonzero(labels)) < MIN_POSITIVES:
        return ()
    if np.all(labels == labels[0]):
        return ()

    def objective(coefficients):
        logits = design @ coefficients
        likelihood = np.sum(weights * (np.logaddexp(0.0, logits) - labels * logits))
        penalty = 0.5 * RIDGE_LAMBDA * float(coefficients[1:] @ coefficients[1:])
        return float(likelihood + penalty)

    def gradient(coefficients):
        residual = weights * (_sigmoid(design @ coefficients) - labels)
        result = design.T @ residual
        result[1:] += RIDGE_LAMBDA * coefficients[1:]
        return result

    result = minimize(
        objective,
        np.zeros(len(FEATURE_NAMES), dtype=float),
        jac=gradient,
        method="L-BFGS-B",
    )
    if not result.success or not np.isfinite(result.x).all():
        raise ValueError(f"behavior optimizer failed: {result.message}")
    return tuple(float(value) for value in result.x)


def fit_behavior(samples):
    """Fit six weighted transition hazards without using future-row features."""
    rows = tuple(samples)
    transitions = {}
    for transition in TRANSITIONS:
        design, labels, weights = _transition_rows(rows, transition)
        transitions[transition] = _fit_coefficients(design, labels, weights)
    return BehaviorModel(
        version=1,
        feature_names=FEATURE_NAMES,
        transitions=transitions,
    )


def transition_probability(model, transition, features):
    """Return a fitted probability, or the explicit insufficient-data sentinel."""
    if transition not in model.transitions:
        raise ValueError(f"unknown transition: {transition}")
    coefficients = model.transitions[transition]
    if not coefficients:
        return INSUFFICIENT_DATA
    if tuple(model.feature_names) != FEATURE_NAMES:
        raise ValueError("behavior model feature order is incompatible")
    if isinstance(features, Mapping):
        values = tuple(float(features[name]) for name in model.feature_names)
    else:
        values = tuple(float(value) for value in features)
    if len(values) != len(coefficients) or not all(math.isfinite(v) for v in values):
        raise ValueError("transition features must be finite and match model order")
    logit = sum(coefficient * value for coefficient, value in zip(coefficients, values))
    if logit >= 0.0:
        return float(1.0 / (1.0 + math.exp(-logit)))
    exp_logit = math.exp(logit)
    return float(exp_logit / (1.0 + exp_logit))


def _forecast_rows(forecast):
    rows = tuple(sorted(forecast, key=lambda row: _aware(_value(row, "at"))))
    if not rows:
        raise ValueError("forecast must not be empty")
    return rows


def _mode(rows):
    mode = str(_first_value(rows[0], ("mode", "season"), default=""))
    if mode not in {"spring", "warm", "fall_charge", "winter"}:
        raise ValueError("forecast mode must be spring, warm, fall_charge, or winter")
    return mode


def _round_quarter(minute):
    return int((int(minute) + 7) // 15 * 15) % 1440


def _learned_minute(model, transition, rows, default):
    if not model.transitions.get(transition):
        return default
    scored = []
    for row in rows:
        minute = int(_minute_of_day(_value(row, "at")))
        if transition == "vent_open" and minute < 12 * 60:
            continue
        if transition == "vent_close" and minute >= 12 * 60:
            continue
        probability = transition_probability(model, transition, feature_vector(row))
        scored.append((float(probability), minute))
    if not scored:
        return default
    total_probability = sum(probability for probability, _ in scored)
    if total_probability <= 0.0:
        return default
    expected_minute = sum(
        probability * minute for probability, minute in scored
    ) / total_probability
    return int(round(expected_minute)) % 1440


def _seasonal_outdoor_shade(rows, mode):
    state = _value(rows[0], "outdoor_shade_present", None)
    if state is None:
        return "present" if mode == "warm" else "absent"
    return "present" if _binary(state) else "absent"


def _time_at_or_after(rows, minute, after=None):
    eligible = [row for row in rows if after is None or _value(row, "at") > after]
    exact = [
        _value(row, "at")
        for row in eligible
        if int(_minute_of_day(_value(row, "at"))) == minute
    ]
    if exact:
        return exact[0]
    if not eligible:
        return None
    return min(
        (_value(row, "at") for row in eligible),
        key=lambda at: abs((at.hour * 60 + at.minute) - minute),
    )


def _vent_times(rows, open_minute, close_minute):
    opened = _time_at_or_after(rows, open_minute)
    if opened is None:
        return None, None
    closed = _time_at_or_after(rows, close_minute, after=opened)
    return opened, closed


def baseline_schedule(model, forecast):
    """Return the learned household baseline constrained by seasonal protocol."""
    rows = _forecast_rows(forecast)
    mode = _mode(rows)
    outdoor_shade = _seasonal_outdoor_shade(rows, mode)
    common = {
        "mode": mode,
        "outdoorShade": outdoor_shade,
        "supportedAirflow": dict(AIRFLOW_LEVELS),
    }
    if mode == "winter":
        daylight = [row for row in rows if _solar_elevation_sin(_value(row, "at")) > 0.0]
        sunny = bool(daylight) and max(float(_value(row, "radiation_wm2")) for row in daylight) >= SUNNY_RADIATION_WM2
        if sunny:
            useful = [row for row in daylight if float(_value(row, "radiation_wm2")) >= SUNNY_RADIATION_WM2]
            shade_open = _value(useful[0], "at") if useful else None
            shade_close = _value(useful[-1], "at") + STEP if useful else None
        else:
            shade_open = None
            shade_close = None
        return {
            **common,
            "vent": "closed",
            "ventFlow": "closed",
            "ventForcing": AIRFLOW_LEVELS["closed"],
            "ventOpenMinute": None,
            "ventCloseMinute": None,
            "ventOpenAt": None,
            "ventCloseAt": None,
            "airflowSegments": (),
            "indoorShadeDay": "open" if sunny else "closed",
            "indoorShadeNight": "closed",
            "shadeOpenAt": shade_open,
            "shadeCloseAt": shade_close,
        }

    open_minute = _round_quarter(_learned_minute(model, "vent_open", rows, 1230))
    close_minute = _round_quarter(_learned_minute(model, "vent_close", rows, 420))
    opened, closed = _vent_times(rows, open_minute, close_minute)
    if opened is None or closed is None:
        raise ValueError("forecast must span a complete learned overnight vent window")
    # Warm-season nightly venting is household baseline behavior, not an on/off
    # optimization.  Shoulder schedules use the same representational vocabulary.
    airflow = ({"startAt": opened, "endAt": closed, "level": "baseline"},)
    return {
        **common,
        "vent": "open",
        "ventFlow": "baseline",
        "ventForcing": AIRFLOW_LEVELS["baseline"],
        "ventOpenMinute": open_minute,
        "ventCloseMinute": close_minute,
        "ventOpenAt": opened,
        "ventCloseAt": closed,
        "airflowSegments": airflow,
        "indoorShadeDay": "closed" if mode == "warm" else "open",
        "indoorShadeNight": "closed",
        "shadeOpenAt": None,
        "shadeCloseAt": None,
    }


@dataclass(frozen=True)
class ScheduleSearchResult(Mapping):
    baseline: dict
    candidate: dict
    modeled_difference: dict
    rejected_candidate_counts: dict

    @property
    def vent_open_at(self):
        return self.candidate.get("ventOpenAt")

    @property
    def vent_close_at(self):
        return self.candidate.get("ventCloseAt")

    def __getitem__(self, key):
        return {
            "baseline": self.baseline,
            "candidate": self.candidate,
            "modeledDifference": self.modeled_difference,
            "rejectedCandidateCounts": self.rejected_candidate_counts,
        }[key]

    def __iter__(self):
        return iter(("baseline", "candidate", "modeledDifference", "rejectedCandidateCounts"))

    def __len__(self):
        return 4


def _candidate_schedule(baseline, rows, open_minute, close_minute):
    opened, closed = _vent_times(rows, open_minute, close_minute)
    if opened is None or closed is None:
        return None
    candidate = dict(baseline)
    candidate.update(
        {
            "ventOpenMinute": open_minute,
            "ventCloseMinute": close_minute,
            "ventOpenAt": opened,
            "ventCloseAt": closed,
            "airflowSegments": (
                {"startAt": opened, "endAt": closed, "level": "baseline"},
            ),
        }
    )
    return candidate


def _window_rows(rows, schedule):
    opened = schedule.get("ventOpenAt")
    closed = schedule.get("ventCloseAt")
    if opened is None or closed is None:
        return ()
    return tuple(row for row in rows if opened <= _value(row, "at") < closed)


def _physical_rejection(rows, schedule):
    window = _window_rows(rows, schedule)
    if len(window) < 12:
        return "outside_forecast_horizon"
    first_hour = window[:12]
    if any(
        float(_value(row, "outdoor_f"))
        > float(_first_value(row, ("air_baseline_f", "air_f"))) - 1.0
        for row in first_hour
    ):
        return "outside_not_cool_for_hour"
    if any(
        float(_value(row, "outdoor_f"))
        >= float(_first_value(row, ("air_baseline_f", "air_f")))
        for row in window
    ):
        return "warmer_outdoor_air"
    return None


def _forcing_rows(rows, schedule):
    opened = schedule.get("ventOpenAt")
    closed = schedule.get("ventCloseAt")
    winter = schedule["mode"] == "winter"
    sunny_winter = winter and schedule["indoorShadeDay"] == "open"
    outdoor_present = float(schedule["outdoorShade"] == "present")
    forcings = []
    for row in rows[1:]:
        at = _value(row, "at")
        vent = (
            AIRFLOW_LEVELS[schedule["ventFlow"]]
            if opened is not None and closed is not None and opened <= at < closed
            else AIRFLOW_LEVELS["closed"]
        )
        if sunny_winter:
            indoor_closed = float(
                not (
                    schedule["shadeOpenAt"] is not None
                    and schedule["shadeOpenAt"] <= at < schedule["shadeCloseAt"]
                )
            )
        elif winter or schedule["indoorShadeDay"] == "closed":
            indoor_closed = 1.0
        else:
            indoor_closed = float(_value(row, "indoor_shade_closed", 0.0))
        forcings.append(
            {
                "outdoor_f": float(_value(row, "outdoor_f")),
                "radiation_wm2": float(_value(row, "radiation_wm2")),
                "vent_open": vent,
                "indoor_shade_closed": indoor_closed,
                "outdoor_shade_present": outdoor_present,
            }
        )
    return forcings


def _simulation(model, rows, schedule):
    initial = {
        "air_f": float(_first_value(rows[0], ("air_baseline_f", "air_f"))),
        "mass_f": float(_first_value(rows[0], ("mass_baseline_f", "mass_f"))),
    }
    return simulate(model, initial, _forcing_rows(rows, schedule))


def _morning_mass(rows, predicted):
    aligned = tuple(zip(rows[1:], predicted))
    morning = [
        result["mass_f"]
        for row, result in aligned
        if 360 <= _minute_of_day(_value(row, "at")) <= 540
    ]
    return float(morning[-1] if morning else predicted[-1]["mass_f"])


def _score(mode, rows, predicted):
    air = [float(row["air_f"]) for row in predicted]
    mass = _morning_mass(rows, predicted)
    if mode == "warm":
        return max(0.0, max(air) - 82.0) * 4.0 + mass
    if mode == "winter":
        hours_below = sum(value < 60.0 for value in air) * STEP.total_seconds() / 3600.0
        return hours_below * 4.0 - mass
    discomfort = sum(max(0.0, 60.0 - value) + max(0.0, value - 82.0) for value in air)
    discomfort *= STEP.total_seconds() / 3600.0
    return discomfort - 0.5 * mass


def _difference(baseline_score, candidate_score):
    improvement = float(baseline_score - candidate_score)
    return {
        "kind": "modeled_counterfactual",
        "description": "Simulation comparison between the learned baseline and bounded candidate.",
        "baselineScore": float(baseline_score),
        "candidateScore": float(candidate_score),
        "scoreImprovement": improvement,
    }


def search_candidate_schedule(*, behavior, dynamics, forecast):
    """Compare nearby schedules with pure simulation; never emit commands or advice."""
    rows = _forecast_rows(forecast)
    baseline = baseline_schedule(behavior, rows)
    mode = baseline["mode"]
    if mode == "winter":
        score = _score(mode, rows, _simulation(dynamics, rows, baseline))
        return ScheduleSearchResult(
            baseline=baseline,
            candidate=dict(baseline),
            modeled_difference=_difference(score, score),
            rejected_candidate_counts={},
        )

    baseline_prediction = _simulation(dynamics, rows, baseline)
    baseline_score = _score(mode, rows, baseline_prediction)
    rejected = Counter()
    surviving = []
    open_center = _round_quarter(baseline["ventOpenMinute"])
    close_center = _round_quarter(baseline["ventCloseMinute"])
    seen = set()
    for open_offset in range(-120, 121, 15):
        for close_offset in range(-120, 121, 15):
            open_minute = (open_center + open_offset) % 1440
            close_minute = (close_center + close_offset) % 1440
            key = (open_minute, close_minute)
            if key in seen:
                continue
            seen.add(key)
            candidate = _candidate_schedule(baseline, rows, open_minute, close_minute)
            if candidate is None:
                rejected["outside_forecast_horizon"] += 1
                continue
            reason = _physical_rejection(rows, candidate)
            if reason is not None:
                rejected[reason] += 1
                continue
            try:
                score = _score(mode, rows, _simulation(dynamics, rows, candidate))
            except ValueError:
                rejected["simulation_invalid"] += 1
                continue
            surviving.append((score, open_minute, close_minute, candidate))

    baseline_reason = _physical_rejection(rows, baseline)
    if not surviving:
        selected = baseline
        selected_score = baseline_score
    else:
        best_score, _, _, best = min(
            surviving,
            key=lambda item: (item[0], item[1], item[2]),
        )
        if baseline_reason is not None or baseline_score - best_score >= MINIMUM_IMPROVEMENT:
            selected = best
            selected_score = best_score
        else:
            selected = baseline
            selected_score = baseline_score
    return ScheduleSearchResult(
        baseline=baseline,
        candidate=selected,
        modeled_difference=_difference(baseline_score, selected_score),
        rejected_candidate_counts=dict(sorted(rejected.items())),
    )
