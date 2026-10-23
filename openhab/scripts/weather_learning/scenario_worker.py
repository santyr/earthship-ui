"""Default-off advisory scenarios from explicitly retained household originals.

Preview is read-only. --apply writes only the explicit private scenario namespace.
No cloud, SQL, Item, selector, service, training or equipment operations occur.
"""
from datetime import datetime,timedelta,timezone
from hashlib import sha256
from pathlib import Path
import argparse,json,time
from .contracts import canonical,identity,instant,digest
from .config import Site
from .native_forecast import _snapshot,_decode,make_native_component_forecast
from .native_scenarios import prepare_native_context,geometry_positions
from .scenarios import ResidualBlock
from .scenario_reporting import prepare_report,retain_report,_runtime

SCHEMA='earthship-optional-household-scenario-producer/v1'
RETAINED_SCHEMA='earthship-optional-household-scenario-producer/v2'
FIELDS={'schema','enabled','state','energy_path','template_paths','observation_cohort_sha256','runtime_sha256'}
ROOT=Path(__file__).resolve().parents[3]


def runtime_sha256():
    value=_runtime()
    return identity(dict(source_package_sha256=value['source_package_sha256'],environment=value['environment']))


# Same qualified-state contract as household_calibrated_energy.storage_inputs;
# isolated here so original producers need no later sidecar module.
def _storage_inputs(snapshot,*,topology_source,origin):
    """Freeze original qualified initial conditions at the forecast issue.

    A forecast published later does not relabel its measurements as current.
    The source's original age/identity/validity/skew policies remain in force
    at that issue. This module grants no live telemetry or actuator permission.
    """
    from household.codec import loads
    from household.energy_persistence import _reading
    from household.energy_configuration import project_energy_configuration
    from household.power_flows import _dc_scope
    doc=snapshot.to_dict();rows=doc['domains']['energy'];soc=rows['battery_soc'];load=rows['estimated_load_w'];ages=doc['temporal_policy']['max_age_seconds']
    if instant(doc['as_of'])!=origin:raise ValueError('same original storage origin required')
    reason=_reading(soc,'BMS_SOC_Evidence_JSON','percent',origin,origin,ages.get('battery_soc'))
    scope,why=_dc_scope(topology_source,origin)
    if reason is None:reason=why
    bank=project_energy_configuration(snapshot.energy_configuration,as_of=origin)['bank'];end=origin+timedelta(hours=24)
    if reason is None and (bank['status']!='declared' or bank.get('nominal_usable_kwh') is None):reason='nominal_capacity_unavailable'
    if reason is None and bank.get('effective_until') is not None and end>=instant(bank['effective_until']):reason='bank_window_does_not_cover_horizon'
    if reason is None:
        topology=loads(topology_source['raw'])
        if topology['effective_until'] is not None and end>=instant(topology['effective_until']):reason='household_topology_window_does_not_cover_horizon'
    load_reason=_reading(load,'Inverter_AC_Evidence_JSON:inverter.ac_output_w','W',origin,origin,ages.get('estimated_load_w'))
    if reason is None and load_reason is None:
        if abs(instant(soc['evidence']['observed_at'])-instant(load['evidence']['observed_at']))>timedelta(seconds=doc['temporal_policy']['max_skew_seconds']):load_reason='source_skew'
    return dict(reason=reason,initial_soc_pct=soc['value'],nominal_bank_kwh=bank.get('nominal_usable_kwh'),current_load_reason=load_reason,
        current_load_w=load['value'] if load_reason is None else None,battery_soc_evidence_sha256=None if soc.get('evidence') is None else soc['evidence']['digest'],household_dc_scope=scope)

