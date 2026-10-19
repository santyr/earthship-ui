#!/usr/bin/env python3
"""Read local original inputs and replay a snapshot; output JSON only to stdout."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import os
from pathlib import Path
import stat
import subprocess
import sys
from household.codec import loads, canonical
from household.replay import compile_inputs, verify_replay, _instant, MAX_BYTES

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT/'openhab/scripts'
VALIDATORS = ('pv_day_evidence.py','weather_temperature_sources.py','weather_temperature_reader.py',
              'weather_temperature_evidence.py','weather_temperature_config.py','weather_temperature_history.py',
              'thermal_model/temperature_history.py',
              'thermal_model/schema.py')


def _read(path,maximum,*,private=False):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size>maximum or (private and (info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o600)):
            raise ValueError('bounded owned original file required')
        with os.fdopen(fd,'rb',closefd=False) as stream:raw=stream.read(maximum+1)
        if len(raw)>maximum: raise ValueError('original file byte budget exceeded')
        return raw
    finally:os.close(fd)


def runtime_manifest():
    import earthship_energy.bms_evidence as bms
    paths={('openhab/scripts/'+name):SCRIPTS/name for name in VALIDATORS}
    paths.update({str(path.relative_to(ROOT)):path for path in (SCRIPTS/'household').glob('*.py')})
    paths['openhab/scripts/household_snapshot.py']=Path(__file__).resolve()
    paths['openhab/scripts/household_capture.py']=SCRIPTS/'household_capture.py'
    paths['openhab/scripts/hourly_temperature_runtime.py']=SCRIPTS/'hourly_temperature_runtime.py'
    import earthship_energy.db as db
    paths['companion/earthship_energy/db.py']=Path(db.__file__)
    paths['companion/earthship_energy/bms_evidence.py']=Path(bms.__file__)
    paths.update({name:ROOT/name for name in ('openhab/managed-resources.json','openhab/file-config/ownership.json')})
    return {name:sha256(_read(path,262144)).hexdigest() for name,path in paths.items()}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True);parser.add_argument('--expect',type=Path)
    args=parser.parse_args(argv)
    try:
        inputs_raw=_read(args.input,MAX_BYTES,private=True);bundle=loads(inputs_raw)
        if _instant(bundle['as_of'])>datetime.now(timezone.utc): raise ValueError('future source bundle refused')
        managed_raw=_read(ROOT/'openhab/managed-resources.json',262144)
        ownership_raw=_read(ROOT/'openhab/file-config/ownership.json',262144)
        managed,ownership=map(loads,(managed_raw,ownership_raw))
        runtime=runtime_manifest()
        if runtime['openhab/managed-resources.json']!=sha256(managed_raw).hexdigest() or runtime['openhab/file-config/ownership.json']!=sha256(ownership_raw).hexdigest():
            raise ValueError('original manifests changed during collection')
        revision=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],timeout=3,text=True).strip()
        result=compile_inputs(bundle,managed=managed,ownership=ownership,code_revision=revision,runtime_manifest=runtime)
        if args.expect:verify_replay(loads(_read(args.expect,262144,private=True)),result)
        if _read(args.input,MAX_BYTES,private=True)!=inputs_raw or runtime_manifest()!=runtime or subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],timeout=3,text=True).strip()!=revision:
            raise ValueError('original input or runtime changed during replay')
        sys.stdout.buffer.write(canonical(result)+b'\n');return 0
    except Exception:
        print('Household snapshot refused: invalid or changed original inputs.',file=sys.stderr)
        return 1


if __name__=='__main__':raise SystemExit(main())
