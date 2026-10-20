"""Read an explicitly selected provisional PV experiment, never auto-qualify it."""
from pathlib import Path
from hashlib import sha256
from datetime import timedelta
import json
from weather_source_files import _read
from .contracts import identity,instant
from .pv_directional_calibration import validate_model


def load_calibration(path,*,origin,system_raw,horizon_raw):
    return restore_calibration(_read(path,262144),origin=origin,system_raw=system_raw,horizon_raw=horizon_raw)


def restore_calibration(raw,*,origin,system_raw,horizon_raw):
    if not isinstance(raw,bytes) or len(raw)>262144:raise ValueError('bounded retained calibration bytes required')
    value=json.loads(raw)
    if (value.get('schema')!='earthship-historical-pv-directional-experiment/v1' or value.get('automatic_actuation') is not False or
        value.get('receipt_sha256')!=identity({k:v for k,v in value.items() if k!='receipt_sha256'})):raise ValueError('unchanged selected PV experiment required')
    model=validate_model(value['final_model']);report=value['report']
    if (report.get('report_sha256')!=identity({k:v for k,v in report.items() if k!='report_sha256'}) or
        report.get('model_sha256')!=value['training_model_sha256'] or report.get('selected') is not True or
        report.get('prospective_score') is not False or report.get('physical_calibration_qualified') is not False or
        report.get('automatic_actuation') is not False or report['candidate_mae_w']>=report['baseline_mae_w']):raise ValueError('original improved provisional comparison required')
    if not instant(model['trained_at'])<=origin<instant(model['trained_at'])+timedelta(days=14) or instant(value['created_at'])>origin:
        raise ValueError('PV calibration is unavailable or expired at origin')
    if value['system_raw'].encode()!=system_raw or value['horizon_raw'].encode()!=horizon_raw:raise ValueError('PV calibration geometry declaration changed')
    scripts=Path(__file__).resolve().parents[1]
    for name in ('weather_learning/pv_directional_calibration.py','weather_learning/pv_calibration.py','weather_learning/contracts.py'):
        key='openhab/scripts/'+name
        if key not in value['runtime_manifest'] or value['runtime_manifest'][key]!=sha256((scripts/name).read_bytes()).hexdigest():raise ValueError('PV calibration numerical runtime changed')
        if name.endswith('pv_directional_calibration.py') and key not in value['runtime_manifest']:raise ValueError('PV calibration numerical runtime missing')
    return dict(model=model,report=report,original=value,original_file_sha256=sha256(raw).hexdigest())