def prepare_owned_inputs(*,energy,plan,retained_producer=None,guard=lambda:None):
    """Derive new predictions from original inputs, never borrow old outputs."""
    if retained_producer is not None:
        from .retained_scenarios import prepare_retained_inputs
        return prepare_retained_inputs(energy=energy,plan=plan,producer=retained_producer,guard=guard)
    from household_energy_forecast import FIELDS as ENERGY_FIELDS,INPUT_FIELDS
    from household.model_snapshot import restore_snapshot
    from household_pv_model import system_configuration
    from household_solar_horizon import horizon_configuration
    if (not isinstance(energy,dict) or set(energy)!=ENERGY_FIELDS or energy['schema']!='earthship-household-energy-forecast-receipt/v1' or
        not isinstance(energy['inputs'],dict) or set(energy['inputs'])!=INPUT_FIELDS or
        energy['receipt_sha256']!=identity({k:v for k,v in energy.items() if k!='receipt_sha256'}) or
        not isinstance(plan,dict) or plan.get('receipt_sha256')!=identity({k:v for k,v in plan.items() if k!='receipt_sha256'}) or
        energy['inputs']['plan_document_sha256']!=sha256(canonical(plan)).hexdigest() or
        energy['inputs']['plan_receipt_sha256']!=plan['receipt_sha256']):raise ValueError('unchanged original energy and plan bindings required')
    guard();snapshot=restore_snapshot(plan['inputs']['snapshot'],plan['inputs']['source_contexts'])
    capture=snapshot.weather.original_capture;origin=instant(capture['issued_at']);forecast=capture['inputs']['forecast']
    context=prepare_native_context(capture,runtime=capture['candidate']['runtime'],expected_capture_sha256=capture['capture_sha256'],expected_artifact_sha256=capture['candidate']['artifact_sha256'],guard=guard)
    geometry,positions=geometry_positions(context)
    source=_snapshot(_decode(forecast['source_original']))
    forcing=make_native_component_forecast(source,origin=origin,available_by=instant(forecast['available_by']),horizon_hours=forecast['horizon_hours'],site=Site(**forecast['site']))
    inputs=energy['inputs'];storage=_storage_inputs(snapshot,topology_source=inputs['topology_source'],origin=origin)
    if storage['reason'] is not None or storage['current_load_reason'] is not None:raise ValueError('original qualified storage/load inputs unavailable: '+str(storage['reason'] or storage['current_load_reason']))
    system,why=system_configuration(inputs['system_source'],origin)
    if why is not None:raise ValueError('original PV system unavailable: '+why)
    horizon,why=horizon_configuration(inputs['horizon_source'],origin=origin,site=forecast['site'],timezone_name=forecast['site']['timezone'])
    if why is not None:raise ValueError('original terrain horizon unavailable: '+why)
    guard()
    return dict(forcing=forcing,household_inputs=dict(positions=positions,array=system['array'],horizon_profile=horizon['profile'],initial_soc_pct=storage['initial_soc_pct'],nominal_bank_kwh=storage['nominal_bank_kwh'],load_ac_w=storage['current_load_w'],thermal_context=context.to_dict()))


def _profile(value):
    if (not isinstance(value,dict) or value.get('schema') not in (SCHEMA,RETAINED_SCHEMA) or
        set(value)!=(FIELDS|{'retained_producer'} if value.get('schema')==RETAINED_SCHEMA else FIELDS) or type(value['enabled']) is not bool or
        not isinstance(value['template_paths'],list) or len(value['template_paths'])>10000 or
        len(set(value['template_paths']))!=len(value['template_paths'])):raise ValueError('closed bounded explicit scenario profile required')
    for name in ('state','energy_path'):
        if not isinstance(value[name],str) or not Path(value[name]).is_absolute():raise ValueError('explicit absolute scenario path required')
    if any(not isinstance(p,str) or not Path(p).is_absolute() for p in value['template_paths']):raise ValueError('absolute original residual paths required')
    if value['schema']==RETAINED_SCHEMA:
        from .retained_scenarios import producer_reference
        producer_reference(value['retained_producer'])
    digest(value['observation_cohort_sha256']);digest(value['runtime_sha256'])
    return value


