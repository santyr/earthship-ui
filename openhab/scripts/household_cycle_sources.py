"""Private configuration and restricted originals for the household cycle."""
from pathlib import Path
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
    def __init__(self,*,token_file,openhab_base,code_revision,clock=lambda:datetime.now(timezone.utc),owner_reader=None):
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

    def _measured_http(self,**request):
        from household_cycle_deadline import borrow_observation_timer
        from household.measured_weather_capture import _http_get
        with borrow_observation_timer():return _http_get(**request,opener=self.opener)

    def _owner_transport(self,item,*,remaining):
        from household.capture import RECEIPT_ITEMS
        from household.power_snapshot import SOURCES
        if item not in {*RECEIPT_ITEMS.values(),*[row[0] for row in SOURCES.values()]}:
            raise ValueError('fixed owner item required')
        budget=remaining()
        if threading.current_thread() is not threading.main_thread() or signal.getitimer(signal.ITIMER_REAL)!=(0.,0.):
            raise ValueError('exclusive owner transport budget required')
        url=self.base+'/items/'+item
        request=urllib.request.Request(url,method='GET',headers={'Authorization':'Bearer '+self.token})
        previous=signal.getsignal(signal.SIGALRM)
        def expired(*args):raise TimeoutError('owner transport deadline elapsed')
        signal.signal(signal.SIGALRM,expired)
        try:
            signal.setitimer(signal.ITIMER_REAL,min(2.,budget))
            with self.opener.open(request,timeout=min(2.,budget)) as response:
                if response.status!=200 or response.geturl()!=url:raise ValueError('fixed owner response required')
                raw=response.read(8193)
            remaining()
        finally:
            signal.setitimer(signal.ITIMER_REAL,0.);signal.signal(signal.SIGALRM,previous)
        if len(raw)>8192:raise ValueError('bounded owner response required')
        value=loads(raw)
        if not isinstance(value.get('state'),str) or len(value['state'].encode())>4096:
            raise ValueError('bounded original owner state required')
        return value['state']

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
        self.verify_unchanged(check);finished=utc(self.clock())
        if not started<=finished<issue:raise ValueError('source collection clock changed')
        result=dict(schema='earthship-household-cycle-sources/v1',issue=issue.isoformat(),captured_at=finished.isoformat(),
            power_receipt=receipt,energy_configuration=configuration.to_dict(),measured_weather=measured.to_dict(),
            owner_bindings=dict(before=before,after=after),automatic_actuation=False)
        if len(canonical(result))>1048576:raise ValueError('bounded cycle source originals required')
        check();return result
