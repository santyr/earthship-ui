#!/usr/bin/env python3
"""Receipt-bound staging of disabled morning forecast recovery.

No job starts, timer enablement, prediction backfill or release-flag override.
Apply installs the qualified instrumentation and closed-gate recovery units.
"""
import argparse
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
from tempfile import TemporaryDirectory
import time

ROOT=Path(__file__).resolve().parents[1]
LIVE=Path('/home/sat/openhab/scripts')
UNITS=Path('/home/sat/.config/systemd/user')
BASE=UNITS/'forecast-intel.service'
DROPINS=tuple(Path(str(BASE)+'.d')/name for name in (
    'advisory-outcomes.conf','qualified-daily-temperature.conf','qualified-soc.conf','qualified-temperature.conf'))
RECEIPTS=Path('/home/sat/.local/state/forecast-intel/deploy-receipts')
OLD='943c09d414c6265d5a9527bb1901c3e8aa7355fc190f261a61cf58d02fbed58e'
CANDIDATES={
    'openhab/scripts/forecast_fetch_recovery.py':'5006637dee86001e4d5c484ad9573f155bcde3a86855b4c7d62385363d84c82c',
    'openhab/scripts/forecast_intel.py':'1b902853bc155b404bc18dc352545ea214632de4053ff295f8683e31574c5d1b',
    'deploy/forecast-intel-fetch-recovery.service':'606368e47408f2539ad142401424eb3f252c3f198abc15cddedf693b4bbe0ef9',
    'deploy/forecast-intel-fetch-recovery.timer':'f52834d9e38de531ba712b96afe5c65475717649f3675dd026f41673f03a9294',
    'deploy/forecast-intel.service.d/fetch-recovery.conf':'1ed6e2bcdd5fcfc53f4ebf940277d7af4e8786f383da8d31b4f0c114e33bff71'}
SPEC=importlib.util.spec_from_file_location('forecast_recovery_secure_files',ROOT/'scripts/thermal-model-files.py')
files=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(files)


def read(path):
    raw,mode=files._read_regular(path,'forecast recovery input')
    if len(raw)>4*1024*1024:raise ValueError('bounded source/configuration required')
    return raw,mode


def systemctl(*args):
    return subprocess.run(['systemctl','--user',*args],capture_output=True,text=True,
        check=True,timeout=15).stdout.strip()


def manifest(live=None,units=None):
    live=LIVE if live is None else live;units=UNITS if units is None else units
    records=[]
    for source in CANDIDATES:
        iscode=source.startswith('openhab/scripts/')
        target=(live/Path(source).name if iscode else units/source.removeprefix('deploy/'))
        records.append(dict(source=source,target=str(target),phase='code' if iscode else 'unit',
            mode=0o755 if source.endswith('/forecast_intel.py') else 0o644))
    return tuple(records)


def policies():
    paths=(BASE,UNITS/'forecast-intel.timer',UNITS/'forecast-json.service',UNITS/'forecast-json.timer',*DROPINS)
    if tuple(sorted(Path(str(BASE)+'.d').glob('*.conf'))) != tuple(sorted(DROPINS)):
        owned=Path(str(BASE)+'.d/fetch-recovery.conf')
        if tuple(sorted(Path(str(BASE)+'.d').glob('*.conf'))) != tuple(sorted((*DROPINS,owned))):
            raise ValueError('unexpected forecast policy drop-in')
    return {str(path):dict(sha256=sha256(read(path)[0]).hexdigest(),mode=read(path)[1]) for path in paths}


def idle_window():
    for name in ('forecast-intel.service','forecast-json.service'):
        state=dict(line.split('=',1) for line in systemctl('show',name,'-p','ActiveState','-p','MainPID').splitlines())
        if state!={'ActiveState':'inactive','MainPID':'0'}:raise ValueError('idle forecast jobs required')
    for name in ('forecast-intel.timer','forecast-json.timer'):
        if systemctl('show',name,'-p','ActiveState','--value')!='active':
            raise ValueError('existing forecast timers must stay active')
        escaped=name.replace('-','_2d').replace('.','_2e')
        def deadline(property):
            value=subprocess.run(['busctl','--user','get-property','org.freedesktop.systemd1',
                '/org/freedesktop/systemd1/unit/'+escaped,'org.freedesktop.systemd1.Timer',property],
                capture_output=True,text=True,check=True,timeout=15).stdout.strip()
            if re.fullmatch(r't [0-9]+',value) is None:raise ValueError('finite timer deadline required')
            return int(value[2:])/1e6
        limits=[value-clock() for value,clock in (
            (deadline('NextElapseUSecRealtime'),time.time),
            (deadline('NextElapseUSecMonotonic'),time.monotonic)) if value]
        if not limits or min(limits)<120:raise ValueError('clear natural forecast timer window required')


