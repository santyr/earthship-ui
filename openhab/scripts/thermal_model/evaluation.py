"""Strictly chronological evaluation for the non-actuating thermal shadow."""

from collections import Counter, defaultdict
from datetime import timedelta, timezone
import math
from statistics import median
from zoneinfo import ZoneInfo

from .behavior import (
    FEATURE_NAMES,
    MIN_TRAINING_CONFIDENCE,
    TRANSITIONS,
    feature_vector,
    transition_probability,
)
from .artifacts import (
    BACKTEST_SCHEMA,
    provisional_promotion_gates,
    valid_paired_24h_prediction_record,
)
from .dataset import RADIATION_PROVENANCE_LABELS
from .dynamics import evaluation_forcing_features, simulate, validate_physics

STEP = timedelta(minutes=5)
SITE_TIMEZONE = ZoneInfo("America/Denver")
HORIZONS_HOURS = (1, 6, 12, 24, 48, 72)
PROVENANCE_LABELS = (
    "confirmed", "photosensor", "reconstructed", "model_inferred", "unknown"
)
MIN_TRAINING_DAYS = 14
INTERVAL_NOMINAL_COVERAGE = 0.90
_TRANSITION_STATES = {
    "vent_open": ("vent_open", False, True, "vent_confidence"),
    "vent_close": ("vent_open", True, False, "vent_confidence"),
    "indoor_shade_open": (
        "indoor_shade_closed", True, False, "indoor_shade_confidence"
    ),
    "indoor_shade_close": (
        "indoor_shade_closed", False, True, "indoor_shade_confidence"
    ),
    "outdoor_shade_installed": (
        "outdoor_shade_present", False, True, "outdoor_shade_confidence"
    ),
    "outdoor_shade_removed": (
        "outdoor_shade_present", True, False, "outdoor_shade_confidence"
    ),
}


