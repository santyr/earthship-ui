#!/usr/bin/env python3
"""Check private installed-domain settings or explicitly publish one live cycle."""
import argparse
import json
import os
from pathlib import Path


def _resource_preflight():
    from thermal_model.capture_guard import verify_resource_limits,_small_text
    from pathlib import PurePosixPath
    verify_resource_limits()
    row=_small_text('/proc/self/cgroup');path=PurePosixPath(row[3:])
    leaf=Path('/sys/fs/cgroup').joinpath(*path.parts[1:])
    quota,period=map(int,_small_text(leaf/'cpu.max').split())
    if (quota*5>period or int(_small_text(leaf/'memory.max'))>268435456 or
            int(_small_text(leaf/'pids.max'))>24 or os.getpriority(os.PRIO_PROCESS,0)<15):
        raise ValueError('strict serial installed publication resource limits required')
    memory={line.split()[0]:line.split()[1] for line in _small_text('/proc/meminfo').splitlines() if line.split()}
    if int(memory['MemAvailable:'])<1572864:raise ValueError('publication memory headroom unavailable')
    pressure=_small_text('/proc/pressure/memory').splitlines()
    for line in pressure:
        cells=dict(part.split('=',1) for part in line.split()[1:])
        if float(cells['avg10'])>.5:raise ValueError('publication memory pressure unavailable')
    # This is a capped publication reader, not the large training-capture worker.
    # Its separate preflight does not change training/capture/fitting guards.
    for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
        if os.environ.get(key)!='1':raise ValueError('one numerical thread required')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    intent=parser.add_mutually_exclusive_group()
    intent.add_argument('--publish',action='store_true')
    intent.add_argument('--check-only',action='store_true')
    intent.add_argument('--withdraw',action='store_true')
    parser.add_argument('--reason',help='private withdrawal reason, required with --withdraw')
    args=parser.parse_args(argv)
    if args.withdraw and not args.reason:parser.error('--withdraw requires --reason')
    if not args.withdraw and args.reason is not None:parser.error('--reason requires --withdraw')
    try:
        if args.publish or args.withdraw:
            _resource_preflight()
            os.environ['EARTHSHIP_QUALIFICATION_FIT']='0';os.environ['EARTHSHIP_REMOTE_QUALIFICATION_FIT']='0'
        if args.withdraw:
            from thermal_model.installed_shade_live_inputs import load_withdraw_settings,WithdrawalBackend
            from thermal_model.installed_shade_live import withdraw_live_publication
            settings=load_withdraw_settings(args.config)
            result=withdraw_live_publication(archive=settings['evidence_directory'],backend=WithdrawalBackend(settings),reason=args.reason)
            print(json.dumps(result,sort_keys=True));return 0 if result['status'] in ('withdrawn','busy') else 1
        from thermal_model.installed_shade_live_inputs import load_live_settings,LiveBackend
        settings=load_live_settings(args.config)
        if not args.publish:
            print(json.dumps(dict(status='configuration_verified',publication_executed=False,automatic_actuation=False)));return 0
        from thermal_model.installed_shade_live import run_live_cycle
        receipt=run_live_cycle(reference_path=settings['release_inputs_path'],archive=settings['evidence_directory'],backend=LiveBackend(settings))
        print(json.dumps(receipt,sort_keys=True));return 0 if receipt['status'] in ('published','withdrawn','busy','duplicate_attempt') else 1
    except Exception:
        # Source exceptions may contain secret config/transport detail. The
        # service remains observable without emitting those bytes or a traceback.
        print(json.dumps(dict(status='unverified_failure',publication_executed=False,automatic_actuation=False)));return 1


if __name__=='__main__':raise SystemExit(main())
