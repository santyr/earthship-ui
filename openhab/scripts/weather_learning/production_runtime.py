"""Bounded state-only publication runtime; release admission remains external.

No CLI, timer, fitted-model selection, legacy state, network forecast retrieval
or equipment command is installed here. The cutover coordinator must supply its
release/ownership admission and existing resource guard on every run.
"""
from datetime import datetime,timedelta,timezone
import json,pathlib,re,shutil
from urllib.request import Request,build_opener,ProxyHandler
from openhab_runtime_io import SharedScoreLock,BASES,ReadBudget,_NoRedirect
from weather_source_files import _directory,_read,_write
from .archive import Archive
from .config import Site
from .contracts import canonical,identity,instant
from .evidence import utc
from .provider import load_production_forecast,load_publication_forecast,publication_sources
from .production_publish import DETAIL,production_states,publish_cycle

ITEM_TYPES={
 'Forecast_Hourly_JSON':'String','Forecast_Daily_JSON':'String','Forecast_10Day_JSON':'String',
 'Forecast_Temp':'Number:Temperature','Forecast_Cloudiness':'Number:Dimensionless',
 'Forecast_Radiation':'Number:Intensity','Forecast_Daily_High':'Number:Temperature',
 'Forecast_Daily_Low':'Number:Temperature','Forecast_Daily_PrecipSum':'Number:Length',
 'Forecast_Tomorrow_High':'Number','Forecast_Tomorrow_Low':'Number',
}
MAX_RESPONSE_BYTES=262144
MAX_TRANSFER_BYTES=8*1024*1024
MAX_RECORD_BYTES=512*1024
MAX_EVIDENCE_BYTES=2*1024**3
MAX_RECORDS=10000


class OwnershipRefused(ValueError):
    def __init__(self,item,kind):
        if item not in ITEM_TYPES or kind not in ('ITEM_TYPE_OR_OWNER','CHANNEL_LINK_PRESENT'):
            raise ValueError('fixed ownership refusal required')
        super().__init__(kind);self.item=item;self.kind=kind


class ProductionTransport:
    """Only the eleven retained forecast Item states, with bounded readbacks."""
    def __init__(self,*,base,token_reader,budget,opener=None):
        if base not in BASES or not callable(token_reader) or not isinstance(budget,ReadBudget):
            raise ValueError('bounded existing loopback state transport required')
        self.base=base;self.token_reader=token_reader;self.budget=budget
        self.opener=opener or build_opener(ProxyHandler({}),_NoRedirect()).open
        self.total=0;self.checked=set()

    def _request(self,path,*,method='GET',raw=None,before_request):
        if not callable(before_request):raise ValueError('held writer admission required')
        remaining_bytes=MAX_TRANSFER_BYTES-self.total
        if remaining_bytes<=0:raise ValueError('forecast transfer budget exhausted')
        token=self.token_reader()
        if not isinstance(token,str) or not 1<=len(token)<=4096 or any(ord(c)<32 for c in token):
            raise ValueError('bounded existing token required')
        url=self.base+path;headers={'Authorization':'Bearer '+token}
        if raw is not None:headers['Content-Type']='text/plain'
        request=Request(url,method=method,headers=headers,data=None if raw is None else raw.encode())
        timeout=self.budget.begin()
        # Pacing can outlive source/ownership checks; admit after that wait.
        before_request();timeout=min(timeout,self.budget.remaining())
        with self.opener(request,timeout=timeout) as response:
            if hasattr(response,'geturl') and response.geturl()!=url:raise ValueError('forecast transport redirect refused')
            status=getattr(response,'status',200)
            if not 200<=status<300:raise ValueError('forecast state endpoint refused')
            value=response.read(min(MAX_RESPONSE_BYTES,remaining_bytes)+1)
        self.total+=len(value)
        if len(value)>MAX_RESPONSE_BYTES or self.total>MAX_TRANSFER_BYTES:raise ValueError('forecast transfer budget exceeded')
        self.budget.remaining();return value

    def preflight(self,*,before_request):
        self.checked.clear();metadata=[]
        for item,kind in ITEM_TYPES.items():
            value=json.loads(self._request('/items/'+item,before_request=before_request))
            if (not isinstance(value,dict) or value.get('name')!=item or value.get('type')!=kind or
                    value.get('editable') is not False):
                raise OwnershipRefused(item,'ITEM_TYPE_OR_OWNER')
            metadata.append(dict(name=item,type=kind,editable=False))
        links=json.loads(self._request('/links',before_request=before_request))
        if (not isinstance(links,list) or len(links)>10000 or
                any(not isinstance(row,dict) or not isinstance(row.get('itemName'),str) or
                    not isinstance(row.get('channelUID'),str) for row in links)):
            raise ValueError('bounded complete channel-link inventory required')
        for row in links:
            if row['itemName'] in ITEM_TYPES:raise OwnershipRefused(row['itemName'],'CHANNEL_LINK_PRESENT')
        self.checked=set(ITEM_TYPES)
        return identity(dict(items=metadata,channel_linked=False))

    def put(self,item,raw,*,before_request):
        if (item not in ITEM_TYPES or item not in self.checked or not isinstance(raw,str) or
                len(raw.encode())>=65536):raise ValueError('bounded preflighted forecast state required')
        self._request('/items/'+item+'/state',method='PUT',raw=raw,before_request=before_request)

    def read_state(self,item,*,before_request):
        if item not in self.checked:raise ValueError('preflighted forecast state required')
        return self._request('/items/'+item+'/state',before_request=before_request).decode()