def _iso_utc(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _dynamics(model):
    if hasattr(model, "dynamics"):
        return model.dynamics
    if isinstance(model, dict) and "dynamics" in model:
        return model["dynamics"]
    return model


def _behavior(model):
    if hasattr(model, "behavior"):
        return model.behavior
    if isinstance(model, dict):
        return model.get("behavior")
    return None


def _inactive_forcing_features(model):
    if hasattr(model, "inactive_forcing_features"):
        return tuple(model.inactive_forcing_features)
    if isinstance(model, dict):
        return tuple(model.get("inactive_forcing_features", ()))
    return ()


def _activated_unidentified_features(model, future):
    inactive = _inactive_forcing_features(model)
    activated = set()
    for row in future:
        forcing = evaluation_forcing_features(row)
        activated.update(
            name for name in inactive if forcing.get(name, 0.0) != 0.0
        )
    return tuple(name for name in inactive if name in activated)


def _continuous_future(by_at, origin, hours):
    steps = hours * 12
    timestamps = tuple(origin.at + STEP * index for index in range(1, steps + 1))
    if not all(at in by_at for at in timestamps):
        return None
    return tuple(by_at[at] for at in timestamps)


def _metric(errors):
    values = tuple(float(error) for error in errors)
    if not values:
        return {"count": 0, "mae": None, "rmse": None, "bias": None}
    return {
        "count": len(values),
        "mae": sum(abs(value) for value in values) / len(values),
        "rmse": math.sqrt(sum(value * value for value in values) / len(values)),
        "bias": sum(values) / len(values),
    }


def _method_summary(records, method):
    return {
        state: {
            str(hours): _metric(
                record[method][state]
                for record in records
                if record["horizon"] == hours
                and method in record
                and record[method].get(state) is not None
            )
            for hours in HORIZONS_HOURS
        }
        for state in ("air", "mass")
    }


def _model_summary(records):
    if not records:
        return {}
    return _method_summary(records, "model")


def _regime(mode):
    if mode == "warm":
        return "warm"
    if mode == "winter":
        return "winter"
    return "shoulder"


def _provenance(sample):
    confidence = float(sample.action_confidence)
    if confidence >= 1.0:
        return "confirmed"
    if confidence >= 0.8:
        return "photosensor"
    if confidence >= 0.35:
        return "reconstructed"
    if confidence >= 0.15:
        return "model_inferred"
    return "unknown"


def _recent_cycle_prediction(by_at, origin, hours, state):
    local_origin = origin.at.astimezone(SITE_TIMEZONE)
    deltas = []
    for lag_days in range(1, 32):
        prior_at = local_origin - timedelta(days=lag_days)
        target_at = prior_at + timedelta(hours=hours)
        if target_at.astimezone(timezone.utc) >= origin.at.astimezone(timezone.utc):
            continue
        prior = by_at.get(prior_at)
        target = by_at.get(target_at)
        if prior is None or target is None:
            continue
        deltas.append(getattr(target, f"{state}_f") - getattr(prior, f"{state}_f"))
        if len(deltas) == 7:
            break
    if not deltas:
        return None
    return float(getattr(origin, f"{state}_f") + median(deltas))


def _quantile(values, probability):
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise ValueError("quantile requires values")
    position = (len(ordered) - 1) * probability
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _interval_coverage(records):
    results = defaultdict(lambda: {"count": 0, "covered": 0})
    for record in records:
        for state in ("air", "mass"):
            key = (state, record["horizon"])
            error = record["model"][state]
            history = [
                prior["model"][state]
                for prior in records
                if prior["horizon"] == record["horizon"]
                and prior["target_at"] <= record["origin_at"]
            ]
            if history:
                low = _quantile(history, 0.05)
                high = _quantile(history, 0.95)
                results[key]["count"] += 1
                results[key]["covered"] += int(low <= error <= high)
    return {
        state: {
            str(hours): {
                "nominal": INTERVAL_NOMINAL_COVERAGE,
                "count": results[(state, hours)]["count"],
                "covered": results[(state, hours)]["covered"],
                "fraction": (
                    results[(state, hours)]["covered"]
                    / results[(state, hours)]["count"]
                    if results[(state, hours)]["count"]
                    else None
                ),
                "calibration": "prior_fold_signed_error_quantiles",
            }
            for hours in HORIZONS_HOURS
        }
        for state in ("air", "mass")
    }


def _daily_metrics(daily_records):
    return {
        "hallway_high_f": _metric(row["hallway_high_f"] for row in daily_records),
        "hallway_low_f": _metric(row["hallway_low_f"] for row in daily_records),
        "peak_time_minutes": _metric(
            row["peak_time_minutes"] for row in daily_records
        ),
        "morning_mass_f": _metric(
            row["morning_mass_f"]
            for row in daily_records
            if row["morning_mass_f"] is not None
        ),
    }


def threshold_advisory(tomorrow_high_f, three_day_average_high_f=None):
    """Pure copy of the existing corrected outdoor-high classification branch."""
    tomorrow = float(tomorrow_high_f)
    streak = (
        None
        if three_day_average_high_f is None
        else float(three_day_average_high_f)
    )
    if not math.isfinite(tomorrow) or (
        streak is not None and not math.isfinite(streak)
    ):
        raise ValueError("threshold baseline inputs must be finite")
    if tomorrow >= 95.0 or (streak is not None and streak >= 92.0):
        return "close_up_tomorrow"
    if tomorrow >= 90.0:
        return "vent_tonight"
    return "none"


def _threshold_metrics(rows):
    counts = Counter(row["classification"] for row in rows)
    true_positive = sum(
        row["classification"] != "none" and row["observed_hot"] for row in rows
    )
    false_positive = sum(
        row["classification"] != "none" and not row["observed_hot"] for row in rows
    )
    false_negative = sum(
        row["classification"] == "none" and row["observed_hot"] for row in rows
    )
    return {
        "definition": {
            "close_up_tomorrow": "tomorrow_high_f >= 95 or three_day_average_high_f >= 92",
            "vent_tonight": "90 <= tomorrow_high_f < 95 unless close_up_tomorrow",
            "none": "otherwise",
        },
        "input": "held_out_outdoor_high_proxy",
        "class_counts": {
            name: counts.get(name, 0)
            for name in ("none", "vent_tonight", "close_up_tomorrow")
        },
        "comparison_target": "held_out_hallway_high_f >= 82",
        "precision": (
            true_positive / (true_positive + false_positive)
            if true_positive + false_positive
            else None
        ),
        "recall": (
            true_positive / (true_positive + false_negative)
            if true_positive + false_negative
            else None
        ),
        "count": len(rows),
    }


def _binary(value):
    if value is None:
        return None
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("action state must be finite")
    return number > 0.0


def _behavior_fold_metrics(model, origin, future):
    behavior = _behavior(model)
    if behavior is None or tuple(behavior.feature_names) != FEATURE_NAMES:
        return (), ()
    classifications = []
    timing = []
    rows = (origin,) + tuple(future[: 24 * 12])
    for transition in TRANSITIONS:
        coefficients = behavior.transitions.get(transition, ())
        if not coefficients:
            continue
        field, at_risk, target, confidence_field = _TRANSITION_STATES[transition]
        predicted_times = []
        actual_times = []
        for left, right in zip(rows, rows[1:]):
            left_state = _binary(getattr(left, field))
            right_state = _binary(getattr(right, field))
            left_confidence = float(getattr(left, confidence_field))
            right_confidence = float(getattr(right, confidence_field))
            if (
                left_state is None
                or right_state is None
                or left_state != at_risk
                or left_confidence < MIN_TRAINING_CONFIDENCE
                or right_confidence < MIN_TRAINING_CONFIDENCE
            ):
                continue
            actual = right_state == target
            probability = transition_probability(
                behavior, transition, feature_vector(left)
            )
            predicted = float(probability) >= 0.5
            classifications.append((predicted, actual))
            if predicted:
                predicted_times.append(right.at)
            if actual:
                actual_times.append(right.at)
        if predicted_times and actual_times:
            timing.append(
                abs((predicted_times[0] - actual_times[0]).total_seconds()) / 60.0
            )
    return tuple(classifications), tuple(timing)


def _behavior_metrics(classifications, timing):
    if not classifications:
        return {
            "available": False,
            "label_count": 0,
            "precision": None,
            "recall": None,
            "median_timing_error_minutes": None,
            "classification_probability": 0.5,
        }
    true_positive = sum(predicted and actual for predicted, actual in classifications)
    false_positive = sum(predicted and not actual for predicted, actual in classifications)
    false_negative = sum(not predicted and actual for predicted, actual in classifications)
    return {
        "available": True,
        "label_count": len(classifications),
        "precision": (
            true_positive / (true_positive + false_positive)
            if true_positive + false_positive
            else None
        ),
        "recall": (
            true_positive / (true_positive + false_negative)
            if true_positive + false_negative
            else None
        ),
        "median_timing_error_minutes": median(timing) if timing else None,
        "classification_probability": 0.5,
    }


def _numbers_finite(value):
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return True
    if isinstance(value, (int, float)):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(_numbers_finite(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return all(_numbers_finite(item) for item in value)
    return False


def walk_forward_evaluate(samples, fit):
    """Fit daily origins and score only fully observed, strictly future horizons."""
    confirmed_action_rows = frozenset(
        getattr(samples, "confirmed_action_rows", ())
    )
    radiation_provenance_by_at = getattr(
        samples, "radiation_provenance_by_at", None
    )
    ordered = tuple(sorted(samples, key=lambda sample: sample.at))
    if not ordered:
        raise ValueError("walk-forward evaluation requires samples")
    if any(sample.at.tzinfo is None or sample.at.utcoffset() is None for sample in ordered):
        raise ValueError("walk-forward timestamps must include timezone information")
    if len({sample.at for sample in ordered}) != len(ordered):
        raise ValueError("walk-forward timestamps must be unique")
    if radiation_provenance_by_at is None:
        radiation_provenance_by_at = {
            sample.at: "observed" for sample in ordered
        }
    if any(
        radiation_provenance_by_at.get(sample.at)
        not in RADIATION_PROVENANCE_LABELS
        for sample in ordered
    ):
        raise ValueError(
            "walk-forward radiation provenance is outside the closed vocabulary"
        )

    by_at = {sample.at: sample for sample in ordered}
    first_local_day = ordered[0].at.astimezone(SITE_TIMEZONE).date()
    continuous_steps = {}
    for sample in reversed(ordered):
        continuous_steps[sample.at] = 1 + continuous_steps.get(
            sample.at + STEP, 0
        )
    candidates = defaultdict(list)
    for sample in ordered:
        local_day = sample.at.astimezone(SITE_TIMEZONE).date()
        candidates[local_day].append(sample)
    origins = {
        local_day: max(
            rows,
            key=lambda sample: (
                continuous_steps[sample.at],
                -sample.at.timestamp(),
            ),
        )
        for local_day, rows in candidates.items()
    }

    folds = []
    records = []
    daily_records = []
    threshold_rows = []
    behavior_classifications = []
    behavior_timing = []
    physics_valid = True
    scored_folds = 0
    confirmed_training_rows = 0
    confirmed_evaluation_targets = 0
    confirmed_disjoint_folds = 0

    for local_day, origin in sorted(origins.items()):
        if (local_day - first_local_day).days < MIN_TRAINING_DAYS:
            continue
        if origin.at - ordered[0].at < timedelta(days=MIN_TRAINING_DAYS):
            continue
        train = tuple(sample for sample in ordered if sample.at < origin.at)
        available = {
            hours: future
            for hours in HORIZONS_HOURS
            if (future := _continuous_future(by_at, origin, hours)) is not None
        }
        if not train or not available:
            continue

        def action_provenance(sample):
            label = _provenance(sample)
            if label == "confirmed" and sample.at not in confirmed_action_rows:
                return "unknown"
            return label

        training_provenance = Counter(
            action_provenance(sample) for sample in train
        )
        evaluation_targets = available[max(available)]
        evaluation_provenance = Counter(
            action_provenance(sample) for sample in evaluation_targets
        )
        training_radiation = Counter(
            radiation_provenance_by_at[sample.at] for sample in train
        )
        evaluation_radiation = Counter(
            radiation_provenance_by_at[sample.at]
            for sample in evaluation_targets
        )
        fold = {
            "train_start": _iso_utc(train[0].at),
            "train_end": _iso_utc(train[-1].at),
            "prediction_start": _iso_utc(origin.at),
            "prediction_end": _iso_utc(
                origin.at + timedelta(hours=max(available))
            ),
            "horizons_hours": list(available),
            "training_row_count": len(train),
            "evaluation_target_row_count": len(evaluation_targets),
            "radiation_provenance": {
                "training": {
                    label: training_radiation.get(label, 0)
                    for label in RADIATION_PROVENANCE_LABELS
                },
                "evaluation_targets": {
                    label: evaluation_radiation.get(label, 0)
                    for label in RADIATION_PROVENANCE_LABELS
                },
            },
            "action_provenance": {
                "training": {
                    label: training_provenance.get(label, 0)
                    for label in PROVENANCE_LABELS
                },
                "evaluation_targets": {
                    label: evaluation_provenance.get(label, 0)
                    for label in PROVENANCE_LABELS
                },
            },
        }
        try:
            fitted = fit(train)
        except ValueError as exc:
            fold["fit_error"] = str(exc)
            folds.append(fold)
            continue
        try:
            max_future = available[max(available)]
            activated = _activated_unidentified_features(fitted, max_future)
            if activated:
                fold["fit_error"] = (
                    "held-out forcing activates unidentified feature: "
                    + ", ".join(activated)
                )
                fold["inactive_forcing_features"] = list(
                    _inactive_forcing_features(fitted)
                )
                folds.append(fold)
                continue
            inactive = _inactive_forcing_features(fitted)
            if inactive:
                fold["inactive_forcing_features"] = list(inactive)
            validate_physics(_dynamics(fitted))
            predictions = simulate(_dynamics(fitted), origin, max_future)
        except (KeyError, TypeError, ValueError) as exc:
            physics_valid = False
            fold["model_error"] = str(exc)
            folds.append(fold)
            continue

        scored_folds += 1
        training_confirmed = training_provenance.get("confirmed", 0)
        evaluation_confirmed = evaluation_provenance.get("confirmed", 0)
        confirmed_training_rows += training_confirmed
        confirmed_evaluation_targets += evaluation_confirmed
        if training_confirmed > 0 and evaluation_confirmed > 0:
            confirmed_disjoint_folds += 1
        folds.append(fold)
        for hours, future in available.items():
            target = future[-1]
            prediction = predictions[hours * 12 - 1]
            record = {
                "origin_at": origin.at,
                "target_at": target.at,
                "horizon": hours,
                "regime": _regime(target.mode),
                "provenance": _provenance(target),
                "model": {
                    "air": prediction["air_f"] - target.air_f,
                    "mass": prediction["mass_f"] - target.mass_f,
                },
                "persistence": {
                    "air": origin.air_f - target.air_f,
                    "mass": origin.mass_f - target.mass_f,
                },
            }
            recent_air = _recent_cycle_prediction(
                by_at, origin, hours, "air"
            )
            recent_mass = _recent_cycle_prediction(
                by_at, origin, hours, "mass"
            )
            if recent_air is not None and recent_mass is not None:
                record["recent_cycle"] = {
                    "air": recent_air - target.air_f,
                    "mass": recent_mass - target.mass_f,
                }
            records.append(record)

        if 24 in available:
            actual_day = available[24]
            predicted_day = predictions[: 24 * 12]
            actual_air = [row.air_f for row in actual_day]
            predicted_air = [row["air_f"] for row in predicted_day]
            actual_high_index = max(range(len(actual_air)), key=actual_air.__getitem__)
            predicted_high_index = max(
                range(len(predicted_air)), key=predicted_air.__getitem__
            )
            morning_index = next(
                (
                    index
                    for index, row in enumerate(actual_day)
                    if row.at.astimezone(SITE_TIMEZONE).hour == 7
                    and row.at.astimezone(SITE_TIMEZONE).minute == 0
                ),
                None,
            )
            daily_records.append(
                {
                    "hallway_high_f": max(predicted_air) - max(actual_air),
                    "hallway_low_f": min(predicted_air) - min(actual_air),
                    "peak_time_minutes": (
                        predicted_high_index - actual_high_index
                    ) * 5.0,
                    "morning_mass_f": (
                        predicted_day[morning_index]["mass_f"]
                        - actual_day[morning_index].mass_f
                        if morning_index is not None
                        else None
                    ),
                }
            )
            day_highs = []
            if 72 in available:
                for day_index in range(3):
                    segment = available[72][
                        day_index * 24 * 12 : (day_index + 1) * 24 * 12
                    ]
                    day_highs.append(max(row.outdoor_f for row in segment))
            tomorrow_high = max(row.outdoor_f for row in actual_day)
            threshold_rows.append(
                {
                    "classification": threshold_advisory(
                        tomorrow_high,
                        sum(day_highs) / len(day_highs) if day_highs else None,
                    ),
                    "observed_hot": max(actual_air) >= 82.0,
                }
            )

        classifications, timing = _behavior_fold_metrics(
            fitted, origin, available[max(available)]
        )
        behavior_classifications.extend(classifications)
        behavior_timing.extend(timing)

    fold_by_origin = {fold["prediction_start"]: fold for fold in folds}
    valid_24h_records = [
        record
        for record in records
        if valid_paired_24h_prediction_record(
            record, fold_by_origin.get(_iso_utc(record["origin_at"]), {})
        )
    ]
    scored_24h_by_regime = Counter(
        record["regime"] for record in valid_24h_records
    )
    overall = {
        method: _method_summary(records, method)
        for method in ("model", "persistence", "recent_cycle")
    }
    by_regime = {
        regime: {
            method: _method_summary(
                [record for record in records if record["regime"] == regime],
                method,
            )
            for method in ("model", "persistence", "recent_cycle")
        }
        for regime in ("warm", "winter", "shoulder")
    }
    provenances = PROVENANCE_LABELS
    by_provenance = {
        provenance: _model_summary(
            [
                record
                for record in records
                if record["provenance"] == provenance
            ]
        )
        for provenance in provenances
    }
    by_horizon = {
        str(hours): {
            state: _metric(
                record["model"][state]
                for record in records
                if record["horizon"] == hours
            )
            for state in ("air", "mass")
        }
        for hours in HORIZONS_HOURS
    }
    metrics = {
        "fold_count": len(folds),
        "scored_fold_count": scored_folds,
        "overall": overall,
        "by_regime": by_regime,
        "by_horizon": by_horizon,
        "by_provenance": by_provenance,
        "action_evidence": {
            "confirmed": {
                "training_rows": confirmed_training_rows,
                "evaluation_targets": confirmed_evaluation_targets,
                "disjoint_fold_count": confirmed_disjoint_folds,
            }
        },
        "daily": _daily_metrics(daily_records),
        "prediction_interval_coverage": _interval_coverage(records),
        "behavior": _behavior_metrics(
            behavior_classifications, behavior_timing
        ),
        "threshold_baseline": _threshold_metrics(threshold_rows),
        "recent_cycle_definition": (
            "median delta from the seven most recent completed local-day "
            "trajectories whose targets precede the forecast origin"
        ),
    }
    model_24 = overall["model"]["air"]["24"]
    persistence_24 = overall["persistence"]["air"]["24"]
    gates = provisional_promotion_gates(
        physics_valid=physics_valid,
        finite_metrics=_numbers_finite(metrics),
        scored_fold_count=scored_folds,
        model_24=model_24,
        persistence_24=persistence_24,
        scored_24h_by_regime={
            regime: scored_24h_by_regime.get(regime, 0)
            for regime in ("warm", "winter", "shoulder")
        },
    )
    metrics["promotion"] = {
        "eligible": all(gates.values()),
        "shadow_only": True,
        "gates": gates,
        "graduation_thresholds": None,
    }
    return {
        "schema": BACKTEST_SCHEMA,
        "generated_at": _iso_utc(ordered[-1].at),
        "data_range": {
            "start": _iso_utc(ordered[0].at),
            "end": _iso_utc(ordered[-1].at + STEP),
        },
        "folds": folds,
        "prediction_records": [
            {
                "origin_at": _iso_utc(record["origin_at"]),
                "target_at": _iso_utc(record["target_at"]),
                "horizon": record["horizon"],
                "regime": record["regime"],
                "provenance": record["provenance"],
                "model": record["model"],
                "persistence": record["persistence"],
                **(
                    {"recent_cycle": record["recent_cycle"]}
                    if "recent_cycle" in record
                    else {}
                ),
            }
            for record in records
        ],
        "metrics": metrics,
    }
