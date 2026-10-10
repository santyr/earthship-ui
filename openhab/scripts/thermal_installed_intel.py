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



def _live(args,*,guard=lambda:None):
    guard()
    from thermal_model.installed_shade_live_inputs import load_live_settings,load_raw_live_settings,load_compressed_live_settings,LiveBackend,CompressedSourceLiveBackend
    loader={1:load_live_settings,2:load_raw_live_settings,3:load_compressed_live_settings}[args.contract_version]
    settings=loader(args.config);guard()
    if not (args.publish or args.bootstrap_shadow):
        print(json.dumps(dict(status='configuration_verified',publication_executed=False,automatic_actuation=False)));return 0
    from thermal_model.installed_shade_live import run_raw_live_cycle,run_bootstrap_live_cycle,run_compressed_live_cycle
    run=run_bootstrap_live_cycle if args.bootstrap_shadow else run_compressed_live_cycle if args.contract_version==3 else run_raw_live_cycle
    backend=(CompressedSourceLiveBackend if args.contract_version==3 else LiveBackend)(settings,shared_lock_guard=guard);guard()
    receipt=run(reference_path=settings['release_inputs_path'],archive=settings['evidence_directory'],backend=backend)
    guard();print(json.dumps(receipt,sort_keys=True))
    return 0 if receipt['status'] in ('published','withdrawn','busy','duplicate_attempt') else 1


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--contract-version',type=int,choices=(1,2,3),default=2,
        help='2 preserves raw production; 3 explicitly selects compressed source qualification; 1 permits native base shadow bootstrap')
    intent=parser.add_mutually_exclusive_group()
    intent.add_argument('--publish',action='store_true')
    intent.add_argument('--bootstrap-shadow',action='store_true',help='contract 1 native base candidate calibration collection only')
    intent.add_argument('--check-only',action='store_true')
    intent.add_argument('--withdraw',action='store_true')
    parser.add_argument('--shared-lock',type=Path,help='existing private consumer lock, required for publication/bootstrap')
    parser.add_argument('--reason',help='private withdrawal reason, required with --withdraw')
    args=parser.parse_args(argv)
    if args.publish and args.contract_version not in (2,3):parser.error('publication requires contract version 2 or 3')
    if args.bootstrap_shadow and args.contract_version!=1:parser.error('base shadow bootstrap requires explicit contract version 1')
    if (args.publish or args.bootstrap_shadow) and args.shared_lock is None:parser.error('publication/bootstrap requires --shared-lock')
    if args.shared_lock is not None and not (args.publish or args.bootstrap_shadow):parser.error('--shared-lock requires publication/bootstrap')
    if args.withdraw and not args.reason:parser.error('--withdraw requires --reason')
    if not args.withdraw and args.reason is not None:parser.error('--reason requires --withdraw')
    try:
        if args.publish or args.bootstrap_shadow or args.withdraw:
            _resource_preflight()
            os.environ['EARTHSHIP_QUALIFICATION_FIT']='0';os.environ['EARTHSHIP_REMOTE_QUALIFICATION_FIT']='0'
        if args.withdraw:
            from thermal_model.installed_shade_live_inputs import load_withdraw_settings,load_raw_withdraw_settings,load_compressed_withdraw_settings,WithdrawalBackend
            from thermal_model.installed_shade_live import withdraw_live_publication,withdraw_raw_live_publication,withdraw_compressed_live_publication
            loader={1:load_withdraw_settings,2:load_raw_withdraw_settings,3:load_compressed_withdraw_settings}[args.contract_version]
            withdraw={1:withdraw_live_publication,2:withdraw_raw_live_publication,3:withdraw_compressed_live_publication}[args.contract_version]
            settings=loader(args.config)
            result=withdraw(archive=settings['evidence_directory'],backend=WithdrawalBackend(settings),reason=args.reason)
            print(json.dumps(result,sort_keys=True));return 0 if result['status'] in ('withdrawn','busy') else 1
        if args.publish or args.bootstrap_shadow:
            from thermal_model.capture_guard import SharedScoreLock
            with SharedScoreLock(args.shared_lock) as held:return _live(args,guard=held.verify)
        return _live(args)
    except BlockingIOError:
        print(json.dumps(dict(status='busy',publication_executed=False,automatic_actuation=False)));return 75
    except Exception:
        # Source exceptions may contain secret config/transport detail. The
        # service remains observable without emitting those bytes or a traceback.
        print(json.dumps(dict(status='unverified_failure',publication_executed=False,automatic_actuation=False)));return 1


if __name__=='__main__':raise SystemExit(main())