def verify_effective(installed):
    if systemctl('show',BASE.name,'-p','FragmentPath','--value')!=str(BASE):
        raise ValueError('original forecast provider required')
    expected=list(map(str,sorted((*DROPINS,*((Path(str(BASE)+'.d/fetch-recovery.conf'),) if installed else ())))))
    if shlex.split(systemctl('show',BASE.name,'-p','DropInPaths','--value'))!=expected:
        raise ValueError('exact existing forecast policy drop-ins required')
    raw=systemctl('show',BASE.name,'-p','ExecStart','--value')
    argv=re.findall(r'argv\[\]=(.+?) ; ignore_errors=',raw)
    if len(argv)!=1 or shlex.split(argv[0])!=['/usr/bin/python3',str(LIVE/'forecast_intel.py')]:
        raise ValueError('original effective forecast command required')
    if systemctl('show',BASE.name,'-p','OnFailure','--value')!=(
        'forecast-intel-fetch-recovery.timer' if installed else ''):
        raise ValueError('unexpected forecast failure target')
    helper=UNITS/'forecast-intel-fetch-recovery.service'
    timer=helper.with_suffix('.timer')
    for path in (helper,timer):
        actual=systemctl('show',path.name,'-p','FragmentPath','--value')
        if actual!=(str(path) if installed else ''):raise ValueError('recovery unit provider drift')
        if systemctl('show',path.name,'-p','DropInPaths','--value')!='':
            raise ValueError('no unreviewed recovery-unit overrides allowed')
        if systemctl('show',path.name,'-p','ActiveState','--value')!='inactive':
            raise ValueError('recovery units must remain inactive during handoff')


def validate(receipt):
    if (receipt.parent!=RECEIPTS or receipt.is_symlink()
            or receipt.parent.resolve()!=receipt.parent
            or re.fullmatch(r'fetch-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}',receipt.name) is None):
        raise ValueError('exact owned forecast recovery receipt required')


def state(receipt):
    validate(receipt)
    details=receipt.lstat()
    if not stat.S_ISDIR(details.st_mode) or details.st_uid!=os.getuid() or stat.S_IMODE(details.st_mode)!=0o700:
        raise ValueError('owned private receipt required')
    data=files._read_json(receipt/'qualification.json','forecast recovery qualification')
    checksum=data.pop('checksum',None)
    if (checksum!=sha256(files._canonical(data)).hexdigest()
            or set(data)!={'version','status','policies','candidate_sha256'} or data['version']!=1
            or data['status'] not in {'prepared','rehearsal_passed','installed_disabled','rolled_back'}
            or data['policies']!=policies() or data['candidate_sha256']!=CANDIDATES):
        raise ValueError('unchanged forecast qualification required')
    for source,digest in CANDIDATES.items():
        if sha256(read(receipt/'source'/source)[0]).hexdigest()!=digest:
            raise ValueError('frozen candidate changed')
    for index,record in enumerate(data['policies'].values()):
        raw,mode=read(receipt/'original-policies'/f'{index:02d}.bin')
        if mode!=0o600 or sha256(raw).hexdigest()!=record['sha256']:
            raise ValueError('original policy archive changed')
    engine=files._load_receipt(receipt/'files',manifest())
    for record in engine['entries']:
        if (record['source_sha256']!=CANDIDATES[record['source']]
                or (record['source'].endswith('/forecast_intel.py') and record.get('prior_sha256')!=OLD)
                or (not record['source'].endswith('/forecast_intel.py') and record['prior']!='absent')):
            raise ValueError('exact original forecast rollback required')
    return data


def save(receipt,data):files._write_json(receipt/'qualification.json',data)


def prepare(receipt):
    validate(receipt);idle_window();verify_effective(False)
    if receipt.exists() or sha256(read(LIVE/'forecast_intel.py')[0]).hexdigest()!=OLD:
        raise ValueError('new receipt and qualified original forecast required')
    for record in manifest():
        target=Path(record['target'])
        if not record['source'].endswith('/forecast_intel.py') and (target.exists() or target.is_symlink()):
            raise ValueError('absent unowned candidate targets required')
        raw,mode=read(ROOT/record['source'])
        if sha256(raw).hexdigest()!=CANDIDATES[record['source']]:raise ValueError('qualified source required')
    baseline=policies()
    files.secure_directory(receipt,0o700,create=True,enforce_mode=True)
    for source in CANDIDATES:
        files._atomic_write_private(receipt/'source'/source,read(ROOT/source)[0],0o600,parent_mode=0o700)
    for index,path in enumerate(sorted(baseline)):
        files._atomic_write_private(receipt/'original-policies'/f'{index:02d}.bin',read(Path(path))[0],0o600,parent_mode=0o700)
    files.capture_backup(receipt/'source',receipt/'files',manifest=manifest())
    save(receipt,dict(version=1,status='prepared',policies=dict(sorted(baseline.items())),candidate_sha256=CANDIDATES))
    state(receipt)
    return dict(status='prepared',production_writes=0)


