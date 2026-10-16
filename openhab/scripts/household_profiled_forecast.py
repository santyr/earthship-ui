"""Separately versioned load/PV/storage scenarios over an original v1 forecast."""
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from household.codec import canonical,loads,identity
from household.control_contracts import instant
from household.evidence import utc
from household.planning import _runtime_manifest
from household_snapshot import _read
from household_energy_forecast import replay_energy_forecast
from household_ac_load_model import project_load
from household_ac_load_store import verify_admitted_source
from household_profiled_storage import simulate_profiled_storage

SCHEMA='earthship-household-profiled-energy-receipt/v1'
FIELDS={'schema','inputs','runtime_manifest','load_runtime_manifest','output','receipt_sha256'}
INPUTS={'original_energy_receipt_sha256','original_energy_document_sha256','plan_receipt_sha256','load_source','assessed_at'}
MODULES=('household_profiled_forecast.py','household_profiled_storage.py')
MAX_BYTES=262144


def profiled_runtime_manifest():
    root=Path(__file__).resolve().parent
    return {'openhab/scripts/'+name:sha256(_read(root/name,262144)).hexdigest() for name in MODULES}


def forecast_cohort(forecast,energy_receipt,plan_receipt):
    from household_solar_outcomes import cohort_for,matched_reference
    if forecast['output']['status']!='conditional_nominal_simulation' or matched_reference(plan_receipt) is None:return None
    original=cohort_for(energy_receipt,plan_receipt)
    if original is None:return None
    profile=forecast['inputs']['load_source']['artifact']['profile']
    return dict(evaluation_scope='rolling_as_issued_model_versions',original_solar_cohort=original,
        profiled_runtime_sha256=identity(forecast['runtime_manifest']),load_algorithm_runtime_sha256=identity(forecast['load_runtime_manifest']),load_policy_sha256=identity(profile['policy']))


def seal_profiled_forecast(*,energy_receipt,plan_receipt,load_source,now,runtime_manifest,energy_runtime_manifest,load_runtime_manifest):
    runtime=_runtime_manifest(runtime_manifest)
    if set(runtime)!={'openhab/scripts/'+name for name in MODULES}:raise ValueError('complete profiled scenario runtime required')
    energy=replay_energy_forecast(energy_receipt,plan_receipt=plan_receipt,runtime_manifest=energy_runtime_manifest)
    now=utc(now);pv=energy['output']['array_pv'];original=energy['output']['nominal_storage'];origin=instant(pv['origin'])
    if not instant(energy['inputs']['assessed_at'])<=now<=origin+timedelta(seconds=120):raise ValueError('bounded original profiled scenario issue clock required')
    source=None;load=None;reason='load_model_unavailable'
    if load_source is not None:
        source=verify_admitted_source(load_source,runtime_manifest=load_runtime_manifest,as_of=origin)
        load=project_load(source['artifact']['profile'],origin=origin,now=now)
        reason=load['reason']
    elif load_runtime_manifest:raise ValueError('absent load source cannot bind a model runtime')
    storage=None
    if reason is None:
        if original['status']!='conditional_nominal_simulation':reason='original_storage_inputs_unavailable'
        else:storage=simulate_profiled_storage(steps=pv['steps'],initial_soc_pct=original['initial_soc_pct'],nominal_bank_kwh=original['nominal_bank_kwh'],load_forecast=load)
    value=dict(schema=SCHEMA,inputs=dict(original_energy_receipt_sha256=energy['receipt_sha256'],original_energy_document_sha256=identity(energy),
        plan_receipt_sha256=plan_receipt['receipt_sha256'],load_source=source,assessed_at=now.isoformat()),runtime_manifest=runtime,
        load_runtime_manifest=dict(load_runtime_manifest),output=dict(status='conditional_nominal_simulation' if storage is not None else 'unavailable',reason=reason,
            issued_at=origin.isoformat(),load_forecast=load,profiled_storage=storage,current_load_persistence_w=original.get('household_ac_load_w_assumption'),
            original_storage_projection_sha256=original['projection_sha256'],physical_calibration_qualified=False,automatic_actuation=False))
    cohort=forecast_cohort(value,energy,plan_receipt)
    value['output']['cohort_id']=None if cohort is None else identity(cohort)
    value['receipt_sha256']=identity(value)
    if len(canonical(value))>MAX_BYTES:raise ValueError('bounded original profiled energy receipt required')
    return loads(canonical(value))


def replay_profiled_forecast(receipt,*,energy_receipt,plan_receipt,runtime_manifest,energy_runtime_manifest,load_runtime_manifest):
    if (not isinstance(receipt,dict) or set(receipt)!=FIELDS or receipt['schema']!=SCHEMA or len(canonical(receipt))>MAX_BYTES or
        not isinstance(receipt['inputs'],dict) or set(receipt['inputs'])!=INPUTS or
        identity({k:v for k,v in receipt.items() if k!='receipt_sha256'})!=receipt['receipt_sha256'] or
        canonical(receipt['runtime_manifest'])!=canonical(runtime_manifest) or canonical(receipt['load_runtime_manifest'])!=canonical(load_runtime_manifest)):
        raise ValueError('unchanged original profiled receipt and runtime required')
    value=seal_profiled_forecast(energy_receipt=energy_receipt,plan_receipt=plan_receipt,load_source=receipt['inputs']['load_source'],now=instant(receipt['inputs']['assessed_at']),
        runtime_manifest=runtime_manifest,energy_runtime_manifest=energy_runtime_manifest,load_runtime_manifest=load_runtime_manifest)
    if canonical(value)!=canonical(receipt):raise ValueError('original profiled scenario differs')
    return value


def main(argv=None):
    import argparse,sys
    from datetime import datetime,timezone
    from household_observation import _private_file
    from household_energy_forecast import forecast_runtime_manifest
    from household_ac_load_artifact import runtime_manifest as model_runtime
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('receipt','energy','plan'):parser.add_argument('--'+name,required=True,type=Path)
    args=parser.parse_args(argv)
    try:
        originals=[(path,_private_file(path,maximum)) for path,maximum in ((args.receipt,MAX_BYTES),(args.energy,262144),(args.plan,2097152))]
        receipt,energy,plan=[loads(value[0]) for _,value in originals];fr=profiled_runtime_manifest();er=forecast_runtime_manifest()
        lr={} if receipt['inputs']['load_source'] is None else model_runtime()
        if instant(receipt['inputs']['assessed_at'])>datetime.now(timezone.utc):raise ValueError('future profile assessment refused')
        result=replay_profiled_forecast(receipt,energy_receipt=energy,plan_receipt=plan,runtime_manifest=fr,energy_runtime_manifest=er,load_runtime_manifest=lr)
        if (profiled_runtime_manifest()!=fr or forecast_runtime_manifest()!=er or lr and model_runtime()!=lr or
            any(_private_file(path,2097152)!=value for path,value in originals)):raise ValueError('original profile replay inputs changed')
        sys.stdout.buffer.write(canonical(result)+b'\n');return 0
    except Exception:
        print('Profiled energy replay refused: invalid or changed original inputs.',file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
