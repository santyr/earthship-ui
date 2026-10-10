#!/usr/bin/env python3
"""Check private settings or derive and preregister raw development thresholds."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from time import monotonic
from thermal_installed_calibrate import _clock,_private_bytes,_time,_index,_resource_preflight

SCHEMA='earthship-installed-shade-registration-config/v1'
FIELDS={'schema','candidate_path','candidate_sha256','runtime_bundle_path','runtime_sha256',
    'raw_sources_path','raw_sources_sha256','intervals','regimes','output_directory','shared_lock'}
INTERVALS={'development_start','development_end','holdout_start','holdout_end','prospective_start','prospective_end'}


def load_settings(path):
    from thermal_model.installed_shade_training import _path,_object
    def reject(_):raise ValueError('nonfinite configuration refused')
    value=json.loads(_private_bytes(Path(path),16384),object_pairs_hook=_object,parse_constant=reject)
    if not isinstance(value,dict) or set(value)!=FIELDS or value['schema']!=SCHEMA:raise ValueError('closed raw registration configuration required')
    for key in ('candidate_sha256','runtime_sha256','raw_sources_sha256'):
        if not isinstance(value[key],str) or re.fullmatch('[0-9a-f]{64}',value[key]) is None:raise ValueError('pinned original identity required')
    for key in ('candidate_path','raw_sources_path','shared_lock'):_path(value[key])
    for key in ('runtime_bundle_path','output_directory'):_path(value[key],directory=True)
    intervals=value['intervals']
    if not isinstance(intervals,dict) or set(intervals)!=INTERVALS:raise ValueError('explicit chronological policy intervals required')
    times={key:None if key=='prospective_end' and val is None else _time(val) for key,val in intervals.items()}
    now=_clock()
    if (not times['development_start']<times['development_end']<=now<times['holdout_start']<times['holdout_end'] or
            times['prospective_start']<=now or times['prospective_end'] is not None and times['prospective_end']<=times['prospective_start']):
        raise ValueError('actual declaration must precede untouched release intervals')
    if (not isinstance(value['regimes'],list) or not 1<=len(value['regimes'])<=3 or
            any(type(item) is not str or item not in ('warm','shoulder','winter') for item in value['regimes']) or len(set(value['regimes']))!=len(value['regimes'])):
        raise ValueError('closed distinct regimes required')
    raw=_private_bytes(Path(value['raw_sources_path']),4000000)
    if sha256(raw).hexdigest()!=value['raw_sources_sha256']:raise ValueError('original development index changed')
    _index(json.loads(raw,object_pairs_hook=_object,parse_constant=reject))
    return deepcopy(value)


def run_registration(settings,*,guard):
    from thermal_model.replay_budget import shared_replay_budget
    guard();deadline=monotonic()+85
    def remaining():guard();return deadline-monotonic()
    with shared_replay_budget(remaining):return _run_registration(settings,guard=guard)


def _run_registration(settings,*,guard):
    from thermal_model.forcing_capture import _canonical
    from thermal_model.runtime_bundle import _owned_bytes,read_runtime_bundle
    from thermal_model.origin_capture import build_runtime_binding,_source_bytes
    from thermal_model.installed_shade_publication import RAW_RUNTIME_PATHS
    from thermal_model.installed_shade_artifact import _digest
    from thermal_model.installed_shade_calibrated_artifact import read_raw_calibrated_candidate
    from thermal_model.installed_shade_qualification import _score_packets
    from thermal_model.installed_shade_score_jobs import _decode
    from thermal_model.graduation_policy import derive_policy,RECORD_FIELDS
    from thermal_model.policy_registration import register_raw_calibrated_installed_shade_policy,read_raw_calibrated_installed_shade_registered_policy
    from thermal_model.installed_shade_calibration import _persist
    from thermal_model.replay_budget import shared_replay_budget,check_shared_budget
    guard();check_shared_budget();started=_clock();root=Path(__file__).resolve().parent
    original=_owned_bytes(Path(settings['raw_sources_path']),4000000)
    if sha256(original).hexdigest()!=settings['raw_sources_sha256']:raise ValueError('original development index changed')
    references=_decode(original);_index(references)
    candidate_bytes=_owned_bytes(Path(settings['candidate_path']),2000000)
    archive=read_runtime_bundle(Path(settings['runtime_bundle_path']));runtime=archive['runtime']
    if set(archive['revision_paths'])!=set(RAW_RUNTIME_PATHS) or _digest(runtime)!=settings['runtime_sha256']:
        raise ValueError('complete pinned runtime required')
    commands={name:_source_bytes(root/name,maximum=65536) for name in (Path(__file__).name,'thermal_installed_calibrate.py')}
    def check():
        guard()
        if _owned_bytes(Path(settings['raw_sources_path']),4000000)!=original:raise ValueError('original development index changed')
        if _owned_bytes(Path(settings['candidate_path']),2000000)!=candidate_bytes:raise ValueError('original candidate changed')
        if _canonical(read_runtime_bundle(Path(settings['runtime_bundle_path'])))!=_canonical(archive):raise ValueError('runtime archive changed')
        if _canonical(build_runtime_binding(root,archive['revision_paths']))!=_canonical(runtime):raise ValueError('executing runtime differs')
        if any(_source_bytes(root/name,maximum=65536)!=raw for name,raw in commands.items()):raise ValueError('registration command changed')
    def guarded_remaining():
        # The outer ContextVar budget clamps this value; do not reset its deadline.
        check();return 85
    with shared_replay_budget(guarded_remaining):
        loaded=read_raw_calibrated_candidate(Path(settings['candidate_path']),expected_runtime_revision=settings['runtime_sha256'],assessed_at=_clock())
        artifact=loaded['artifact']
        if (artifact['schema']!='earthship-installed-shade-candidate/v3' or artifact['artifact_sha256']!=settings['candidate_sha256'] or
                _canonical(artifact['runtime'])!=_canonical(runtime) or loaded['fit_evidence']['fit_gates_passed'] is not True or
                loaded['calibration']['summary']['complete'] is not True):raise ValueError('source-qualified calibrated candidate required')
        metadata={key:deepcopy(artifact[key]) for key in ('artifact_sha256','trained_through','created_at','sensor_epochs')}
        metadata.update(runtime_sha256=settings['runtime_sha256'],active_parameter_count=len(artifact['base_candidate']['dynamics']['coefficients']))
        if metadata['active_parameter_count']!=10:raise ValueError('exact installed ten-parameter candidate required')
        check_shared_budget()
        scored=_score_packets(references,assessed_at=_clock(),version=4)
        if scored.get('raw_native_score_sources') is not True:raise ValueError('original development queries required')
        if any(row['sensor_epochs']!=metadata['sensor_epochs'] for row in scored['rows']):raise ValueError('development hardware phase differs')
        development=[{key:row[key] for key in RECORD_FIELDS} for row in scored['rows']]
        check_shared_budget()
        policy=derive_policy(development,declared_at=_clock(),intervals=settings['intervals'],candidate=metadata,regimes=settings['regimes'])
        check_shared_budget()
        path=register_raw_calibrated_installed_shade_policy(Path(settings['output_directory']),policy,references)
        restored=read_raw_calibrated_installed_shade_registered_policy(path)
        if _canonical(restored['policy'])!=_canonical(policy) or _canonical(restored['development_sources'])!=_canonical(references):
            raise ValueError('original policy seal readback differs')
        check_shared_budget()
        result=dict(status='policy_registered',registration_executed=True,registration_path=str(path),
            registration_sha256=restored['registration_sha256'],policy_sha256=policy['policy_sha256'],release_authorized=False,production_installed=False)
        receipt=dict(schema='earthship-installed-shade-registration-build-receipt/v1',started_at=started.isoformat(),completed_at=_clock().isoformat(),
            candidate_sha256=settings['candidate_sha256'],runtime_sha256=settings['runtime_sha256'],raw_sources_sha256=settings['raw_sources_sha256'],
            command_source=dict(sha256=sha256(commands[Path(__file__).name]).hexdigest(),utf8=commands[Path(__file__).name].decode()),
            configuration_helper_source=dict(sha256=sha256(commands['thermal_installed_calibrate.py']).hexdigest(),utf8=commands['thermal_installed_calibrate.py'].decode()),**result)
        receipt['receipt_sha256']=_digest(receipt);check_shared_budget()
        receipt_path=_persist(Path(settings['output_directory']),receipt,receipt['receipt_sha256'],'.installed-shade-registration-build-v1.json')
        if _owned_bytes(receipt_path,65536)!=_canonical(receipt):raise ValueError('private execution receipt differs')
        check_shared_budget();return dict(result,receipt_path=str(receipt_path))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--register',action='store_true');args=parser.parse_args(argv)
    saved={key:os.environ.get(key) for key in ('EARTHSHIP_QUALIFICATION_FIT','EARTHSHIP_REMOTE_QUALIFICATION_FIT')}
    try:
        if args.register:_resource_preflight()
        settings=load_settings(args.config)
        if not args.register:
            print(json.dumps(dict(status='configuration_verified',registration_executed=False,release_authorized=False)));return 0
        os.environ['EARTHSHIP_QUALIFICATION_FIT']='0';os.environ['EARTHSHIP_REMOTE_QUALIFICATION_FIT']='0'
        from thermal_model.capture_guard import SharedScoreLock
        with SharedScoreLock(settings['shared_lock']) as held:result=run_registration(settings,guard=held.verify)
        print(json.dumps(result,sort_keys=True));return 0
    except BlockingIOError:
        print(json.dumps(dict(status='busy',registration_executed=False,release_authorized=False)));return 75
    except Exception:
        print(json.dumps(dict(status='withheld',registration_executed=None,release_authorized=False)));return 1
    finally:
        for key,value in saved.items():
            if value is None:os.environ.pop(key,None)
            else:os.environ[key]=value


if __name__=='__main__':raise SystemExit(main())
