"""Private configuration and restricted originals for the household cycle."""
from pathlib import Path
from http.client import HTTPException
import re
from household.codec import loads
from household_observation import _private_file

CONFIG_FIELDS={'schema','forecast_config','retained_energy_parameters','parameters_sha256','evidence_directory','observation_cache'}
PATH_FIELDS={'forecast_config','retained_energy_parameters','evidence_directory','observation_cache'}


def load_cycle_settings(path):
    raw,_=_private_file(Path(path).absolute(),8192)
    value=loads(raw)
    if set(value)!=CONFIG_FIELDS or value['schema']!='earthship-household-cycle-config/v1':
        raise ValueError('closed private household cycle configuration required')
    if not isinstance(value['parameters_sha256'],str) or re.fullmatch('[a-f0-9]{64}',value['parameters_sha256']) is None:
        raise ValueError('original parameter digest required')
    for key in PATH_FIELDS:
        text=value[key]
        if not isinstance(text,str) or not 1<=len(text)<=4096:
            raise ValueError('bounded original path required')
        original=Path(text)
        if not original.is_absolute() or original.resolve()!=original:
            raise ValueError('fixed resolved original path required')
    if value['forecast_config']==value['observation_cache'] or value['retained_energy_parameters']==value['observation_cache']:
        raise ValueError('source cannot be a publication target')
    return value

from datetime import datetime,timedelta,timezone
from hashlib import sha256
import math,signal,threading,urllib.request
from household.codec import canonical
from household.evidence import utc
from household_capture import _connection
from household_cycle_deadline import MAX_OBSERVATION_SECONDS

DAILY_STATE_PATH=Path('/home/sat/.local/state/forecast-intel/state.json')
DAILY_RECEIPT_ITEM='Forecast_Prediction_Receipt_JSON'
METRIC_PATH=Path('/home/sat/Solar_PV/analytics/config/metric-sources.json')
LOAD_TOPOLOGY_PATH=Path(__file__).resolve().parents[2]/'openhab/household-energy-topology.json'

PRIVATE_PATHS={
    'energy_db':Path('/home/sat/.config/hex/energy-power-reader.jdbc'),
    'native_db':Path('/home/sat/.config/hex/weather-temperature-db.json'),
    'native_policy':Path('/home/sat/.config/hex/weather-temperature-policy-v2.json'),
}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ValueError('fixed owner redirect refused')


