"""Prepare the selected native forecast geometry before the issuance window.

This command computes private observational geometry only. It cannot fit a
model, publish telemetry, select a model or issue a household device command.
"""
from datetime import datetime,timedelta,timezone
from pathlib import Path
import time


def _library_paths(raw):
    from astro_geometry_worker import ROLES
    from household.codec import loads
    value=loads(raw)
    if (set(value)!={'schema','library_paths'} or value['schema']!='earthship-native-geometry-libraries/v1' or
        not isinstance(value['library_paths'],dict) or set(value['library_paths'])!=ROLES):
        raise ValueError('closed native library configuration required')
    result={}
    for role,name in value['library_paths'].items():
        if not isinstance(name,str) or not 1<=len(name)<=1024:
            raise ValueError('bounded original native library path required')
        path=Path(name)
        if not path.is_absolute() or path.resolve()!=path:
            raise ValueError('resolved original native library path required')
        result[role]=path
    return result


def run(config,libraries,*,stage=None,clock=lambda:datetime.now(timezone.utc),monotonic=time.monotonic):
    from native_thermal_live import load_settings,prepare_geometry,_resource_preflight
    from thermal_model.provisional_live import _next_issue
    from thermal_model.capture_guard import SharedScoreLock
    from native_inference_pressure import NativeInferenceHeadroom
    from thermal_model.origin_capture import _source_bytes
    from household_observation import _private_file
    _resource_preflight()
    config,libraries=map(lambda path:Path(path).absolute(),(config,libraries))
    original=_private_file(config,8192);library_original=_private_file(libraries,8192)
    settings=load_settings(config);paths=_library_paths(library_original[0])
    source=Path(__file__).resolve();own=_source_bytes(source,maximum=262144)
    now=clock();issue=_next_issue(now)
    if issue-now<timedelta(seconds=120):
        raise BlockingIOError('original forecast preparation window reserved')
    verifier=None;binding=None
    if stage is not None:
        from household_cycle_deploy import verify_stage
        stage=Path(stage).absolute();binding=verify_stage(stage);verifier=verify_stage
        if source!=stage/'sources/openhab/scripts/household_native_geometry_prepare.py':
            raise ValueError('staged native preparer execution required')
    with SharedScoreLock(settings['shared_lock']) as lock:
        pressure=NativeInferenceHeadroom();pressure.preflight()
        deadline=monotonic()+75
        def guard():
            lock.verify();pressure.check()
            if monotonic()>=deadline or clock()>=issue-timedelta(seconds=35):
                raise ValueError('native preparation lifetime elapsed')
            if (_private_file(config,8192)!=original or _private_file(libraries,8192)!=library_original or
                _source_bytes(source,maximum=262144)!=own):
                raise ValueError('native preparation source or configuration changed')
        guard()
        result=prepare_geometry(settings,issue=issue,library_paths=paths,guard=guard)
        guard()
        if verifier is not None and verifier(stage)!=binding:
            raise ValueError('staged native preparation runtime changed')
        guard();return result


def main(argv=None):
    import argparse,json
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True,type=Path)
    parser.add_argument('--libraries',required=True,type=Path)
    parser.add_argument('--stage',type=Path)
    args=parser.parse_args(argv)
    try:result=run(args.config,args.libraries,stage=args.stage)
    except BlockingIOError:
        print(json.dumps(dict(status='busy',fit_executed=False,automatic_actuation=False)));return 75
    except Exception:
        print(json.dumps(dict(status='geometry_withheld',fit_executed=False,automatic_actuation=False)));return 1
    print(json.dumps(result));return 0 if result.get('status')=='prepared' else 1


if __name__=='__main__':raise SystemExit(main())