def run(profile,*,policy,apply=False,clock=lambda:datetime.now(timezone.utc),guard=lambda:None):
    from .retained_scenarios import retained_cache
    with retained_cache():return _run(profile,policy=policy,apply=apply,clock=clock,guard=guard)


def _run(profile,*,policy,apply=False,clock=lambda:datetime.now(timezone.utc),guard=lambda:None):
    from household_solar_score import read_forecast,unchanged
    from household_observation import _private_file
    if type(apply) is not bool:raise ValueError('explicit publication flag required')
    profile=_profile(profile)
    if not profile['enabled']:return dict(status='disabled',retained=False,automatic_actuation=False)
    deadline=time.monotonic()+90.
    def check():
        guard()
        if time.monotonic()>=deadline:raise TimeoutError('bounded household scenario opportunity elapsed')
    check();runtime=runtime_sha256()
    if runtime!=profile['runtime_sha256']:raise ValueError('explicit scenario producer source/environment pin differs')
    energy,plan,originals=read_forecast(profile['energy_path']);prepared=prepare_owned_inputs(energy=energy,plan=plan,retained_producer=profile.get('retained_producer'),guard=check)
    templates=[];original_blocks=[];total=0;rows=0
    for path in profile['template_paths']:
        check();raw,metadata=_private_file(Path(path),16*1024**2);total+=len(raw)
        if total>policy['maximum_original_bytes']:raise ValueError('combined residual original byte budget exceeded')
        block=ResidualBlock(raw);rows+=len(block.to_dict()['residuals'])
        if rows>policy['maximum_template_rows']:raise ValueError('combined residual row budget exceeded')
        templates.append(block);original_blocks.append((Path(path),raw,metadata))
    owned_sources=dict(energy=energy,plan=plan)
    if profile['schema']==RETAINED_SCHEMA:owned_sources['retained_producer']=profile['retained_producer']
    report=prepare_report(**prepared,owned_sources=owned_sources,policy=policy,blocks=templates,cohort_sha256=profile['observation_cohort_sha256'],prepared_at=clock(),guard=check)
    check();unchanged(originals)
    for path,raw,metadata in original_blocks:
        check()
        if _private_file(path,16*1024**2)!=(raw,metadata):raise ValueError('original residual changed during preparation')
    if runtime_sha256()!=runtime:raise ValueError('scenario producer changed during preparation')
    value=report.to_dict();result=dict(status='prepared',retained=False,cached=False,report_sha256=value['report_sha256'],stress_cases=len(value['output']['stress']),joint_status=value['output']['joint']['status'],probability_claim=False,automatic_actuation=False)
    if apply:
        try:
            check();retained=retain_report(profile['state'],report,clock=clock,guard=check);result.update(retained,status='retained')
        except Exception as error:
            # The archive or cache may already have changed before a failed guard
            # or readback. Do not promise preservation after partial publication.
            result.update(status='publication_uncertain',retained=None,cached=None,reason=type(error).__name__)
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--profile',type=Path);parser.add_argument('--apply',action='store_true');parser.add_argument('--print-runtime',action='store_true');args=parser.parse_args(argv)
    try:
        if args.print_runtime:
            if args.profile is not None or args.apply:raise ValueError('runtime inventory is read-only')
            print(json.dumps(dict(runtime_sha256=runtime_sha256())));return 0
        if args.profile is None:raise ValueError('explicit optional profile required')
        from household_observation import _private_file
        from weather_source_files import _read
        profile=json.loads(_private_file(args.profile,65536)[0]);policy=json.loads(_read(ROOT/'docs/operations/weathernext3-capabilities/scenario-protocol.json',65536,source=True))
        result=run(profile,policy=policy,apply=args.apply);print(json.dumps(result));return 1 if result['status']=='publication_uncertain' else 0
    except Exception as error:
        print(json.dumps(dict(status='unavailable',reason=type(error).__name__,detail=str(error)[:512],retained=False,probability_claim=False,automatic_actuation=False)));return 1

if __name__=='__main__':raise SystemExit(main())
