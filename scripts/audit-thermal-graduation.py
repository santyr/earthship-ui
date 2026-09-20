#!/usr/bin/env python3
"""Read-only graduation evidence report; never load the mutable model registry."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'openhab/scripts'))
from thermal_model.artifacts import (
    PERSISTENCE_MAE_TOLERANCE_F, _artifact_from_payload,
    _validate_backtest_report, validate_artifact,
)


def summarize(metrics):
    rows = []
    for horizon, model in sorted(metrics['overall']['model']['air'].items(), key=lambda pair: int(pair[0])):
        persistence = metrics['overall']['persistence']['air'][horizon]
        recent = metrics['overall']['recent_cycle']['air'][horizon]
        interval = metrics['prediction_interval_coverage']['air'].get(horizon, {})
        comparable = model['count'] > 0 and model['count'] == persistence['count'] == recent['count']
        rows.append({'hours': int(horizon), 'count': model['count'],
            'model_mae_f': model['mae'], 'persistence_mae_f': persistence['mae'],
            'recent_cycle_mae_f': recent['mae'], 'bias_f': model['bias'],
            'strictly_beats_both_baselines': comparable and model['mae'] < min(persistence['mae'], recent['mae']),
            'interval_coverage': interval.get('fraction'), 'nominal_coverage': interval.get('nominal'),
            'interval_count': interval.get('count', 0)})
    regimes = {name: {method: values[method]['air']['24'] for method in ('model', 'persistence', 'recent_cycle')}
               for name, values in metrics['by_regime'].items()}
    return {'advisory_graduation_claimed': False,
        'shadow_acceptance': metrics['promotion'],
        'shadow_mae_tolerance_f': PERSISTENCE_MAE_TOLERANCE_F,
        'air_forecast_comparisons': rows, 'air_24h_by_regime': regimes,
        'confirmed_action_evidence': metrics['action_evidence']['confirmed'],
        'behavior_metrics': metrics['behavior'],
        'interpretation': 'Descriptive audit, not release thresholds. Shadow acceptance is not advisory graduation.'}


def audit(directory):
    paths = [directory / 'accepted.json', directory / 'backtest-report.json']
    bodies = [path.read_bytes() for path in paths]
    model, report = map(json.loads, bodies)
    validate_artifact(_artifact_from_payload(model))
    _validate_backtest_report(report)
    if model['metrics'] != report['metrics']:
        raise ValueError('accepted artifact and backtest metrics differ')
    result = summarize(report['metrics'])
    result['inputs_sha256'] = {path.name: hashlib.sha256(body).hexdigest() for path, body in zip(paths, bodies)}
    result['trained_through'] = model['trained_through']
    result['data_range'] = report['data_range']
    if any(path.read_bytes() != body for path, body in zip(paths, bodies)):
        raise ValueError('model/report changed during audit; retry after training completes')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-dir', type=Path, default=Path('/home/sat/.local/state/thermal-intel/models'))
    print(json.dumps(audit(parser.parse_args().model_dir), indent=2, sort_keys=True, allow_nan=False))
