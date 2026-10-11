#!/usr/bin/env python3
"""Rederive a private model/plan receipt; no live readers or action transport."""
import argparse
from pathlib import Path
from hashlib import sha256
import sys
from household.codec import loads,canonical
from household.pipeline import replay_pipeline,MAX_BYTES
from household_snapshot import _read,runtime_manifest,VALIDATORS
from household.thermal_model import _execution_runtime


def pipeline_runtime_manifest(*,expanded=False):
    result=runtime_manifest();root=Path(__file__).resolve().parent
    for name in ('household_plan.py','household_pipeline.py','forecast_intel.py'):
        result['openhab/scripts/'+name]=sha256(_read(root/name,262144)).hexdigest()
    if expanded:
        from earthship_energy import ac_evidence,power_evidence,power_intervals
        for module in (ac_evidence,power_evidence,power_intervals):
            result['companion/earthship_energy/'+Path(module.__file__).name]=sha256(_read(Path(module.__file__),262144)).hexdigest()
    return result


SOURCE_MODULES=('__init__','adapters','capabilities','capture','codec','evidence','power_capture','power_snapshot','replay','snapshot')
POWER_COMPANIONS={'companion/earthship_energy/'+name+'.py' for name in ('ac_evidence','power_evidence','power_intervals')}


def verify_source_closure(record,actual):
    contexts=record['inputs'].get('source_contexts')
    if not isinstance(contexts,dict) or not 1<=len(contexts)<=9:raise ValueError('bounded original source contexts required')
    required={'openhab/scripts/'+name for name in VALIDATORS}
    required.update('openhab/scripts/household/'+name+'.py' for name in SOURCE_MODULES)
    required.update('openhab/scripts/'+name for name in ('household_snapshot.py','household_capture.py','hourly_temperature_runtime.py'))
    required.update(('companion/earthship_energy/db.py','companion/earthship_energy/bms_evidence.py',
        'openhab/managed-resources.json','openhab/file-config/ownership.json'))
    required.update(POWER_COMPANIONS)
    for source in contexts.values():
        weather_required=set()
        if source.get('schema')=='earthship-household-weather-source-context/v1':
            from household.weather_context import PreparedWeatherContext
            if set(source)!={'schema','power_receipt','weather_inputs'}:raise ValueError('closed original weather source context required')
            weather=PreparedWeatherContext(canonical(source['weather_inputs']))
            if canonical(weather.prepared.to_dict()['executing_runtime'])!=canonical(_execution_runtime(Path(__file__).resolve().parent)):raise ValueError('original weather executing runtime differs')
            weather_required={'openhab/scripts/household/'+name+'.py' for name in ('weather_context','weather_snapshot')}
            source=source['power_receipt']
        expected=source['runtime_manifest']
        if not isinstance(expected,dict) or not (required|weather_required)<=set(expected) or any(actual.get(name)!=sha for name,sha in expected.items()):
            raise ValueError('complete original source execution closure differs')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt',required=True,type=Path);args=parser.parse_args(argv)
    try:
        raw=_read(args.receipt,MAX_BYTES,private=True);record=loads(raw)
        expanded=record.get('schema') in ('earthship-household-model-plan-receipt/v2','earthship-household-model-plan-receipt/v3')
        executing=pipeline_runtime_manifest(expanded=expanded);root=Path(__file__).resolve().parent
        thermal=_execution_runtime(root) if record['inputs']['thermal_inputs'] is not None else None
        if expanded:verify_source_closure(record,executing)
        replayed=replay_pipeline(record,runtime_manifest=executing,thermal_runtime=thermal)
        repeated_thermal=_execution_runtime(root) if thermal is not None else None
        if (pipeline_runtime_manifest(expanded=expanded)!=executing or canonical(repeated_thermal)!=canonical(thermal) or
            _read(args.receipt,MAX_BYTES,private=True)!=raw):raise ValueError('original or executing model/plan runtime changed')
        sys.stdout.buffer.write(canonical(replayed)+b'\n');return 0
    except Exception:
        print('Household model/plan replay refused: invalid or changed original context.',file=sys.stderr)
        return 1


if __name__=='__main__':raise SystemExit(main())
