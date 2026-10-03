#!/usr/bin/env python3
"""Activate only the qualified recovery gate, with receipt-bound rollback.

No job start, timer enable, forecast request or learned-state mutation.
"""
import argparse
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import shlex
import stat

SPEC=importlib.util.spec_from_file_location('forecast_stage',Path(__file__).with_name('forecast-recovery-files.py'))
s=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(s)
CODE='openhab/scripts/forecast_fetch_recovery.py'
DROP='deploy/forecast-intel-fetch-recovery.service.d/enabled.conf'
PINS={CODE:'efcaa18f39fcd7c08619f7507ad8c310ad604ce1148e1e9b370017b4f6ba0f33',
      DROP:'8e98cdb91652d8fd9c9af0c180f7d4718fbb41774e510c96d7eb164e010629fe'}
FLAG='EARTHSHIP_FORECAST_FETCH_RECOVERY_ENABLE=1'


def manifest():
    return (dict(source=CODE,target=str(s.LIVE/'forecast_fetch_recovery.py'),phase='code',mode=0o644),
        dict(source=DROP,target=str(s.UNITS/'forecast-intel-fetch-recovery.service.d/enabled.conf'),phase='unit',mode=0o644))


def save(receipt,data):s.files._write_json(receipt/'activation.json',data)


def state(receipt):
    s.validate(receipt)
    details=receipt.lstat()
    if (not stat.S_ISDIR(details.st_mode) or details.st_uid!=os.getuid()
            or stat.S_IMODE(details.st_mode)!=0o700):raise ValueError('owned private activation receipt required')
    data=s.files._read_json(receipt/'activation.json','bounded forecast recovery activation')
    checksum=data.pop('checksum',None)
    if (checksum!=sha256(s.files._canonical(data)).hexdigest()
            or set(data)!={'version','status','policies','candidate_sha256'}
            or type(data['version']) is not int or data['version']!=1
            or data['status'] not in {'prepared','enabled','rolled_back'}
            or data['policies']!=s.policies() or data['candidate_sha256']!=PINS):
        raise ValueError('unchanged exact activation receipt required')
    for source in ('deploy/forecast-intel-fetch-recovery.service','deploy/forecast-intel-fetch-recovery.timer'):
        if sha256(s.read(s.UNITS/Path(source).name)[0]).hexdigest()!=s.CANDIDATES[source]:
            raise ValueError('unchanged qualified recovery units required')
    if sha256(s.read(s.LIVE/'forecast_intel.py')[0]).hexdigest()!=s.CANDIDATES['openhab/scripts/forecast_intel.py']:
        raise ValueError('unchanged installed forecast instrumentation required')
    engine=s.files._load_receipt(receipt/'files',manifest())
    for source,digest in PINS.items():
        if sha256(s.read(receipt/'source'/source)[0]).hexdigest()!=digest:
            raise ValueError('frozen activation source changed')
    code,drop=engine['entries']
    old={s.LEGACY_CANDIDATES[CODE],s.CANDIDATES[CODE]}
    if (code['source_sha256']!=PINS[CODE] or code['prior']!='present'
            or code['prior_sha256'] not in old or code['prior_mode']!=0o644
            or drop['source_sha256']!=PINS[DROP] or drop['prior']!='absent'):
        raise ValueError('exact staged recovery rollback required')
    return data


def verify(enabled):
    s.verify_effective(True,recovery_enabled=enabled)
    helper='forecast-intel-fetch-recovery.service'
    env=shlex.split(s.systemctl('show',helper,'-p','Environment','--value'))
    if env!=([FLAG] if enabled else []):raise ValueError('exact isolated recovery setting required')
    raw=s.systemctl('show',helper,'-p','ExecStart','--value')
    argv=s.re.findall(r'argv\[\]=(.+?) ; ignore_errors=',raw)
    if len(argv)!=1 or shlex.split(argv[0])!=['/usr/bin/python3',str(s.LIVE/'forecast_fetch_recovery.py'),'--run']:
        raise ValueError('qualified recovery command required')


def prepare(receipt):
    s.validate(receipt);s.idle_window();verify(False)
    if receipt.exists() or sha256(s.read(s.LIVE/'forecast_intel.py')[0]).hexdigest()!=s.CANDIDATES['openhab/scripts/forecast_intel.py']:
        raise ValueError('new receipt and installed forecast instrumentation required')
    code,drop=manifest()
    if (sha256(s.read(Path(code['target']))[0]).hexdigest() not in {s.LEGACY_CANDIDATES[CODE],s.CANDIDATES[CODE]}
            or Path(drop['target']).exists() or Path(drop['target']).is_symlink()):
        raise ValueError('exact staged recovery and absent opt-in required')
    for source,digest in PINS.items():
        if sha256(s.read(s.ROOT/source)[0]).hexdigest()!=digest:raise ValueError('qualified source required')
    policies=s.policies()
    # Also pin the two unchanged recovery units and installed forecast source.
    # These stay outside the changed manifest and are never restored by it.
    for source in ('deploy/forecast-intel-fetch-recovery.service','deploy/forecast-intel-fetch-recovery.timer'):
        path=s.UNITS/Path(source).name
        if sha256(s.read(path)[0]).hexdigest()!=s.CANDIDATES[source]:raise ValueError('unchanged recovery units required')
    s.files.secure_directory(receipt,0o700,create=True,enforce_mode=True)
    for source in PINS:s.files._atomic_write_private(receipt/'source'/source,s.read(s.ROOT/source)[0],0o600,parent_mode=0o700)
    s.files.capture_backup(receipt/'source',receipt/'files',manifest=manifest())
    save(receipt,dict(version=1,status='prepared',policies=policies,candidate_sha256=PINS))
    state(receipt)
    return dict(status='prepared',production_writes=0)


def activate(receipt):
    data=state(receipt)
    if data['status']!='prepared':raise ValueError('prepared activation required')
    s.idle_window();verify(False)
    for record in s.files._load_receipt(receipt/'files',manifest())['entries']:
        if not s.files._target_matches(record,'original'):
            raise ValueError('unchanged original activation targets required')
    try:
        for phase in ('code','unit'):s.files.install_phase(receipt/'source',receipt/'files',phase,manifest=manifest())
        s.systemctl('daemon-reload');verify(True);state(receipt)
        data['status']='enabled';save(receipt,data)
    except Exception:
        s.files.restore(receipt/'source',receipt/'files',manifest=manifest())
        s.systemctl('daemon-reload');verify(False)
        data['status']='rolled_back';save(receipt,data)
        raise
    return dict(status='enabled',jobs_started=False,forecast_policy_changed=False)


def restore(receipt):
    data=state(receipt);s.idle_window()
    s.files.recover(receipt/'source',receipt/'files',manifest=manifest())
    s.files.restore(receipt/'source',receipt/'files',manifest=manifest())
    s.systemctl('daemon-reload');verify(False)
    data['status']='rolled_back';save(receipt,data)
    return dict(status='rolled_back',jobs_started=False)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=('prepare','activate','restore'))
    parser.add_argument('--receipt',required=True,type=Path)
    parser.add_argument('--allow-apply',action='store_true')
    args=parser.parse_args(argv)
    try:
        if args.operation!='prepare' and not args.allow_apply:raise ValueError('explicit activation authority required')
        print(json.dumps(globals()[args.operation](args.receipt),sort_keys=True));return 0
    except Exception:
        print('bounded forecast recovery activation withheld; inspect private receipt');return 1


if __name__=='__main__':raise SystemExit(main())
