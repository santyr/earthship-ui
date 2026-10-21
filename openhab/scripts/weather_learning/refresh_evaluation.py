"""Original publication populations and past-only refresh-policy preparation.

The daily-first-issue benchmark is untouched. A 48h/360h label here describes
retained collection coverage, not an inferred provider product class or schedule.
No acquisition, fitting, publication, calibration selection or control authority.
"""
from datetime import timedelta
import json

from .archive import Archive
from .config import Site
from .contracts import canonical,digest,identity,instant
from .evidence import utc
from .provider import REQUIRED,TEMPERATURE,load_production_forecast


class RefreshRecord:
    __slots__=('_raw',)
    def __init__(self,*args,**kwargs):raise TypeError('prepare from original decisions')
    def __setattr__(self,name,value):raise AttributeError('refresh record is immutable')
    def to_dict(self):return json.loads(self._raw)


def _freeze(body):
    body=dict(body);body['record_sha256']=identity(body)
    value=object.__new__(RefreshRecord)
    object.__setattr__(value,'_raw',canonical(body));return value


def _checked(value,key):
    if not isinstance(value,dict) or value.get(key)!=identity({k:v for k,v in value.items() if k!=key}):
        raise ValueError('unchanged original publication digest required')
    return value


def _context(archive,site):
    if not isinstance(archive,Archive) or not isinstance(site,Site):
        raise ValueError('original archive and authoritative site required')


class _PinnedArchive:
    """Rebuild one originally selected source, never substitute today's winner."""
    def __init__(self,snapshot):self.snapshot=snapshot
    def eligible_snapshot(self,decision,target_end,*,required_variables):
        value=self.snapshot
        initialized=instant(value['initialized_at'])
        if (value['historical'] or not initialized<=instant(value['first_seen_at'])<=instant(value['ingestion_completed_at'])<=decision
                or decision-initialized>timedelta(hours=24)):
            raise ValueError('original source unavailable at decision')
        first=decision.replace(minute=0,second=0,microsecond=0)+timedelta(hours=1)
        for variable in required_variables:
            times={instant(p['valid_at']) for p in value['points'] if p['variable']==variable and p['statistic']=='mean' and p['value'] is not None}
            at=first
            while at<=target_end:
                if at not in times:return None
                at+=timedelta(hours=1)
        return value


def _provider(snapshot,*,decision,site,horizon):
    value=load_production_forecast(_PinnedArchive(snapshot),decision_at=decision,required_horizon=horizon,site=site).to_dict()
    if value['status']!='AVAILABLE':raise ValueError('complete rederived original profile required')
    return value


def _source(profile,snapshot,decision):
    required=set(profile['required_variables']);last=[]
    for variable in required:
        times=[instant(p['valid_at']) for p in snapshot['points'] if p['variable']==variable and p['statistic']=='mean' and p['value'] is not None]
        if not times:raise ValueError('original profile coverage unavailable')
        last.append(max(times))
    source=dict(profile['source']);initialized=instant(source['initialized_at']);completed=instant(source['ingestion_completed_at'])
    source.update(initialization_age_hours=(decision-initialized).total_seconds()/3600,
        availability_lag_hours=(completed-initialized).total_seconds()/3600,
        remaining_native_hours=(min(last)-decision).total_seconds()/3600)
    return source


def _series(profile):
    return [dict(at=row['at'],raw_c=(row['temp_f']-32)*5/9) for row in profile['hours']]


def refresh_profiles(archive,*,decision_at,site):
    """Latest eligible 48h-collection and 360h-collection on the next 24h.

    Native originals determine retained coverage. This deliberately does not
    pretend a truncated full run is proven to be Google's interim product.
    Index/original disagreement is fatal, rather than fabricating availability.
    The bounded 256-object policy is explicit in the resulting record.
    """
    _context(archive,site);decision=utc(decision_at);profiles={}
    with archive._connect() as db:
        rows=db.execute('SELECT digest,initialized,first_seen,completed FROM snapshots WHERE historical=0 AND first_seen<=? AND completed<=? AND initialized>=? ORDER BY initialized DESC,completed DESC,digest LIMIT 257',
            (decision.isoformat(),decision.isoformat(),(decision-timedelta(hours=24)).isoformat())).fetchall()
    if len(rows)>256:raise ValueError('bounded refresh candidate scan exhausted')
    inspected=0
    for name,initialized,seen,completed in rows:
        snapshot=archive.read(name);inspected+=1
        if tuple(map(instant,(initialized,seen,completed)))!=tuple(instant(snapshot[k]) for k in ('initialized_at','first_seen_at','ingestion_completed_at')):
            raise ValueError('original source clocks differ from index')
        # All native capsules must have the same requested collection horizon.
        lengths={len(s['payload'].get('metadata',[])) for s in snapshot['source_originals']}
        if len(lengths)!=1 or next(iter(lengths)) not in (48,360):continue
        horizon=next(iter(lengths));key=f'latest_{horizon}h_collection'
        if key in profiles:continue
        # A wrong-site newest original cannot be relabeled as the requested site.
        if snapshot['site']!=site.__dict__:raise ValueError('original site differs')
        candidate=load_production_forecast(_PinnedArchive(snapshot),decision_at=decision,
            required_horizon=timedelta(hours=24),site=site).to_dict()
        if candidate['reason']=='INVALID_SOURCE':raise ValueError('invalid original refresh source')
        if candidate['status']!='AVAILABLE':continue
        profiles[key]=dict(status='AVAILABLE',reason=None,retained_collection_hours=horizon,
            required_horizon_hours=24,source=_source(candidate,snapshot,decision),
            served_hours=len(candidate['hours']),hours=_series(candidate),issue_sha256=candidate['issue_sha256'])
    for horizon in (48,360):
        profiles.setdefault(f'latest_{horizon}h_collection',dict(status='UNAVAILABLE',reason='NO_KNOWN_COMPLETE_COLLECTION',
            retained_collection_hours=horizon,required_horizon_hours=24,source=None,served_hours=0,hours=[],issue_sha256=None))
    return _freeze(dict(schema='earthship-refresh-profiles/v1',decision_at=decision.isoformat(),
        profiles=profiles,candidate_objects_inspected=inspected,candidate_limit=256,coverage='all_indexed_candidates_within_24h_or_refuse',
        source_class_basis='retained_collection_horizon_not_nominal_provider_product',probability_claim=False,automatic_actuation=False))


