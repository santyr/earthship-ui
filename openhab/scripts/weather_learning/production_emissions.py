"""Immutable selected production originals and confirmed OpenHAB emissions.

Prepared and issued are different identities. A confirmed emission binds the
original state bytes and successful per-Item readbacks; later process failure
cannot erase those originals or turn an unsuccessful write into a forecast.
"""
from datetime import timedelta
import base64,gzip,io,json
from hashlib import sha256
from .contracts import canonical,identity,digest,instant
from .production_forecast import ProductionForecast,SCHEMA,_original
from .production_publish import production_states,DETAIL
from .provider import ProviderSnapshot
from .shadow import _directory,_read

SCORE_OFFSETS=(1,2,3,4,6,9,12,18,24,36,48,60,72,96,120,144,168,192,216,240,264,288,312,336)
EMISSION_SCHEMA='earthship-confirmed-production-weather-emission/v1'


def _checked(value,key):
    if not isinstance(value,dict) or value.get(key)!=identity({k:v for k,v in value.items() if k!=key}):
        raise ValueError('unchanged original production object required')
    return value


def retain_prepared(state,product,*,provider,now):
    body=_original(product,provider,now);pin=body['issue_sha256'];_directory(state.root/'production-issues')
    path=state.root/'production-issues'/(pin+'.json')
    if path.exists():
        if read_issue(state,pin).to_dict()!=body:raise ValueError('original retained production issue differs')
        return pin
    raw=canonical(body)
    if len(raw)>16*1024**2:raise ValueError('bounded original production issue required')
    capsule=dict(schema='earthship-production-issue-lossless-capsule/v1',issue_sha256=pin,
        uncompressed_bytes=len(raw),original_bytes_sha256=sha256(raw).hexdigest(),
        gzip_base64=base64.b64encode(gzip.compress(raw,mtime=0)).decode())
    capsule['capsule_sha256']=identity(capsule)
    state._write(path,capsule,immutable=True)
    if read_issue(state,pin).to_dict()!=body:raise ValueError('production original readback differs')
    return pin


def read_issue(state,pin):
    digest(pin);body=_read(state.root/'production-issues'/(pin+'.json'),16*1024**2)
    if body.get('schema')=='earthship-production-issue-lossless-capsule/v1':
        _checked(body,'capsule_sha256')
        if (set(body)!={'schema','issue_sha256','uncompressed_bytes','original_bytes_sha256','gzip_base64','capsule_sha256'} or
                body['issue_sha256']!=pin or type(body['uncompressed_bytes']) is not int or not 0<body['uncompressed_bytes']<=16*1024**2):
            raise ValueError('bounded original production capsule required')
        try:
            packed=base64.b64decode(body['gzip_base64'],validate=True)
            with gzip.GzipFile(fileobj=io.BytesIO(packed)) as stream:raw=stream.read(16*1024**2+1)
            if len(raw)!=body['uncompressed_bytes'] or sha256(raw).hexdigest()!=body['original_bytes_sha256']:
                raise ValueError('bounded original production capsule bytes differ')
            body=json.loads(raw)
        except (OSError,EOFError,TypeError,ValueError) as error:
            raise ValueError('bounded original production capsule required') from error
    _checked(body,'issue_sha256')
    if (body['issue_sha256']!=pin or body.get('schema')!=SCHEMA or
            any(body.get(k) is not False for k in ('issued','local_coverage_qualified','probability_claim','automatic_actuation'))):
        raise ValueError('original prepared production forecast required')
    product=object.__new__(ProductionForecast);object.__setattr__(product,'_raw',canonical(body));return product