def _persist(root,body,kind):
    field='attempt_sha256' if kind=='attempt' else 'result_sha256'
    record=dict(body);record[field]=identity(record);raw=canonical(record)
    if len(raw)>MAX_RECORD_BYTES:raise ValueError('bounded publication evidence required')
    path=_write(root,record[field]+'.publication-'+kind+'-v1.json',raw)
    if _read(path,MAX_RECORD_BYTES)!=raw:raise ValueError('original publication evidence readback differs')
    return path,record


def _capacity(root,check):
    used=0
    for index,path in enumerate(root.glob('*.publication-*-v1.json')):
        if index>=MAX_RECORDS-2:raise ValueError('publication evidence object capacity exhausted')
        used+=path.stat().st_size
        if index%128==0:check()
    if used+2*MAX_RECORD_BYTES>MAX_EVIDENCE_BYTES or shutil.disk_usage(root).free<16*1024**2:
        raise ValueError('insufficient bounded publication evidence capacity')


def run_publication(*,archive,site,evidence_directory,shared_lock,code_revision,transport,
        authorize=None,guard,clock=lambda:datetime.now(timezone.utc),
        required_horizon=timedelta(hours=336),astro_source=None,admission_sha256=None):
    """Publish only after held-lock, release, source and Item-owner admission.

    The result records state readbacks, not a JDBC delivery receipt or scientific
    release assessment. Missing admission has no HTTP or evidence side effects.
    """
    if (not isinstance(archive,Archive) or getattr(archive,'readonly',False) is not True or
            not isinstance(site,Site) or type(transport) is not ProductionTransport or
            not callable(authorize) or not callable(guard) or not callable(clock) or
            not isinstance(code_revision,str) or re.fullmatch('[a-f0-9]{40}',code_revision) is None):
        raise ValueError('explicit Google runtime and release admission required')
    if admission_sha256 is not None and (not isinstance(admission_sha256,str) or re.fullmatch('[a-f0-9]{64}',admission_sha256) is None):
        raise ValueError('original production admission digest required')
    root=_directory(pathlib.Path(evidence_directory));decision=utc(clock())
    with SharedScoreLock(shared_lock) as held:
        guard();held.verify()
        if required_horizon==timedelta(hours=336):
            provider=load_publication_forecast(archive,decision_at=decision,site=site,astro_source=astro_source)
        else:
            provider=load_production_forecast(archive,decision_at=decision,required_horizon=required_horizon,site=site,astro_source=astro_source)
        def check():
            guard();held.verify();now=utc(clock());transport.budget.remaining()
            if not decision<=now<=decision+timedelta(seconds=85):raise ValueError('publication lifetime elapsed')
            if authorize(provider) is not True:raise ValueError('qualified writer admission refused')
        check();states=production_states(provider,now=decision);_capacity(root,check)
        attempt_path,attempt=_persist(root,dict(schema='earthship-weather-publication-attempt/v1',
            started_at=decision.isoformat(),code_revision=code_revision,admission_sha256=admission_sha256,provider=provider.to_dict(),
            states=states,states_sha256=identity(states),release_authorized=False,automatic_actuation=False),'attempt')
        ownership=None;publication=None;failure=None;failed_item=None;status='REFUSED'
        def put(item,raw):
            withdrawal=(raw in ('UNDEF','[]') or (item==DETAIL and json.loads(raw).get('providerStatus')=='UNAVAILABLE'))
            def before():
                check()
                if not withdrawal:
                    sources=publication_sources(provider)
                    if not sources:raise ValueError('no original Google source to serve')
                    for source in sources:
                        archive.read(source['snapshot_sha256'])
                        if utc(clock())-instant(source['initialized_at'])>timedelta(hours=24):
                            raise ValueError('original Google source expired')
            transport.put(item,raw,before_request=before)
        try:
            ownership=transport.preflight(before_request=check)
            publication=publish_cycle(provider,now=decision,put_state=put,
                read_state=lambda item:transport.read_state(item,before_request=check),
                authorize=lambda original:check() is None)
            status=publication['status']
        except Exception as error:
            # Arbitrary guard/transport errors can contain private inputs.
            failure=error.kind if type(error) is OwnershipRefused else type(error).__name__
            failed_item=error.item if type(error) is OwnershipRefused else None
        result_path,result=_persist(root,dict(schema='earthship-weather-publication-run/v1',
            attempt_sha256=attempt['attempt_sha256'],status=status,completed_at=utc(clock()).isoformat(),
            ownership_sha256=ownership,publication=publication,failure_kind=failure,failed_item=failed_item,
            release_authorized=False,automatic_actuation=False),'result')
    return dict(status=status,attempt_path=str(attempt_path),result_path=str(result_path),
        attempt_sha256=attempt['attempt_sha256'],result_sha256=result['result_sha256'],
        release_authorized=False,automatic_actuation=False)
