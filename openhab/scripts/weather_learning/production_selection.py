"""Reviewed explicit production model ownership; no fitting or model promotion."""
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
import json
from household_job_budget import AdmissionDeferred
from weather_source_files import _read,_directory
from .contracts import canonical,digest,identity,instant
from .evidence import utc
from .config import Site
from .production_training import read_production
from .production_model_admission import _authorization,_validate
from .production_forecast import prepare_production_forecast
from .probabilistic_issue import temperature_context,wind_context
from .production_emissions import retain_prepared,confirm_publication
from .shadow import ShadowStore

SCHEMA='earthship-selected-weather-production-profile/v1'
FIELDS={'schema','archive','state','site','models','temperature_policy','temperature_db_config','runtime_sha256','authorization_policy_sha256','parallel_shadow_required','automatic_actuation'}
MODEL_FIELDS={'bundle_sha256','artifact_sha256','model_sha256','admission_sha256'}
ROOT=Path(__file__).resolve().parents[3]


class ProductionSelection:
    def __init__(self,path,*,expected_sha256,archive,site,clock,guard):
        from .production_worker import _path,_json,runtime_manifest
        digest(expected_sha256)
        if not isinstance(site,Site) or not callable(clock) or not callable(guard):raise ValueError('explicit production owner context required')
        self.path=_path(str(path));self.raw=_read(self.path,131072);self._data=_json(self.raw);self.clock=clock;self.guard=guard
        value=self._data
        if (sha256(self.raw).hexdigest()!=expected_sha256 or not isinstance(value,dict) or set(value)!=FIELDS or value['schema']!=SCHEMA or
                value['parallel_shadow_required'] is not False or value['automatic_actuation'] is not False or value['site']!=site.__dict__ or
                _path(value['archive'])!=archive.root or value['runtime_sha256']!=identity(runtime_manifest()) or
                not isinstance(value['models'],list) or not 1<=len(value['models'])<=12):
            raise ValueError('exact reviewed production selection profile required')
        self.archive=archive;self.site=site;self.profile_sha256=expected_sha256;self.root=_path(value['state']);_directory(self.root)
        self.policy=_json(_read(ROOT/'docs/operations/weathernext3-capabilities/marginal-calibration-protocol.json',65536,source=True))
        authorization=_json(_read(ROOT/'docs/operations/weathernext3-capabilities/deployment-policy.json',65536,source=True))
        _authorization(authorization,value['authorization_policy_sha256'])
        if (value['temperature_policy'] is None)!=(value['temperature_db_config'] is None):raise ValueError('paired native temperature policy/database required')
        self._configuration_files={}
        for name,limit in (('temperature_policy',65536),('temperature_db_config',4096)):
            if value[name] is not None:
                p=_path(value[name]);self._configuration_files[p]=(_read(p,limit),limit)
        self._models=[];self._files={};self._allowed={};seen=set()
        state=SimpleNamespace(root=self.root)
        for spec in value['models']:
            guard()
            if not isinstance(spec,dict) or set(spec)!=MODEL_FIELDS:raise ValueError('explicit closed selected model identity required')
            for pin in spec.values():digest(pin)
            if spec['bundle_sha256'] in seen:raise ValueError('unique selected production bundles required')
            seen.add(spec['bundle_sha256']);artifact=self.root/'production-models'/(spec['artifact_sha256']+'.json')
            original=_read(artifact,16*1024**2);bundle=read_production(state,spec['artifact_sha256'],policy=self.policy)
            if _read(artifact,16*1024**2)!=original:raise ValueError('selected model artifact changed during read')
            admission_path=self.root/'production-admissions'/(spec['admission_sha256']+'.json');admission_raw=_read(admission_path,65536);admission=_json(admission_raw)
            body=bundle.to_dict()
            if (body['bundle_sha256']!=spec['bundle_sha256'] or admission.get('model_sha256')!=spec['model_sha256'] or
                    admission.get('admission_sha256')!=spec['admission_sha256'] or admission.get('authorization_policy_sha256')!=value['authorization_policy_sha256']):
                raise ValueError('original registered production model/admission differs')
            # Validate original admission at its real admission clock. Expiry at
            # serving time remains a named raw fallback in the point adapter.
            _validate(bundle,admission,policy=self.policy,at=instant(admission['admitted_at']))
            self._models.append((bundle,admission));self._allowed[spec['admission_sha256']]=canonical(admission)
            self._files[artifact]=(sha256(original).hexdigest(),16*1024**2)
            self._files[admission_path]=(sha256(admission_raw).hexdigest(),65536)
        self.contexts={};self._prepared=None;self._used_expiries={};self.verify()

    @property
    def models(self):return tuple((b,json.loads(canonical(a))) for b,a in self._models)

    def _selection(self):
        self.guard()
        if _read(self.path,131072)!=self.raw:raise ValueError('reviewed production selection profile changed')
        for path,(raw,limit) in self._configuration_files.items():
            if _read(path,limit)!=raw:raise ValueError('selected production measurement configuration changed')

    def verify(self,product=None):
        self._selection()
        for path,(pin,limit) in self._files.items():
            if sha256(_read(path,limit)).hexdigest()!=pin:raise ValueError('original selected production model artifact changed')
        if product is not None:
            if product.to_dict()['issue_sha256']!=self._prepared:raise ValueError('original selected production preparation required')
            now=utc(self.clock())
            if any(now>=expiry for expiry in self._used_expiries.values()):raise ValueError('selected production model expired before transport')
        return True

    def authorize(self,receipt):
        self._selection()
        return self._allowed.get(receipt.get('admission_sha256'))==canonical(receipt)

    def capture_contexts(self,*,temperature_reader=None):
        self.verify();self.contexts={};value=self._data
        if value['temperature_policy'] is None:return
        from hourly_temperature_runtime import _native_outdoor_policy,read_db_config
        from weather_temperature_history import fetch_temperature_grid_v2
        try:
            policy,epoch=_native_outdoor_policy(value['temperature_policy']);sampled=utc(self.clock())
            if temperature_reader is None:
                import psycopg2
                config=read_db_config(value['temperature_db_config'])
                rows=fetch_temperature_grid_v2(lambda:psycopg2.connect(**config,connect_timeout=3),targets=[sampled],assessed_at=sampled,stream='outdoor',policy=policy,sensor_epoch=epoch)
                metadata=dict(rows).get(sampled)
            else:metadata=temperature_reader(sampled,policy,epoch)
            acquired=utc(self.clock());self._selection()
            if metadata is not None:self.contexts['temperature']=temperature_context(metadata,sampled_at=sampled,acquired_at=acquired,sensor_epoch=epoch)
        except (TimeoutError,AdmissionDeferred,MemoryError):raise
        except Exception:
            # A missing measurement input withholds only that local target.
            # Configuration/owner changes still fail globally after this scope.
            self._selection()

    def prepare(self,decision,provider):
        self.verify();contexts=dict(self.contexts,wind=wind_context(decision=decision))
        product=prepare_production_forecast(provider=provider,read_source=self.archive.read,contexts=contexts,models=self._models,
            policy=self.policy,authorize=self.authorize,guard=self.guard)
        body=product.to_dict();self._prepared=body['issue_sha256'];used={r['prediction']['admission_sha256'] for r in body['rows'] if r['prediction'] is not None}
        self._used_expiries={a['admission_sha256']:instant(a['valid_until']) for _,a in self._models if a['admission_sha256'] in used}
        self.verify(product);return product

    def retain(self,product,provider,attempt,result):
        if result is None:
            self.verify(product);return retain_prepared(ShadowStore(self.root),product,provider=provider,now=instant(product.to_dict()['decision_at']))
        # Publication already happened. Keep the actual success even if an
        # owner/configuration subsequently changes; do not renew its clocks.
        state=ShadowStore(self.root);emission=confirm_publication(state,product,provider=provider,attempt=attempt,result=result)
        from .production_queue import ProductionQueue
        ProductionQueue(state).register(emission['emission_sha256'])
        from .production_public import retain_public_view
        retain_public_view(state,emission['emission_sha256']);return emission


def from_profile(path,*,expected_sha256,archive,site,clock,guard):
    return ProductionSelection(path,expected_sha256=expected_sha256,archive=archive,site=site,clock=clock,guard=guard)