def rehearse(receipt):
    data=state(receipt)
    if data['status'] not in {'prepared','rehearsal_passed','rolled_back'}:
        raise ValueError('prepared or restored original required')
    for record in files._load_receipt(receipt/'files',manifest())['entries']:
        if not files._target_matches(record,'original'):raise ValueError('unchanged original required for rehearsal')
    with TemporaryDirectory(prefix='earthship-forecast-handoff-') as temp:
        root=Path(temp);live=root/'scripts';units=root/'units'
        for path in data['policies']:
            relative=Path(path).relative_to(UNITS)
            files._atomic_write_private(units/relative,read(Path(path))[0],0o600,parent_mode=0o700)
        def parse():
            subprocess.run(['systemd-analyze','--user','verify',str(units/BASE.name)],
                capture_output=True,check=True,timeout=30)
        parse()
        files._atomic_write_private(live/'forecast_intel.py',read(LIVE/'forecast_intel.py')[0],read(LIVE/'forecast_intel.py')[1])
        isolated=manifest(live,units);store=root/'receipt'
        files.capture_backup(receipt/'source',store,manifest=isolated)
        for phase in ('code','unit'):files.install_phase(receipt/'source',store,phase,manifest=isolated)
        parse()
        files.restore(receipt/'source',store,manifest=isolated)
        parse()
        class Crash(BaseException):pass
        def crash(event,index):
            if event=='after-replace':raise Crash()
        for phase in ('code','unit'):
            try:files.install_phase(receipt/'source',store,phase,manifest=isolated,fault=crash)
            except Crash:pass
            else:raise ValueError('interruption not reached')
            files.recover(receipt/'source',store,manifest=isolated)
            files.restore(receipt/'source',store,manifest=isolated)
        if read(live/'forecast_intel.py')!=read(LIVE/'forecast_intel.py'):
            raise ValueError('original forecast rollback differs')
        if any(Path(record['target']).exists() for record in isolated if not record['source'].endswith('/forecast_intel.py')):
            raise ValueError('original absent targets not restored')
    data['status']='rehearsal_passed';save(receipt,data)
    return dict(status=data['status'],temporary_storage_removed=True)


def apply(receipt):
    data=state(receipt)
    if data['status']!='rehearsal_passed':raise ValueError('rehearsed original required')
    idle_window();verify_effective(False)
    try:
        for phase in ('code','unit'):files.install_phase(receipt/'source',receipt/'files',phase,manifest=manifest())
        systemctl('daemon-reload');verify_effective(True);state(receipt)
        data['status']='installed_disabled';save(receipt,data)
    except Exception:
        files.restore(receipt/'source',receipt/'files',manifest=manifest())
        systemctl('daemon-reload');verify_effective(False)
        data['status']='rolled_back';save(receipt,data)
        raise
    return dict(status=data['status'],jobs_started=False,recovery_enabled=False)


def restore(receipt,recover=False):
    data=state(receipt);idle_window()
    if recover:files.recover(receipt/'source',receipt/'files',manifest=manifest())
    files.restore(receipt/'source',receipt/'files',manifest=manifest())
    systemctl('daemon-reload');verify_effective(False)
    data['status']='rolled_back';save(receipt,data)
    return dict(status='rolled_back',jobs_started=False)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=('prepare','rehearse','apply','restore','recover'))
    parser.add_argument('--receipt',required=True,type=Path)
    parser.add_argument('--allow-apply',action='store_true')
    args=parser.parse_args(argv)
    try:
        if args.operation in {'apply','restore','recover'} and not args.allow_apply:
            raise ValueError('explicit file handoff authority required')
        result=(restore(args.receipt,recover=args.operation=='recover')
            if args.operation in {'restore','recover'} else globals()[args.operation](args.receipt))
        print(json.dumps(result,sort_keys=True));return 0
    except Exception:
        print('forecast recovery handoff withheld; inspect private receipt');return 1


if __name__=='__main__':raise SystemExit(main())