def _confirmation(product,provider,attempt,result):
    body=product.to_dict();decision=instant(body['decision_at']);states=production_states(provider,now=decision,production=product)
    _checked(attempt,'attempt_sha256');_checked(result,'result_sha256');publication=result.get('publication')
    if (attempt.get('provider')!=provider.to_dict() or attempt.get('started_at')!=body['decision_at'] or attempt.get('states')!=states or
            attempt.get('states_sha256')!=identity(states) or result.get('attempt_sha256')!=attempt['attempt_sha256'] or
            result.get('status')!='PUBLISHED' or not isinstance(publication,dict) or publication.get('status')!='PUBLISHED' or
            publication.get('production_issue_sha256')!=body['issue_sha256'] or publication.get('states_sha256')!=identity(states) or
            set(publication.get('verified_items',[]))!=set(states) or len(publication['verified_items'])!=len(states) or
            publication.get('failed_item') is not None or publication.get('withdrawal_attempts')!=[] or publication.get('unconfirmed_withdrawals')!=[]):
        raise ValueError('original confirmed complete production publication required')
    _checked(publication,'result_sha256');emitted=instant(result['completed_at'])
    if not decision<=emitted<=decision+timedelta(seconds=85):raise ValueError('original production publication lifetime exceeded')
    detail=json.loads(states[DETAIL]);indexed={(r['profile'],r['kind'],instant(r['at'])):r for r in body['rows']};published=[];scored=[]
    first=decision.replace(minute=0,second=0,microsecond=0)+timedelta(hours=1)
    for day in detail['days']:
        for hour in day['hours']:
            at=instant(hour['at']);profile=hour.get('forecastProfile','extended')
            for kind in ('temperature','wind'):
                row=indexed[(profile,kind,at)];frame=row['forecast']
                # Only rows present in the actual emitted hourly JSON are issued
                # here. Native instantaneous wind is a different target.
                if kind=='wind' and hour.get('windMeanMph') is None:continue
                ref=dict(kind=kind,at=row['at'],profile=profile,row_sha256=identity(row))
                published.append(ref)
                offset=1+int((at-first).total_seconds()/3600)
                if (offset in SCORE_OFFSETS and frame is not None and emitted<at and
                        (kind=='temperature' or instant(frame['target_start'])>=emitted)):
                    scored.append(ref)
    if len(scored)>48:raise ValueError('bounded declared production score targets required')
    return dict(schema=EMISSION_SCHEMA,issue_sha256=body['issue_sha256'],published_at=emitted.isoformat(),
        attempt_sha256=attempt['attempt_sha256'],result_sha256=result['result_sha256'],states_sha256=identity(states),
        attempt_original=attempt,publication_original=result,published_rows=published,score_rows=scored,
        evaluation_population='actual_published_hourly_points_at_predeclared_offsets',score_offsets=list(SCORE_OFFSETS),
        issued=True,parallel_shadow_required=False,local_coverage_qualified=False,probability_claim=False,automatic_actuation=False)


def confirm_publication(state,product,*,provider,attempt,result):
    original=read_issue(state,product.to_dict()['issue_sha256'])
    if original.to_dict()!=product.to_dict():raise ValueError('exact retained production original required')
    emission=_confirmation(product,provider,attempt,result);emission['emission_sha256']=identity(emission)
    _directory(state.root/'production-emissions');state._write(state.root/'production-emissions'/(emission['emission_sha256']+'.json'),emission,immutable=True)
    return emission


def read_emission(state,pin):
    digest(pin);value=_checked(_read(state.root/'production-emissions'/(pin+'.json'),16*1024**2),'emission_sha256')
    if value.get('emission_sha256')!=pin or value.get('schema')!=EMISSION_SCHEMA:raise ValueError('original confirmed production emission required')
    product=read_issue(state,value['issue_sha256']);provider=object.__new__(ProviderSnapshot)
    object.__setattr__(provider,'_raw',canonical(value['attempt_original']['provider']))
    rebuilt=_confirmation(product,provider,value['attempt_original'],value['publication_original']);rebuilt['emission_sha256']=identity(rebuilt)
    if value!=rebuilt:raise ValueError('original published prediction membership differs')
    return value
