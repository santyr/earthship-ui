"""Explicit read-only production sensitivity sidecar from completed native originals.

No cloud, observation database, model fitting or equipment path is opened.
Disabled unless --enabled is supplied; publication additionally requires --publish.
"""
from datetime import datetime,timedelta,timezone
from hashlib import sha256
from pathlib import Path
import argparse,json,time
from component_household_files import read_current_originals,unchanged_current
from household_native_training import effective_selection
from household_native_family import selected_interpreter
from household_cycle_deploy import verify_stage
from .contracts import canonical,identity,instant
from .retained_scenarios import retained_cache,producer_reference,PRODUCER_SCHEMA,PRODUCER_V2
from .scenario_worker import prepare_owned_inputs,runtime_sha256,ROOT
from .scenario_reporting import prepare_report
from .scenario_retention import archive_compact,restore_compact,retain_compact,_read,_write
from .shadow import ShadowStore,_directory
from .worker import collector_lock

# There is no qualified physical GHI / complete joint measurement contract.
# This named absence identity is deliberately disjoint from any eligible target
# cohort. No template import is accepted by this production entry point.
UNAVAILABLE_JOINT_COHORT=identity(dict(schema='earthship-unavailable-joint-weather-target-cohort/v1',reason='physical_ghi_and_complete_joint_targets_unavailable'))


def run(*,state,observation_path,enabled=False,publish=False,clock=lambda:datetime.now(timezone.utc),guard=lambda:None):
    if type(enabled) is not bool or type(publish) is not bool:raise ValueError('explicit scenario modes required')
    if not enabled:return dict(status='disabled',cached=False,automatic_actuation=False)
    started=time.monotonic()
    from household_cycle_pressure import PublicationHeadroom
    pressure=PublicationHeadroom()
    def check():
        guard();pressure.check()
        if time.monotonic()-started>90:raise TimeoutError('bounded production scenario opportunity elapsed')
    # A separate optional writer lock never blocks the normal household owner.
    state=Path(state)
    if not state.is_absolute() or state.resolve()!=state:raise ValueError('resolved private scenario state required')
    _directory(state)
    with collector_lock(state/'production-scenario-worker.lock'),retained_cache():
        check();selected=effective_selection();stage=Path(selected['stage']);verify_stage(stage,expected_deployment_sha256=selected['deployment_sha256'])
        current=read_current_originals(stage,observation_path,guard=check)
        if current is None:return dict(status='awaiting_completed_origin',cached=False,automatic_actuation=False)
        energy=current['energy'];origin=instant(energy['output']['array_pv']['origin']);now=clock()
        if not origin<=now<=origin+timedelta(minutes=15):return dict(status='awaiting_fresh_origin',cached=False,automatic_actuation=False)
        producer=dict(schema=PRODUCER_SCHEMA,stage=str(stage),deployment_sha256=selected['deployment_sha256'])
        interpreter=selected_interpreter(stage,deployment_sha256=selected['deployment_sha256'],guard=check)
        if interpreter is not None:producer.update(schema=PRODUCER_V2,python_path=interpreter['path'],python_sha256=interpreter['sha256'])
        producer=producer_reference(producer)
        from weather_source_files import _read as read_source
        policy_raw=read_source(ROOT/'docs/operations/weathernext3-capabilities/scenario-protocol.json',65536,source=True);policy=json.loads(policy_raw)
        runtime=runtime_sha256();binding=dict(schema='earthship-production-scenario-opportunity/v1',energy_sha256=identity(energy),plan_sha256=identity(current['plan']),producer=producer,policy_sha256=policy['policy_sha256'],runtime_sha256=runtime)
        pin=identity(binding);directory=state/'scenario-reports';index_path=directory/('issue-'+pin+'.json')
        try:index=_read(index_path,32768)
        except FileNotFoundError:index=None
        def unchanged():
            check();unchanged_current(current)
            if effective_selection()!=selected or runtime_sha256()!=runtime:raise ValueError('production scenario inputs or producer changed')
        if index is not None:
            if set(index)!={'schema','binding','original_report_sha256'} or index['schema']!='earthship-production-scenario-issue/v1' or index['binding']!=binding:raise ValueError('original scenario opportunity differs')
            report=restore_compact(state,index['original_report_sha256'],guard=check)
        else:
            prepared=prepare_owned_inputs(energy=energy,plan=current['plan'],retained_producer=producer,guard=check)
            report=prepare_report(**prepared,owned_sources=dict(energy=energy,plan=current['plan'],retained_producer=producer),policy=policy,blocks=[],cohort_sha256=UNAVAILABLE_JOINT_COHORT,prepared_at=clock(),guard=check)
        unchanged();value=report.to_dict()
        result=dict(status='prepared',report_sha256=value['report_sha256'],origin=origin.isoformat(),stress_cases=len(value['output']['stress']),joint_status=value['output']['joint']['status'],cached=False,probability_claim=False,automatic_actuation=False)
        if not publish:return dict(result,seconds=time.monotonic()-started)
        parents=dict(energy=current['energy_path'],plan=current['originals'][2])
        store=ShadowStore(state);_directory(directory)
        try:
            # Write the original opportunity binding before its public cache.
            # An interrupted retry reconstructs its first clocks, never relabels.
            archive_compact(state,report.content,parents=parents,guard=check)
            _write(store,index_path,dict(schema='earthship-production-scenario-issue/v1',binding=binding,original_report_sha256=value['report_sha256']),check)
            unchanged()
            retained=retain_compact(state,report,parents=parents,clock=clock,guard=check,before_confirm=unchanged)
        except Exception as error:
            return dict(result,status='publication_uncertain',cached=None,retained=None,reason=type(error).__name__,seconds=time.monotonic()-started)
        return dict(result,**{k:v for k,v in retained.items() if k not in result},cached=retained['cached'],status='confirmed' if retained['cached'] else 'original_expired',seconds=time.monotonic()-started)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--state',type=Path,required=True);parser.add_argument('--observation',type=Path,required=True);parser.add_argument('--enabled',action='store_true');parser.add_argument('--publish',action='store_true');args=parser.parse_args(argv)
    try:
        value=run(state=args.state,observation_path=args.observation,enabled=args.enabled,publish=args.publish);print(json.dumps(value));return 1 if value['status']=='publication_uncertain' else 0
    except Exception as error:
        print(json.dumps(dict(status='unavailable',reason=type(error).__name__,detail=str(error)[:256],cached=False,automatic_actuation=False)));return 1

if __name__=='__main__':raise SystemExit(main())
