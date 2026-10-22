"""Explicit source-pinned optional marginal producer; no cloud or Item writes."""
import argparse,json,time
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime,timedelta,timezone
from hashlib import sha256
from household_job_budget import AdmissionDeferred
from weather_source_files import _read
from .contracts import digest,instant
from .evidence import utc
from .config import Site
from .archive import Archive
from .probabilistic_artifacts import NUMERICAL_FILES,read_candidates
from .probabilistic_issue import temperature_context,wind_context,_context,prepare_marginal_issue
from .probabilistic_retained import SPECS
from .marginal_queue import MarginalQueue
from .shadow import ShadowStore

ROOT=Path(__file__).resolve().parents[3]
from .production_worker import SOURCE_FILES as CORE_SOURCE_FILES
SOURCE_FILES=tuple(sorted(set(CORE_SOURCE_FILES)|set(NUMERICAL_FILES)|{
    'openhab/scripts/weather_learning/'+name+'.py' for name in ('marginal_runtime','marginal_queue','marginal_outcomes','marginal_reporting','probabilistic_evaluation','correction_monitor','solar_shadow','wind_history')}|{
    'openhab/scripts/'+name+'.py' for name in ('weather_radiation_reader','weather_radiation_evidence')}))
FIELDS={'schema','enabled','archive','state','site','model_artifacts','temperature_policy','temperature_db_config','solar_origin_context','runtime_manifest'}


def runtime_manifest():return {name:sha256(_read(ROOT/name,1024**2,source=True)).hexdigest() for name in SOURCE_FILES}


def _path(value,*,optional=False):
    if optional and value is None:return None
    if not isinstance(value,str):raise ValueError('explicit resolved marginal profile path required')
    p=Path(value)
    if not p.is_absolute() or p.resolve()!=p:raise ValueError('resolved marginal profile path required')
    return p


def _profile(path):
    value=json.loads(_read(Path(path),131072))
    if (not isinstance(value,dict) or set(value)!=FIELDS or value['schema']!='earthship-marginal-production-profile/v1' or type(value['enabled']) is not bool or
            not isinstance(value['site'],dict) or set(value['site'])!={'latitude','longitude','timezone'} or
            not isinstance(value['model_artifacts'],dict) or len(value['model_artifacts'])>12):raise ValueError('closed explicit marginal producer profile required')
    Site(**value['site'])
    for name in ('archive','state','temperature_policy','temperature_db_config','solar_origin_context'):_path(value[name],optional=name not in ('archive','state'))
    for bundle,artifact in value['model_artifacts'].items():digest(bundle);digest(artifact)
    if value['runtime_manifest']!=runtime_manifest():raise ValueError('exact marginal runtime source profile required')
    return value


def _origins(value,*,clock,guard,temperature_reader):
    contexts={};policy_path=value['temperature_policy']
    if policy_path is not None:
        from hourly_temperature_runtime import _native_outdoor_policy,read_db_config
        from weather_temperature_history import fetch_temperature_grid_v2
        try:
            guard();policy,epoch=_native_outdoor_policy(policy_path);sampled=utc(clock())
            if temperature_reader is None:
                import psycopg2
                config=read_db_config(value['temperature_db_config'])
                original=fetch_temperature_grid_v2(lambda:psycopg2.connect(**config,connect_timeout=3),targets=[sampled],assessed_at=sampled,stream='outdoor',policy=policy,sensor_epoch=epoch)
                metadata=dict(original).get(sampled)
            else:metadata=temperature_reader(sampled,policy,epoch)
            acquired=utc(clock());guard()
            if metadata is not None:contexts['temperature']=temperature_context(metadata,sampled_at=sampled,acquired_at=acquired,sensor_epoch=epoch)
        except (TimeoutError,AdmissionDeferred,MemoryError):raise
        except Exception:pass
    if value['solar_origin_context'] is not None:
        try:
            guard();context=_context(json.loads(_read(_path(value['solar_origin_context']),16*1024**2)))
            if context.to_dict()['kind']!='solar_proxy':raise ValueError('original solar origin context required')
            contexts['solar_proxy']=context
        except (OSError,ValueError,KeyError,TypeError):pass
    return contexts


def run(path,*,apply=False,clock=lambda:datetime.now(timezone.utc),guard=lambda:None,temperature_reader=None):
    if type(apply) is not bool:raise ValueError('explicit marginal retention flag required')
    value=_profile(path);guard()
    if not value['enabled']:return dict(status='disabled',retained=False,local_coverage_qualified=False,automatic_actuation=False)
    state=SimpleNamespace(root=_path(value['state']));bundles=[]
    policy=json.loads(_read(ROOT/'docs/operations/weathernext3-capabilities/marginal-calibration-protocol.json',65536,source=True))
    for pin,artifact in value['model_artifacts'].items():
        guard();bundle=read_candidates(state,artifact,policy=policy,require_current=False)
        if bundle.to_dict()['bundle_sha256']!=pin:raise ValueError('original explicitly configured marginal artifact differs')
        bundles.append(bundle)
    contexts=_origins(value,clock=clock,guard=guard,temperature_reader=temperature_reader);decision=utc(clock());contexts['wind']=wind_context(decision=decision)
    archive=Archive.open_readonly(_path(value['archive']),allow_missing=True);site=Site(**value['site']);snapshots={}
    for kind,spec in SPECS.items():
        for hours in (24,336):
            guard();snapshot=archive.eligible_snapshot(decision,decision+timedelta(hours=hours),required_variables={spec[0]})
            if snapshot is not None:snapshots[snapshot['snapshot_sha256']]=snapshot
    guard();issue=prepare_marginal_issue(snapshots=list(snapshots.values()),decision=decision,site=site,contexts=contexts,bundles=bundles,policy=policy,guard=guard);body=issue.to_dict()
    if value['runtime_manifest']!=runtime_manifest():raise ValueError('marginal runtime source changed while preparing')
    if apply:
        guard();queue=MarginalQueue(ShadowStore(state.root),policy=policy);queue.publish(issue,model_artifacts=value['model_artifacts'],clock=clock);guard()
    return dict(status=body['status'],retained=apply,issue_sha256=body['issue_sha256'],rows=len(body['rows']),local_candidate_rows=sum(r['candidates']['status']=='read_only_shadow_candidates' for r in body['rows']),
        raw_fallback_rows=sum(r['candidates']['status']=='raw_fallback' for r in body['rows']),origin_contexts=sorted(contexts),issued=apply,selected_pointer_installed=False,local_coverage_qualified=False,probability_claim=False,automatic_actuation=False)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--profile',type=Path,required=True);parser.add_argument('--apply',action='store_true');args=parser.parse_args(argv);deadline=time.monotonic()+90
    def guard():
        if time.monotonic()>=deadline:raise TimeoutError('optional marginal producer deadline elapsed')
    try:
        print(json.dumps(run(args.profile,apply=args.apply,guard=guard)));return 0
    except Exception as error:
        print(json.dumps(dict(status='unavailable',reason=type(error).__name__,retained=None,emission_status='unknown_partial_state',automatic_actuation=False)));return 1

if __name__=='__main__':raise SystemExit(main())
