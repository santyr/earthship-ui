"""Offline solar/season residual comparison; never a live forecast publisher.

All variants share the same raw, archived weather forecast. This tests residual
corrections, not the production Kalman correction or a physical thermal model.
The fitted corrections are frozen before the first held-out origin.
"""

from datetime import timedelta
from hashlib import sha256
import json
import math

import numpy as np

SEASONS = ('SPRING', 'SUMMER', 'AUTUMN', 'WINTER')
VARIANTS = ('raw', 'bias', 'season', 'daylight', 'daylight_and_season')
FIELDS = frozenset(('origin', 'target', 'forecast_f', 'actual_f',
                    'daylight_hours', 'season', 'outcome_stored_at',
                    'forecast_sha256', 'solar_sha256', 'outcome_sha256'))


def _features(row, variant):
    features = []
    if 'daylight' in variant:
        features.append(row['daylight_hours'])
    if 'season' in variant:
        features.extend(float(row['season'] == season) for season in SEASONS)
    return features


def _validate(rows):
    if not isinstance(rows, (list, tuple)) or not 1 <= len(rows) <= 31:
        raise ValueError('bounded paired daily rows required')
    previous = None
    for row in rows:
        if not isinstance(row, dict) or set(row) != FIELDS:
            raise ValueError('closed paired row required')
        for key in ('origin', 'target', 'outcome_stored_at'):
            at = row[key]
            if not hasattr(at, 'utcoffset') or at.utcoffset() is None:
                raise ValueError('aware pair timestamps required')
        if (row['target'] - row['origin'] != timedelta(hours=24)
                or row['outcome_stored_at'] > row['target']
                or (previous is not None and row['origin'] - previous < timedelta(hours=24))):
            raise ValueError('elapsed nonoverlapping daily pairs required')
        previous = row['origin']
        for key, low, high in (('forecast_f', -40, 140), ('actual_f', -40, 140),
                               ('daylight_hours', 0, 24)):
            value = row[key]
            if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
                raise ValueError('finite paired feature required')
        if row['season'] not in SEASONS:
            raise ValueError('known astronomical season required')
        for key in ('forecast_sha256', 'solar_sha256', 'outcome_sha256'):
            digest = row[key]
            if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
                raise ValueError('paired provenance digest required')


def compare(rows, *, split_at, minimum_train=10, minimum_test=5):
    """Fixed ridge strength and train-only scaling; no holdout tuning or writes."""
    _validate(rows)
    if not hasattr(split_at, 'utcoffset') or split_at.utcoffset() is None:
        raise ValueError('aware frozen split required')
    if any(type(value) is not int or value < 5 for value in (minimum_train, minimum_test)):
        raise ValueError('at least five independent days per partition required')
    train = [row for row in rows if row['origin'] < split_at
             and row['target'] <= split_at and row['outcome_stored_at'] <= split_at]
    test = [row for row in rows if row['origin'] >= split_at]
    serial = [{k: v.isoformat() if hasattr(v, 'isoformat') else v for k, v in row.items()}
              for row in rows]
    report = {'scope': 'offline_raw_outdoor_temperature_residual_ablation',
              'production_changed': False, 'seasonal_skill_proven': False,
              'split_at': split_at.isoformat(), 'paired_days': len(rows),
              'train_days': len(train), 'test_days': len(test),
              'minimum_train_days': minimum_train, 'minimum_test_days': minimum_test,
              'pair_sha256': sha256(json.dumps(serial, sort_keys=True,
                  separators=(',', ':'), allow_nan=False).encode()).hexdigest()}
    # Unfitted archived-forecast accuracy needs no training sample. Keep it
    # separate from the comparison, which may be withheld for insufficient fit.
    raw_errors = [row['forecast_f'] - row['actual_f'] for row in test]
    report['raw_test_baseline'] = {'count': len(test),
        'mae_f': sum(abs(value) for value in raw_errors) / len(test) if test else None,
        'bias_f': sum(raw_errors) / len(test) if test else None}
    if len(train) < minimum_train or len(test) < minimum_test:
        return dict(report, status='withheld_insufficient_pairs', variants={})
    y = np.array([row['actual_f'] - row['forecast_f'] for row in train])
    metrics = {}
    for variant in VARIANTS:
        if variant == 'raw':
            corrections = np.zeros(len(test))
        else:
            x = np.array([_features(row, variant) for row in train], dtype=float)
            xt = np.array([_features(row, variant) for row in test], dtype=float)
            center = x.mean(axis=0)
            scale = x.std(axis=0)
            # A constant training feature contributes nothing on holdout;
            # in particular, an unseen season cannot acquire a fitted effect.
            varying = scale > 1e-9
            z = (x[:, varying] - center[varying]) / scale[varying]
            zt = (xt[:, varying] - center[varying]) / scale[varying]
            design = np.column_stack((np.ones(len(train)), z))
            penalty = np.eye(design.shape[1]); penalty[0, 0] = 0.0
            coefficients = np.linalg.solve(design.T @ design + penalty, design.T @ y)
            corrections = np.column_stack((np.ones(len(test)), zt)) @ coefficients
        errors = np.array([row['forecast_f'] - row['actual_f'] for row in test]) + corrections
        metrics[variant] = {'mae_f': float(np.abs(errors).mean()),
                            'bias_f': float(errors.mean()),
                            'max_absolute_error_f': float(np.abs(errors).max())}
    train_seasons = sorted({row['season'] for row in train})
    test_seasons = sorted({row['season'] for row in test})
    return dict(report, status='shadow_comparison', variants=metrics,
                train_seasons=train_seasons, test_seasons=test_seasons,
                unseen_test_seasons=sorted(set(test_seasons) - set(train_seasons)),
                train_daylight_range_hours=[min(r['daylight_hours'] for r in train),
                                            max(r['daylight_hours'] for r in train)],
                test_daylight_range_hours=[min(r['daylight_hours'] for r in test),
                                           max(r['daylight_hours'] for r in test)],
                ridge_strength=1.0, train_only_standardization=True)