def _replay_profile(profile,archive,decision,site):
    _checked(profile,'provider_snapshot_sha256')
    if profile['decision_at']!=decision.isoformat() or profile['timezone']!=site.timezone:
        raise ValueError('original profile decision/site differs')
    if profile['source'] is None:
        if profile['hours'] or profile['days'] or profile['issue_sha256'] is not None:
            raise ValueError('unavailable original profile contains predictions')
        return profile,None
    snapshot=archive.read(profile['source']['snapshot_sha256'])
    rebuilt=_provider(snapshot,decision=decision,site=site,horizon=timedelta(seconds=profile['required_horizon_seconds']))
    # Solar context is separately acquired, and does not enter temperature
    # policy evaluation. Everything else must replay from the original source.
    for key in ('schema','provider','decision_at','required_horizon_seconds','timezone','required_variables','status','reason','source','issue_sha256','learning_namespace','model','hours','days','release_authorized','automatic_actuation'):
        if profile[key]!=rebuilt[key]:raise ValueError('published profile differs from original source: '+key)
    return profile,snapshot


def publication_decision(attempt,result,*,archive,site):
    """Validate an actual successful attempt/result and replay its exact sources.

    These are recorded forecasts, not a rerun of selection against a later index.
    State readback is evidence of publication, not JDBC delivery or label quality.
    The returned series overlays only the retained near-term hours; extended
    summaries and each separate profile remain identifiable.
    """
    _context(archive,site);_checked(attempt,'attempt_sha256');_checked(result,'result_sha256')
    if (attempt['schema']!='earthship-weather-publication-attempt/v1' or result['schema']!='earthship-weather-publication-run/v1'
            or result['attempt_sha256']!=attempt['attempt_sha256']):raise ValueError('original publication pair differs')
    decision=instant(attempt['started_at']);completed=instant(result['completed_at'])
    if completed<decision:raise ValueError('original publication completion precedes decision')
    if result['status']!='PUBLISHED' or result['failure_kind'] is not None:
        raise ValueError('confirmed published population required')
    provider=_checked(attempt['provider'],'provider_snapshot_sha256')
    published=_checked(result['publication'],'result_sha256')
    if (published['status']!='PUBLISHED' or published['failed_item'] is not None or published['unconfirmed_withdrawals']
            or published['provider_snapshot_sha256']!=provider['provider_snapshot_sha256']
            or published['states_sha256']!=attempt['states_sha256'] or attempt['states_sha256']!=identity(attempt['states'])):
        raise ValueError('original published state binding differs')
    from .production_publish import production_states
    from .provider import _freeze as freeze_provider
    if set(published['verified_items'])!=set(attempt['states']) or len(published['verified_items'])!=len(attempt['states']):
        raise ValueError('all original published Item readbacks required')
    body={k:v for k,v in provider.items() if k!='provider_snapshot_sha256'}
    if production_states(freeze_provider(body),now=decision)!=attempt['states']:
        raise ValueError('original publication states differ from retained provider')
    profiles={};composite=provider['schema']=='earthship-weathernext-publication-provider/v2'
    if composite:
        near=provider['near_term']
        extended={k:v for k,v in provider.items() if k not in ('near_term','extended_status','extended_reason','provider_snapshot_sha256')}
        extended.update(schema='earthship-weathernext-provider/v1',status=provider['extended_status'],reason=provider['extended_reason'])
        extended['provider_snapshot_sha256']=identity(extended)
        candidates=(('extended',extended),('near_term',near))
    elif provider['schema']=='earthship-weathernext-provider/v1':candidates=(('single',provider),)
    else:raise ValueError('supported original publication provider required')
    hours={}
    for key,profile in candidates:
        profile,snapshot=_replay_profile(profile,archive,decision,site)
        series=_series(profile)
        profiles[key]=dict(source=None if snapshot is None else _source(profile,snapshot,decision),
            status=profile['status'],issue_sha256=profile['issue_sha256'],hours=series,
            required_horizon_hours=profile['required_horizon_seconds']/3600)
        for row in series:hours[row['at']]=dict(row,profile=key)
    for value in (attempt,result,published,provider):
        if value.get('release_authorized') is not False or value.get('automatic_actuation') is not False:
            raise ValueError('original read-only publication authority required')
    digest(attempt['attempt_sha256']);digest(result['result_sha256'])
    return _freeze(dict(schema='earthship-recorded-publication-decision/v1',population='actual_publication_decisions_v1',
        decision_at=decision.isoformat(),publication_completed_at=completed.isoformat(),
        publication_latency_seconds=(completed-decision).total_seconds(),
        code_revision=attempt['code_revision'],attempt_sha256=attempt['attempt_sha256'],result_sha256=result['result_sha256'],
        provider_sha256=provider['provider_snapshot_sha256'],profiles=profiles,hours=sorted(hours.values(),key=lambda r:r['at']),
        prospective_score=True,probability_claim=False,automatic_actuation=False))
