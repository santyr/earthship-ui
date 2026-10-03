#!/usr/bin/env python3
"""Receipt-bound supporting Energy daily-quality unit handoff.

Only one user drop-in can change. Prepare/rehearse do not touch live units;
apply/restore/recover require explicit CLI authority and an idle timer window.
No start, stop, restart, timer enable, SQL mutation or OpenHAB request is made.
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

ROOT = Path(__file__).resolve().parents[1]
SOLAR = Path('/home/sat/Solar_PV')
BASE = Path('/home/sat/.config/systemd/user/energy-daily-aggregate.service')
TIMER = BASE.with_suffix('.timer')
UNIT = Path(str(BASE) + '.d/zz-qualified-switch.conf')
BASELINE_DROPINS = tuple(UNIT.parent/name for name in ('qualified-power.conf','qualified-temperature.conf'))
CANDIDATE = SOLAR/'deploy/systemd/user/energy-daily-aggregate.service.d/zz-qualified-switch.conf'
CANDIDATE_SHA = '6a12658f41ba8e6b32e6543681cfd05676f5c4830a6e6f20f62b4f9b40d5a5e5'
RECEIPTS = Path('/home/sat/.local/state/earthship-energy/deploy-receipts')
PYTHONPATH = '/home/sat/Solar_PV/analytics/src:/home/sat/earthship-ui/openhab/scripts'
# Operator accepted actual-binding fault/JVM qualification on October 3, 2026,
# instead of deliberately faulting household equipment. Explicit CLI authority,
# unchanged rehearsed receipt and idle-window/readback gates remain mandatory.
SUPPORTING_QUALITY_RELEASE_READY = True
SCHEMA = 'earthship-energy-quality-unit/v1'
SOURCE = 'candidate/zz-qualified-switch.conf'

spec = importlib.util.spec_from_file_location('energy_quality_secure_files', ROOT/'scripts/thermal-model-files.py')
files = importlib.util.module_from_spec(spec)
spec.loader.exec_module(files)


def read(path):
    data, mode = files._read_regular(path, 'quality input')
    if len(data) > 4*1024*1024: raise ValueError('bounded configuration/source required')
    return data, mode


def systemctl(*args):
    return subprocess.run(['systemctl','--user',*args],capture_output=True,text=True,
                          check=True,timeout=15).stdout.strip()


def idle_window():
    for name in ('energy-daily-aggregate.service','energy-ui-publish.service'):
        state = dict(line.split('=',1) for line in systemctl('show','-p','ActiveState','-p','MainPID',name).splitlines())
        if state != {'ActiveState':'inactive','MainPID':'0'}:
            raise ValueError('idle aggregate and publisher required')
    if systemctl('show','-p','ActiveState','--value','energy-daily-aggregate.timer') != 'active':
        raise ValueError('existing daily timer must remain active')
    raw = subprocess.run(['busctl','--user','get-property','org.freedesktop.systemd1',
        '/org/freedesktop/systemd1/unit/energy_2ddaily_2daggregate_2etimer',
        'org.freedesktop.systemd1.Timer','NextElapseUSecRealtime'],capture_output=True,text=True,
        check=True,timeout=15).stdout.strip()
    if re.fullmatch(r't [1-9][0-9]{15,16}',raw) is None or int(raw[2:])/1e6-time.time() < 90:
        raise ValueError('clear natural daily timer window required')


def input_paths():
    paths = {BASE,TIMER,*BASELINE_DROPINS,
        *UNIT.parent.glob('*.conf'),
        *SOLAR.joinpath('analytics/src/earthship_energy').rglob('*.py'),
        *SOLAR.joinpath('analytics/config').glob('*.json'),
        *SOLAR.joinpath('analytics/migrations').glob('*.sql'),
        *ROOT.joinpath('openhab/scripts').glob('*.py')}
    paths.discard(UNIT)
    paths = {path for path in paths if not path.name.startswith('test_')}
    paths.update(Path('/home/sat/.config/hex')/name for name in (
        'openhab.env','energy-power-reader.jdbc','energy-power-writer.jdbc',
        'weather-temperature-policy.json','weather-temperature-db.json'))
    publisher = BASE.parent/'energy-ui-publish.service'
    paths.add(publisher)
    paths.update(Path(str(publisher)+'.d').glob('*.conf'))
    return tuple(sorted(paths))


def pins():
    result = {}
    for path in sorted(input_paths(),key=str):
        data, mode = read(path)
        result[str(path)] = {'sha256':sha256(data).hexdigest(),'mode':mode}
    return result


def manifest(target=None):
    return ({'source':SOURCE,'target':str(UNIT if target is None else target),'phase':'unit','mode':0o644},)


def command(raw):
    if sha256(raw).hexdigest() != CANDIDATE_SHA:
        raise ValueError('exact tested combined candidate required')
    commands = [line[len('ExecStart='):] for line in raw.decode().splitlines() if line.startswith('ExecStart=')]
    if len(commands) != 2 or commands[0] != '': raise ValueError('single tested override required')
    return shlex.split(commands[1])


def verify_effective(installed):
    expected = command(read(CANDIDATE)[0])
    if not installed: expected = expected[:-8]  # Only the two new paired readers.
    raw = systemctl('show','-p','ExecStart','--value',BASE.name)
    matches = re.findall(r'argv\[\]=(.+?) ; ignore_errors=',raw)
    runtime = os.environ.get('XDG_RUNTIME_DIR')
    if (runtime is None or not runtime.startswith('/run/user/') or len(matches) != 1
            or shlex.split(matches[0]) != [value.replace('%t',runtime) for value in expected]):
        raise ValueError('effective daily command differs from exact candidate/baseline')
    if systemctl('show','-p','FragmentPath','--value',BASE.name) != str(BASE):
        raise ValueError('daily unit provider drift')
    paths = shlex.split(systemctl('show','-p','DropInPaths','--value',BASE.name))
    if paths != list(map(str,(*BASELINE_DROPINS,*((UNIT,) if installed else ())))):
        raise ValueError('daily drop-in ownership drift')
    env = shlex.split(systemctl('show','-p','Environment','--value',BASE.name))
    if env != ['PYTHONPATH='+PYTHONPATH]: raise ValueError('daily environment drift')


def validate_receipt_path(receipt):
    receipt = Path(receipt)
    if (not receipt.is_absolute() or receipt.parent != RECEIPTS or receipt.is_symlink()
            or re.fullmatch(r'quality-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}',receipt.name) is None):
        raise ValueError('new, immediate-child private Energy receipt required')


def save(receipt, data):
    files._write_json(receipt/'qualification.json',data)


def state(receipt):
    validate_receipt_path(receipt)
    details = receipt.lstat()
    if (not stat.S_ISDIR(details.st_mode) or stat.S_IMODE(details.st_mode) != 0o700
            or details.st_uid != os.getuid()):
        raise ValueError('owned mode-0700 private Energy receipt required')
    data = files._read_json(receipt/'qualification.json','private Energy qualification')
    checksum = data.pop('checksum',None)
    if (checksum != sha256(files._canonical(data)).hexdigest()
            or set(data) != {'schema','status','candidate_sha256','inputs','originals'}
            or data['schema'] != SCHEMA or data['candidate_sha256'] != CANDIDATE_SHA
            or data['status'] not in {'prepared','rehearsal_passed','installed_waiting_natural_aggregate','rolled_back'}
            or data['inputs'] != pins()):
        raise ValueError('unchanged exact source/configuration receipt required')
    if sha256(read(receipt/'source'/SOURCE)[0]).hexdigest() != CANDIDATE_SHA:
        raise ValueError('frozen candidate source changed')
    expected_originals = {f'{index:03d}.bin':{'path':path,'sha256':data['inputs'][path]['sha256']}
        for index,path in enumerate(path for path in data['inputs']
                                   if Path(path).suffix not in {'.py','.sql'})}
    if data['originals'] != expected_originals:
        raise ValueError('exact original configuration archive identities required')
    for name, record in data['originals'].items():
        raw, mode = read(receipt/'originals'/name)
        if mode != 0o600 or sha256(raw).hexdigest() != record['sha256']:
            raise ValueError('original configuration archive changed')
    engine = files._load_receipt(receipt/'files',manifest())
    if (engine['entries'][0]['source_sha256'] != CANDIDATE_SHA
            or engine['entries'][0].get('prior') != 'absent'):
        raise ValueError('exact absent-target rollback manifest required')
    return data


def prepare(receipt):
    validate_receipt_path(receipt)
    idle_window()
    if receipt.exists() or UNIT.exists() or UNIT.is_symlink():
        raise ValueError('new receipt and absent unowned candidate required')
    candidate, _ = read(CANDIDATE)
    command(candidate)
    verify_effective(False)
    inputs = pins()
    snapshots = {path:read(Path(path))[0] for path in inputs
                 if Path(path).suffix not in {'.py','.sql'}}
    if pins() != inputs: raise ValueError('inputs changed during backup preflight')
    files.secure_directory(receipt,0o700,create=True,enforce_mode=True)
    files._atomic_write_private(receipt/'source'/SOURCE,candidate,0o600,parent_mode=0o700)
    originals = {}
    for index, (path,raw) in enumerate(snapshots.items()):
        name = f'{index:03d}.bin'
        files._atomic_write_private(receipt/'originals'/name,raw,0o600,parent_mode=0o700)
        originals[name] = {'path':path,'sha256':sha256(raw).hexdigest()}
    data = {'schema':SCHEMA,'status':'prepared','candidate_sha256':CANDIDATE_SHA,
            'inputs':inputs,'originals':originals}
    save(receipt,data)
    files.capture_backup(receipt/'source',receipt/'files',manifest=manifest())
    state(receipt)
    return {'status':'prepared','receipt':str(receipt),'production_writes':0}


def verify_unit(path):
    subprocess.run(['systemd-analyze','--user','verify',str(path)],check=True,
                   capture_output=True,timeout=30)


def rehearse(receipt):
    data = state(receipt)
    if data['status'] not in {'prepared','rehearsal_passed'}:
        raise ValueError('original prepared receipt required for isolated rehearsal')
    with TemporaryDirectory(prefix='earthship-energy-unit-') as temporary:
        root = Path(temporary)
        original = root/BASE.name
        files._atomic_write_private(original,read(BASE)[0],0o600,parent_mode=0o700)
        target = Path(str(original)+'.d')/UNIT.name
        for dropin in BASELINE_DROPINS:
            files._atomic_write_private(target.parent/dropin.name,read(dropin)[0],0o600,parent_mode=0o700)
        baseline = {path:read(path) for path in (original,*(target.parent/p.name for p in BASELINE_DROPINS))}
        isolated = manifest(target)
        store = root/'receipt'
        files.capture_backup(receipt/'source',store,manifest=isolated)
        verify_unit(original)
        files.install_phase(receipt/'source',store,'unit',manifest=isolated)
        if read(target)[0] != read(CANDIDATE)[0]: raise ValueError('isolated installed unit differs')
        verify_unit(original)
        files.restore(receipt/'source',store,manifest=isolated)
        if target.exists() or any(read(path) != prior for path,prior in baseline.items()):
            raise ValueError('isolated original unit rollback differs')
        verify_unit(original)
        # Exercise the exact journaled interrupted rename, not just unlink.
        class Crash(BaseException): pass
        def crash(event,index):
            if event == 'after-replace': raise Crash()
        try: files.install_phase(receipt/'source',store,'unit',manifest=isolated,fault=crash)
        except Crash: pass
        else: raise ValueError('isolated interruption was not reached')
        files.recover(receipt/'source',store,manifest=isolated)
        if target.exists() or any(read(path) != prior for path,prior in baseline.items()):
            raise ValueError('isolated interrupted recovery differs')
    state(receipt)
    data['status']='rehearsal_passed'; save(receipt,data)
    return {'status':'rehearsal_passed','production_writes':0,'temporary_storage_removed':True}


def apply(receipt):
    if not SUPPORTING_QUALITY_RELEASE_READY:
        raise ValueError('supporting quality qualification/release gate is closed')
    data = state(receipt)
    if data['status'] != 'rehearsal_passed' or UNIT.exists() or UNIT.is_symlink():
        raise ValueError('rehearsed original state and absent owned target required')
    idle_window()
    verify_effective(False)
    idle_window()
    try:
        files.install_phase(receipt/'source',receipt/'files','unit',manifest=manifest())
        systemctl('daemon-reload')
        verify_effective(True)
        state(receipt)
        data['status']='installed_waiting_natural_aggregate'; save(receipt,data)
    except Exception:
        files.restore(receipt/'source',receipt/'files',manifest=manifest())
        systemctl('daemon-reload'); verify_effective(False)
        data['status']='rolled_back'; save(receipt,data)
        raise
    return {'status':data['status'],'jobs_started':False,'controls_enabled':False}


def restore(receipt):
    data=state(receipt); idle_window()
    files.restore(receipt/'source',receipt/'files',manifest=manifest())
    systemctl('daemon-reload'); verify_effective(False)
    data['status']='rolled_back'; save(receipt,data)
    return {'status':data['status'],'jobs_started':False}


def recover(receipt):
    state(receipt); idle_window()
    files.recover(receipt/'source',receipt/'files',manifest=manifest())
    return restore(receipt)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','rehearse','verify','apply','restore','recover'))
    parser.add_argument('--receipt',type=Path,required=True)
    parser.add_argument('--allow-apply',action='store_true')
    args=parser.parse_args(argv)
    try:
        if args.mode in {'apply','restore','recover'} and not args.allow_apply:
            raise ValueError('explicit attended write authority required')
        if args.mode=='verify':
            data=state(args.receipt)
            result={'status':data['status'],'release_ready':SUPPORTING_QUALITY_RELEASE_READY,'production_writes':0}
        else: result=globals()[args.mode](args.receipt)
        print(json.dumps(result,sort_keys=True,separators=(',',':')))
        return 0
    except Exception as error:
        print('Energy unit operation withheld ('+type(error).__name__+'); exact state, recovery or release gate failed',file=__import__('sys').stderr)
        return 1


if __name__=='__main__': raise SystemExit(main())