class CycleSourceCollector:
    """Gather original fixed receipts, never a supplied scalar or action."""
    def __init__(self,*,token_file,openhab_base,code_revision,clock=lambda:datetime.now(timezone.utc),owner_reader=None,rule_reader=None,policy_reader=None):
        from thermal_model.capture_readers import BASES
        from weather_temperature_config import load_temperature_receiver_configuration
        from household_pipeline import pipeline_runtime_manifest
        from household_snapshot import ROOT,_read
        if openhab_base not in BASES:raise ValueError('fixed local owner required')
        if not isinstance(code_revision,str) or re.fullmatch('[a-f0-9]{40}',code_revision) is None:
            raise ValueError('source code identity required')
        if set(PRIVATE_PATHS)!={'energy_db','native_db','native_policy'}:raise ValueError('fixed complete source paths required')
        self.paths={**PRIVATE_PATHS,'token':Path(token_file).absolute()}
        self.private={name:_private_file(path,16384 if name=='token' else 8192) for name,path in self.paths.items()}
        self.token=self.private['token'][0].decode().strip()
        if not self.token or any(char in self.token for char in '\r\n'):raise ValueError('original token required')
        self.energy=_connection(str(self.paths['energy_db']),'energy_power_reader')
        self.native=_connection(str(self.paths['native_db']),'weather_temperature_reader')
        self.policies,self.phases=load_temperature_receiver_configuration(str(self.paths['native_policy']))
        if self.phases is None:raise ValueError('original hardware phases required')
        self.clock=clock;self.base=openhab_base;self.code_revision=code_revision
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),_NoRedirect())
        self.owner_reader=owner_reader or self._owner_http
        self.rule_reader=rule_reader or self._rules_http
        self.policy_reader=policy_reader or self._policy_http
        self.runtime_reader=lambda:pipeline_runtime_manifest(expanded=True,configured=True,measured=True)
        self.runtime=self.runtime_reader()
        self.registry_paths={'managed':ROOT/'openhab/managed-resources.json','ownership':ROOT/'openhab/file-config/ownership.json'}
        self.registry={name:_read(path,262144) for name,path in self.registry_paths.items()}
        from household.energy_configuration_capture import FIXED_PATHS,_owned_text
        from household.energy_configuration import SOURCES as CONFIGURATION_SOURCES
        from household.measured_weather_capture import FIXED_POLICY_PATHS
        self.policy_bindings=[(path,CONFIGURATION_SOURCES[kind][1],_owned_text(path,CONFIGURATION_SOURCES[kind][1],lambda:6.))
            for kind,path in FIXED_PATHS.items()]
        self.policy_bindings.extend((path,4096,_owned_text(path,4096,lambda:6.)) for path in FIXED_POLICY_PATHS.values())
        from household.power_flows import prepare_topology_source
        self.load_topology_source=None
        try:
            original=_owned_text(LOAD_TOPOLOGY_PATH,4096,lambda:6.)
            self.policy_bindings.append((LOAD_TOPOLOGY_PATH,4096,original))
            if original[0] is not None:
                self.load_topology_source=prepare_topology_source(original[0].encode('utf-8'),available_at=utc(self.clock()))
        except (OSError,ValueError,UnicodeError,RecursionError):
            self.load_topology_source=None
        # Optional original sign/unit declaration. Malformed configuration
        # withholds the new baseline while preserving the other domains.
        from household.energy_persistence import METRIC_MAX_BYTES,METRIC_IDENTITY
        self.metric_source=None
        try:
            original=_owned_text(METRIC_PATH,METRIC_MAX_BYTES,lambda:6.)
            self.policy_bindings.append((METRIC_PATH,METRIC_MAX_BYTES,original))
            raw=original[0]
            if raw is not None:
                loads(raw)
                from hashlib import sha256
                self.metric_source=dict(schema='earthship-household-battery-metric-source/v1',source_identity=METRIC_IDENTITY,
                    raw=raw,sha256=sha256(raw.encode()).hexdigest(),available_at=utc(self.clock()).isoformat())
        except (OSError,ValueError,UnicodeError,RecursionError):
            self.metric_source=None


    def verify_unchanged(self,check=lambda:6.):
        from household_snapshot import _read
        from household.energy_configuration_capture import _owned_text
        check()
        if any(_private_file(path,16384 if name=='token' else 8192)!=self.private[name] for name,path in self.paths.items()):
            raise ValueError('private source configuration changed')
        if any(_owned_text(path,maximum,check)!=original for path,maximum,original in self.policy_bindings):
            raise ValueError('original bank, topology or measured-weather policy changed')
        if self.runtime_reader()!=self.runtime or any(_read(path,262144)!=self.registry[name] for name,path in self.registry_paths.items()):
            raise ValueError('source execution or registry changed')
        check()

    def _owner_http(self,item,*,remaining):
        from household_cycle_deadline import borrow_observation_timer
        with borrow_observation_timer():return self._owner_transport(item,remaining=remaining)

    def _rules_http(self,*,remaining):
        from household_cycle_deadline import borrow_observation_timer
        from household.owner_sources import ENDPOINT,MAX_RAW_BYTES
        with borrow_observation_timer():
            return self._get_original(ENDPOINT,maximum=MAX_RAW_BYTES,remaining=remaining).decode('utf-8')

    def _policy_http(self,*,remaining):
        from household_cycle_deadline import borrow_observation_timer
        from household.owner_policy import RULE_ENDPOINT,STATUS_ENDPOINT
        result=dict(schema='earthship-greywater-policy-source/v1')
        with borrow_observation_timer():
            for name,endpoint,maximum in (('rule_before',RULE_ENDPOINT,65536),('status',STATUS_ENDPOINT,2048),('rule_after',RULE_ENDPOINT,65536)):
                remaining();requested=utc(self.clock())
                raw=self._get_original(endpoint,maximum=maximum,remaining=remaining).decode('utf-8')
                result[name]=dict(endpoint=endpoint,raw=raw,sha256=sha256(raw.encode()).hexdigest(),
                    requested_at=requested.isoformat(),received_at=utc(self.clock()).isoformat())
        return result

    def _measured_http(self,**request):
        from household_cycle_deadline import borrow_observation_timer
        from household.measured_weather_capture import _http_get
        with borrow_observation_timer():return _http_get(**request,opener=self.opener)

    def _owner_transport(self,item,*,remaining):
        from household.capture import RECEIPT_ITEMS
        from household.power_snapshot import SOURCES
        if item not in {DAILY_RECEIPT_ITEM,*RECEIPT_ITEMS.values(),*[row[0] for row in SOURCES.values()]}:
            raise ValueError('fixed owner item required')
        raw=self._get_original('/items/'+item,maximum=8192,remaining=remaining)
        value=loads(raw)
        if not isinstance(value.get('state'),str) or len(value['state'].encode())>4096:
            raise ValueError('bounded original owner state required')
        return value['state']

    def _get_original(self,endpoint,*,maximum,remaining):
        budget=remaining()
        if threading.current_thread() is not threading.main_thread() or signal.getitimer(signal.ITIMER_REAL)!=(0.,0.):
            raise ValueError('exclusive owner transport budget required')
        url=self.base+endpoint
        request=urllib.request.Request(url,method='GET',headers={'Authorization':'Bearer '+self.token})
        previous=signal.getsignal(signal.SIGALRM)
        def expired(*args):raise TimeoutError('owner transport deadline elapsed')
        signal.signal(signal.SIGALRM,expired)
        try:
            signal.setitimer(signal.ITIMER_REAL,min(2.,budget))
            with self.opener.open(request,timeout=min(2.,budget)) as response:
                if response.status!=200 or response.geturl()!=url:raise ValueError('fixed owner response required')
                raw=response.read(maximum+1)
            remaining()
        finally:
            signal.setitimer(signal.ITIMER_REAL,0.);signal.signal(signal.SIGALRM,previous)
        if len(raw)>maximum:raise ValueError('bounded owner response required')
        return raw

    def __call__(self,*,issue,remaining,guard):
        from household.capture import RECEIPT_ITEMS,NATIVE_ROLES,fetch_receipt
        from household.power_capture import collect_power_inputs,fetch_power_receipt
        from household.power_snapshot import SOURCES,POWER_ROLES,compile_power_inputs,replay_power_snapshot
        from household.energy_configuration_capture import collect_configuration
        from household.measured_weather_capture import collect_measured_weather
        from thermal_model.temperature_history import STREAMS,POLICY
        from weather_temperature_sources import fetch_temperature_source
        from weather_temperature_evidence import TemperaturePolicy
        from earthship_energy.bms_evidence import parse_evidence
        from pv_day_evidence import parse_pv_receipt
        from household_snapshot import _read
        started=utc(self.clock());issue=utc(issue)
        def check():
            guard();value=remaining()
            if type(value) not in (int,float) or not math.isfinite(value) or not 0<value<=MAX_OBSERVATION_SECONDS:
                raise ValueError('external issue budget unavailable')
            if utc(self.clock())>=issue:raise ValueError('original sources arrived after issue')
            return value
        check();before={};after={}
        # Daily state is an existing mutable input, not an immutable credential
        # or release artifact. Retain only its exact energy record and match it
        # to the independently read published receipt before using it.
        from household.daily_energy_source import capture_daily_source
        daily_source=None
        try:
            daily_raw=_read(DAILY_STATE_PATH,2097152)
            daily_receipt=self.owner_reader(DAILY_RECEIPT_ITEM,remaining=check)
            daily_source=capture_daily_source(daily_raw,daily_receipt,collected_at=utc(self.clock()))
            if _read(DAILY_STATE_PATH,2097152)!=daily_raw:daily_source=None
        except (OSError,ValueError,KeyError,TypeError):
            daily_source=None
        check()
        parsers={RECEIPT_ITEMS['battery_soc']:parse_evidence,RECEIPT_ITEMS['pv_day_wh']:parse_pv_receipt,
                 **{item:parser for item,parser in SOURCES.values()}}
        def owners(target):
            epochs={}
            for item,parser in parsers.items():
                check();raw=self.owner_reader(item,remaining=check);at=utc(self.clock());record=parser(raw,at)
                if record is None:raise ValueError('original owner binding unavailable')
                current=getattr(record,'stream_epoch',None) or getattr(record,'epoch',None)
                epochs[item]=current
                target[item]=dict(raw=raw,sha256=sha256(raw.encode()).hexdigest(),available_at=at.isoformat())
            return epochs
        expected=owners(before)
        base_epochs={role:expected[item] for role,item in RECEIPT_ITEMS.items()}
        for role,name in NATIVE_ROLES.items():
            stream,model,sensor_id=STREAMS[name]
            if self.policies.get(stream)!=TemperaturePolicy(model,sensor_id,**POLICY):
                raise ValueError('native source policy differs')
            base_epochs[role]=self.phases[stream]
        power_epochs={kind:expected[item] for kind,(item,_) in SOURCES.items()}
        configuration=collect_configuration(clock=self.clock,remaining=check)
        measured=collect_measured_weather(clock=self.clock,remaining=check,source_getter=self._measured_http)
        base_policy=dict(requirements={'battery_display':['battery_soc'],'thermal_forecast':list(NATIVE_ROLES),'pv_day_display':['pv_day_wh']},
            max_age_seconds={role:120 for role in base_epochs},max_skew_seconds=60)
        power_policy=dict(requirements={'current_energy':['battery_soc',*POWER_ROLES],'full_energy':['usable_battery_kwh','physical_bank_epoch','estimated_load_w']},
            max_age_seconds={role:30 if role=='inverter_output_w' else 120 for role in POWER_ROLES},max_skew_seconds=60)
        bundle=collect_power_inputs(base_epochs=base_epochs,base_policy=base_policy,power_epochs=power_epochs,power_policy=power_policy,
            receipt_reader=lambda role,start,end,inner:fetch_receipt(lambda:self.energy(remaining=lambda:min(check(),inner())),role=role,start=start,end=end,remaining=lambda:min(check(),inner())),
            native_reader=lambda **request:fetch_temperature_source(lambda:self.native(remaining=lambda:min(check(),request['remaining_timeout']())),**{**request,'remaining_timeout':lambda:min(check(),request['remaining_timeout']())}),
            power_reader=lambda kind,start,end,inner:fetch_power_receipt(self.energy,kind=kind,start=start,end=end,remaining=lambda:min(check(),inner())),clock=self.clock)
        if owners(after)!=expected:raise ValueError('original owner epoch changed')
        self.verify_unchanged(check)
        receipt=compile_power_inputs(bundle,managed=loads(self.registry['managed']),ownership=loads(self.registry['ownership']),
            code_revision=self.code_revision,runtime_manifest=self.runtime)
        if replay_power_snapshot(receipt,runtime_manifest=self.runtime)!=receipt:raise ValueError('original source replay differs')
        from household.owner_sources import ENDPOINT,coordination_from_rules
        from household.capabilities import CapabilityRegistry
        owner_source=None
        check()
        requested=utc(self.clock())
        try:
            raw=self.rule_reader(remaining=check)
            received=utc(self.clock())
            owner_source=dict(schema='earthship-household-owner-source/v1',endpoint=ENDPOINT,raw=raw,
                sha256=sha256(raw.encode()).hexdigest(),requested_at=requested.isoformat(),received_at=received.isoformat())
            registry=CapabilityRegistry(canonical({key:value for key,value in receipt['registry'].items() if key!='registry_id'}))
            coordination_from_rules(owner_source,snapshot_id=receipt['snapshot']['snapshot_id'],registry=registry,horizon_hours=24,as_of=received)
        except (OSError,ValueError,KeyError,TypeError,UnicodeError,RecursionError,HTTPException):
            owner_source=None
        check()
        from household.owner_policy import observe_policy
        policy_source=None
        try:
            policy_source=self.policy_reader(remaining=check)
            registry=CapabilityRegistry(canonical({key:value for key,value in receipt['registry'].items() if key!='registry_id'}))
            observe_policy(policy_source,registry=registry,as_of=utc(self.clock()))
        except (OSError,ValueError,KeyError,TypeError,UnicodeError,RecursionError,HTTPException):
            policy_source=None
        check()
        self.verify_unchanged(check);finished=utc(self.clock())
        if not started<=finished<issue:raise ValueError('source collection clock changed')
        result=dict(schema='earthship-household-cycle-sources/v6',issue=issue.isoformat(),captured_at=finished.isoformat(),
            power_receipt=receipt,energy_configuration=configuration.to_dict(),measured_weather=measured.to_dict(),daily_energy_source=daily_source,owner_source=owner_source,policy_source=policy_source,energy_persistence_source=self.metric_source,load_topology_source=self.load_topology_source,
            owner_bindings=dict(before=before,after=after),automatic_actuation=False)
        if len(canonical(result))>1048576:raise ValueError('bounded cycle source originals required')
        check();return result
