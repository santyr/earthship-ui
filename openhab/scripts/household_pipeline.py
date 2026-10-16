#!/usr/bin/env python3
"""Rederive a private model/plan receipt; no live readers or action transport."""
import argparse
from pathlib import Path
from hashlib import sha256
import sys
from household.codec import loads,canonical
from household.pipeline import replay_pipeline,MAX_BYTES
from household_snapshot import _read,runtime_manifest,VALIDATORS
from household.thermal_model import _execution_runtime,_native_execution_runtime,PreparedProjection


def thermal_execution_runtime(root,value):
    if value is None:return None
    prepared=PreparedProjection(canonical(value));record=prepared.to_dict()
    if record['schema']=='earthship-household-prepared-thermal/v2':
        return _native_execution_runtime(root,record['executing_runtime']['thermal_runtime'],lambda:None)
    return _execution_runtime(root)


MEASURED_VALIDATORS=('weather_radiation_reader.py','weather_radiation_evidence.py','weather_rain_day.py','weather_rain_evidence.py')


def pipeline_runtime_manifest(*,expanded=False,configured=False,measured=False):
    result=runtime_manifest();root=Path(__file__).resolve().parent
    for name in ('household_plan.py','household_pipeline.py','forecast_intel.py'):
        result['openhab/scripts/'+name]=sha256(_read(root/name,262144)).hexdigest()
    if expanded:
        from earthship_energy import ac_evidence,power_evidence,power_intervals
        for module in (ac_evidence,power_evidence,power_intervals):
            result['companion/earthship_energy/'+Path(module.__file__).name]=sha256(_read(Path(module.__file__),262144)).hexdigest()
    if configured:
        result['openhab/scripts/advisory_windows.py']=sha256(_read(root/'advisory_windows.py',262144)).hexdigest()
    if measured:
        for name in MEASURED_VALIDATORS:result['openhab/scripts/'+name]=sha256(_read(root/name,262144)).hexdigest()
    return result


SOURCE_MODULES=('__init__','adapters','capabilities','capture','codec','evidence','power_capture','power_snapshot','replay','snapshot')
POWER_COMPANIONS={'companion/earthship_energy/'+name+'.py' for name in ('ac_evidence','power_evidence','power_intervals')}


def verify_source_closure(record,actual):
    if record.get('schema')=='earthship-household-model-plan-receipt/v6' and 'openhab/scripts/household/energy_persistence.py' not in record['runtime_manifest']:
        raise ValueError('energy persistence runtime source required')
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
        measured=source.get('schema')=='earthship-household-measured-source-context/v1'
        configured=measured or source.get('schema')=='earthship-household-energy-source-context/v1'
        if configured or source.get('schema')=='earthship-household-weather-source-context/v1':
            from household.weather_context import PreparedWeatherContext
            fields={'schema','power_receipt','weather_inputs'}|({'energy_configuration'} if configured else set())|({'measured_weather'} if measured else set())
            if set(source)!=fields:raise ValueError('closed original weather/energy source context required')
            if configured:
                from household.energy_configuration import PreparedEnergyConfiguration
                PreparedEnergyConfiguration(canonical(source['energy_configuration']))
            if measured:
                from household.measured_weather import PreparedMeasuredWeather
                PreparedMeasuredWeather(canonical(source['measured_weather']))
            weather=PreparedWeatherContext(canonical(source['weather_inputs']))
            if canonical(weather.prepared.to_dict()['executing_runtime'])!=canonical(thermal_execution_runtime(Path(__file__).resolve().parent,weather.prepared.to_dict())):raise ValueError('original weather executing runtime differs')
            weather_required={'openhab/scripts/household/'+name+'.py' for name in ('weather_context','weather_snapshot')}
            if configured:
                weather_required.update('openhab/scripts/household/'+name+'.py' for name in ('energy_configuration','energy_configuration_capture','energy_source_snapshot','energy_outcome_sources'))
                weather_required.add('openhab/scripts/advisory_windows.py')
            if measured:
                weather_required.update('openhab/scripts/household/'+name+'.py' for name in ('measured_weather','measured_weather_snapshot','measured_weather_capture'))
                weather_required.update('openhab/scripts/'+name for name in MEASURED_VALIDATORS)
            source=source['power_receipt']
        expected=source['runtime_manifest']
        if not isinstance(expected,dict) or not (required|weather_required)<=set(expected) or any(actual.get(name)!=sha for name,sha in expected.items()):
            raise ValueError('complete original source execution closure differs')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt',required=True,type=Path);args=parser.parse_args(argv)
    try:
        raw=_read(args.receipt,MAX_BYTES,private=True);record=loads(raw)
        expanded=record.get('schema') in ('earthship-household-model-plan-receipt/v2','earthship-household-model-plan-receipt/v3','earthship-household-model-plan-receipt/v4','earthship-household-model-plan-receipt/v5','earthship-household-model-plan-receipt/v6')
        configured=record.get('schema') in ('earthship-household-model-plan-receipt/v4','earthship-household-model-plan-receipt/v5','earthship-household-model-plan-receipt/v6')
        measured=record.get('schema') in ('earthship-household-model-plan-receipt/v5','earthship-household-model-plan-receipt/v6')
        executing=pipeline_runtime_manifest(expanded=expanded,configured=configured,measured=measured);root=Path(__file__).resolve().parent
        thermal=thermal_execution_runtime(root,record['inputs']['thermal_inputs'])
        if expanded:verify_source_closure(record,executing)
        replayed=replay_pipeline(record,runtime_manifest=executing,thermal_runtime=thermal)
        repeated_thermal=thermal_execution_runtime(root,record['inputs']['thermal_inputs'])
        if (pipeline_runtime_manifest(expanded=expanded,configured=configured,measured=measured)!=executing or canonical(repeated_thermal)!=canonical(thermal) or
            _read(args.receipt,MAX_BYTES,private=True)!=raw):raise ValueError('original or executing model/plan runtime changed')
        sys.stdout.buffer.write(canonical(replayed)+b'\n');return 0
    except Exception:
        print('Household model/plan replay refused: invalid or changed original context.',file=sys.stderr)
        return 1


if __name__=='__main__':raise SystemExit(main())
