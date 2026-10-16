"""Source-bound daily load artifacts; replay uses retained originals only."""
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
import sys,math
from household.codec import canonical,loads,identity
from household.evidence import utc,digest
from household.control_contracts import instant
from household_ac_load_model import fit_profile,replay_profile,_zone,POLICY
from household_ac_load_sources import replay_day_source,summarize_day

SCHEMA='earthship-ac-load-model-artifact/v1'
FIELDS={'schema','cutoff','trained_at','days','dataset_sha256','runtime_manifest','profile','automatic_actuation','artifact_sha256'}


def runtime_manifest():
    import earthship_energy.ac_evidence as ac
    root=Path(__file__).resolve().parent
    paths={'openhab/scripts/'+name:root/name for name in (
        'household_ac_load_artifact.py','household_ac_load_store.py','household_ac_load_model.py','household_ac_load_sources.py','household_ac_load_transport.py',
        'household/codec.py','household/control_contracts.py','household/evidence.py')}
    companion=Path(ac.__file__).parent
    paths.update({'companion/earthship_energy/'+name:companion/name for name in ('ac_evidence.py','power_evidence.py','power_intervals.py')})
    paths['runtime/America-Denver-zoneinfo']=Path('/usr/share/zoneinfo/America/Denver')
    paths['runtime/python-executable']=Path(sys.executable).resolve()
    from thermal_model.origin_capture import _source_bytes
    from household_snapshot import _read
    # Match the existing household source-manifest contract for repository and
    # companion files. The resolved executable retains its stricter trust check.
    values={name:sha256(_source_bytes(path,maximum=64*1024**2) if name=='runtime/python-executable' else _read(path,262144)).hexdigest() for name,path in paths.items()}
    values['runtime/python-version']=identity(dict(version=sys.version))
    return values


def build_artifact(*,sources,cutoff,trained_at,runtime_manifest):
    cutoff,trained=utc(cutoff),utc(trained_at);zone=_zone('America/Denver');local=cutoff.astimezone(zone)
    if local!=local.replace(hour=0,minute=0,second=0,microsecond=0) or trained<cutoff:raise ValueError('completed original load cutoff required')
    if not isinstance(sources,list) or len(sources)!=POLICY['lookback_days']:raise ValueError('complete original lookback day set required')
    if not isinstance(runtime_manifest,dict) or not 1<=len(runtime_manifest)<=32 or any(not isinstance(k,str) or not k for k in runtime_manifest):raise ValueError('bounded original load runtime required')
    runtime={k:digest(v) for k,v in runtime_manifest.items()};days=[];hours=[];mapping=None
    for i,source in enumerate(sources):
        source=replay_day_source(source)
        start=(local-timedelta(days=POLICY['lookback_days']-i)).astimezone(cutoff.tzinfo)
        end=(local-timedelta(days=POLICY['lookback_days']-i-1)).astimezone(cutoff.tzinfo)
        if instant(source['window_start'])!=start or instant(source['window_end'])!=end or instant(source['received_at'])>trained:
            raise ValueError('complete chronological original day availability required')
        if mapping is not None and source['item_id']!=mapping:raise ValueError('stable original AC Item mapping required')
        mapping=source['item_id'];account=summarize_day(source);rows=account['hourly_rows'];hours.extend(rows)
        covered=math.fsum(row['covered_seconds'] for row in rows)
        days.append(dict(window_start=start.isoformat(),window_end=end.isoformat(),source_sha256=source['source_sha256'],
            source_document_sha256=identity(source),item_id=mapping,status=account['status'],reason=account['reason'],
            accounting_sha256=identity(account),covered_seconds=covered,missing_seconds=(end-start).total_seconds()-covered,
            known_ac_kwh=math.fsum(row['known_ac_kwh'] for row in rows)))
    value=dict(schema=SCHEMA,cutoff=cutoff.isoformat(),trained_at=trained.isoformat(),days=days,dataset_sha256=identity(days),runtime_manifest=runtime,
        profile=fit_profile(hourly_rows=hours,training_end=cutoff,trained_at=trained),automatic_actuation=False)
    value['artifact_sha256']=identity(value)
    if len(canonical(value))>262144:raise ValueError('bounded compact load artifact required')
    return loads(canonical(value))


def verify_compact(artifact,*,runtime_manifest):
    if (not isinstance(artifact,dict) or set(artifact)!=FIELDS or artifact['schema']!=SCHEMA or len(canonical(artifact))>262144 or
        artifact['automatic_actuation'] is not False or identity({k:v for k,v in artifact.items() if k!='artifact_sha256'})!=artifact['artifact_sha256'] or
        canonical(artifact['runtime_manifest'])!=canonical(runtime_manifest) or identity(artifact['days'])!=artifact['dataset_sha256']):
        raise ValueError('unchanged admitted load artifact and runtime required')
    replay_profile(artifact['profile'])
    if artifact['profile']['inputs']['training_end']!=artifact['cutoff'] or artifact['profile']['inputs']['trained_at']!=artifact['trained_at']:
        raise ValueError('original load profile training clocks differ')
    return loads(canonical(artifact))


def replay_artifact(artifact,*,sources,runtime_manifest):
    verify_compact(artifact,runtime_manifest=runtime_manifest)
    value=build_artifact(sources=sources,cutoff=instant(artifact['cutoff']),trained_at=instant(artifact['trained_at']),runtime_manifest=runtime_manifest)
    if canonical(value)!=canonical(artifact):raise ValueError('original load source accounting or model differs')
    return value
