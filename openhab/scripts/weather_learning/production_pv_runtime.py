"""Exact selected component-PV owner shared by daily and storage consumers."""
from pathlib import Path
from datetime import datetime,timedelta,time,timezone
from zoneinfo import ZoneInfo
from hashlib import sha256
import json
from weather_source_files import _read
from .contracts import canonical,identity,digest,instant
from .evidence import utc
from .production_model_admission import _authorization
from .production_pv import load_calibration,project_calibrated,source_manifest,MAX_BYTES
from household_pv_components import project_window_components

ROOT=Path(__file__).resolve().parents[3]
FIELDS={'schema','model_path','model_file_sha256','calibration_sha256','measurement_cohort_sha256','system_path','horizon_path','power_policy_path','runtime_sha256','authorization_policy_sha256','parallel_shadow_required','automatic_actuation'}

def runtime_manifest():
    return source_manifest()|{n:sha256(_read(ROOT/n,262144,source=True)).hexdigest() for n in (
        'openhab/scripts/weather_learning/production_pv_runtime.py','openhab/scripts/daily_pv_worker.py',
        'openhab/scripts/household_component_energy.py','openhab/scripts/component_household_files.py','openhab/scripts/household_profiled_storage.py',
        'openhab/scripts/household_ac_load_model.py','openhab/scripts/weather_learning/component_household_inputs.py',
        'openhab/scripts/weather_learning/retained_scenario_child.py','openhab/scripts/weather_learning/retained_scenarios.py')}

def _path(value):
    if not isinstance(value,str) or len(value)>1024:raise ValueError('explicit original component owner path required')
    path=Path(value)
    if not path.is_absolute() or path.resolve()!=path:raise ValueError('resolved component owner path required')
    return path

class ComponentOwner:
    def __init__(self,path,*,expected_sha256,clock=lambda:datetime.now(timezone.utc),guard=lambda:None):
        digest(expected_sha256);self.path=_path(str(path));self.raw=_read(self.path,32768);self.clock=clock;self.guard=guard;self.profile=json.loads(self.raw);p=self.profile
        if (sha256(self.raw).hexdigest()!=expected_sha256 or not isinstance(p,dict) or set(p)!=FIELDS or p['schema']!='earthship-component-pv-production-profile/v1' or
            p['parallel_shadow_required'] is not False or p['automatic_actuation'] is not False or p['runtime_sha256']!=identity(runtime_manifest())):
            raise ValueError('exact reviewed component production profile required')
        authorization=json.loads(_read(ROOT/'docs/operations/weathernext3-capabilities/deployment-policy.json',65536,source=True));_authorization(authorization,p['authorization_policy_sha256'])
        self.model_path=_path(p['model_path']);self.model_raw=_read(self.model_path,MAX_BYTES);body=json.loads(self.model_raw)
        if sha256(self.model_raw).hexdigest()!=p['model_file_sha256'] or body['calibration_sha256']!=p['calibration_sha256'] or body['authorization_policy_sha256']!=p['authorization_policy_sha256']:
            raise ValueError('unchanged explicitly selected component fit required')
        self.model=load_calibration(body,at=instant(body['ready_at']));self.body=self.model.to_dict();self.context=self.body['context'];self._used=False;self._origin=None
        self.configurations={}
        for field,pin,limit in (('system_path','system_sha256',16384),('horizon_path','horizon_sha256',16384),('power_policy_path','power_policy_sha256',65536)):
            path=_path(p[field]);raw=_read(path,limit,source=True)
            if sha256(raw).hexdigest()!=self.context[pin]:raise ValueError('selected component physical context differs from training')
            self.configurations[field]=(path,raw,limit)
        if p['measurement_cohort_sha256']!=self.context['measurement_cohort_sha256']:raise ValueError('original measured-power cohort required')
        self.verify()

    def verify(self):
        self.guard()
        if self._origin is not None and not self._origin<=utc(self.clock())<=self._origin+timedelta(seconds=85):raise ValueError('component production origin expired')
        if _read(self.path,32768)!=self.raw or _read(self.model_path,MAX_BYTES)!=self.model_raw or self.profile['runtime_sha256']!=identity(runtime_manifest()):
            raise ValueError('component production owner source/profile/model changed')
        for path,raw,limit in self.configurations.values():
            if _read(path,limit,source=True)!=raw:raise ValueError('component physical configuration changed')
        load_calibration(self.model,at=instant(self.body['ready_at']))
        if self._used and utc(self.clock())>=instant(self.body['expires_at']):raise ValueError('component fit expired before publication')
        return True

    def authorize(self,body):
        self.verify();return body==self.body

    def project(self,*,forecast,positions,start,end):
        origin=instant(forecast['origin'])
        if self._origin is not None and self._origin!=origin:raise ValueError('one original component publication opportunity required')
        self._origin=origin;self.verify();now=utc(self.clock())
        if not origin<=now<=origin+timedelta(seconds=85):raise ValueError('current bounded component production origin required')
        system=self.configurations['system_path'][1];horizon=self.configurations['horizon_path'][1]
        ready,expiry=map(instant,(self.body['ready_at'],self.body['expires_at']));reason=None
        if origin<ready:reason='registered_model_not_yet_available'
        elif origin>=expiry:reason='registered_model_expired'
        elif forecast['site']['timezone']!=self.context['timezone'] or forecast['rows'][0]['solar']['grid_sha256']!=self.context['solar_grid_sha256']:
            reason='registered_solar_grid_unavailable'
        if reason is None:
            prepared=project_calibrated(self.model,forecast=forecast,positions=positions,system_raw=system,horizon_raw=horizon,
                measurement_cohort_sha256=self.profile['measurement_cohort_sha256'],power_policy_sha256=self.context['power_policy_sha256'],
                start=start,end=end,authorize=self.authorize)
            raw=prepared['raw_projection'];projection=prepared['calibrated_projection'];self._used|=projection['calibrated_segments']>0
        else:
            from .native_forecast import validate_native_forecast
            from .native_solar_forecast import SCHEMA
            forecast=validate_native_forecast(forecast)
            if forecast['schema']!=SCHEMA:raise ValueError('actual native component source required for raw fallback')
            raw=project_window_components(array=json.loads(system)['array'],forecast=forecast,positions=positions,start=start,end=end,
                timezone_name=forecast['site']['timezone'],horizon_profile=json.loads(horizon)['profile'])
            projection=dict(raw);projection.pop('projection_sha256')
            projection.update(calibration_scope='none',calibrated_segments=0,raw_fallback_segments=len(raw['segments']))
            projection['projection_sha256']=identity(projection)
        self.verify()
        value=dict(schema='earthship-owned-production-component-window/v1',mode='selected_native_gain' if reason is None else 'native_components_raw_fallback',reason=reason,
            calibration_sha256=self.body['calibration_sha256'],raw_projection=raw,projection=projection,issued=False,physical_calibration_qualified=False,automatic_actuation=False)
        value['window_sha256']=identity(value);return value

    def project_days(self,*,dates,forecast,positions):
        if not isinstance(dates,list) or not 1<=len(dates)<=10 or dates!=sorted(set(dates)):raise ValueError('bounded ordered component PV dates required')
        origin=instant(forecast['origin']);zone=ZoneInfo(forecast['site']['timezone']);days=[];originals=[]
        for text in dates:
            day=datetime.fromisoformat(text).date();begin=datetime.combine(day,time.min,zone).astimezone(timezone.utc);end=datetime.combine(day+timedelta(days=1),time.min,zone).astimezone(timezone.utc)
            if day<origin.astimezone(zone).date():raise ValueError('current or future local PV day required')
            start=max(origin,begin)
            row=dict(date=text,status='unavailable',reason='incomplete_weather_or_geometry',potentialKwh=None,uncalibratedPotentialKwh=None,
                fromAt=start.isoformat(),throughAt=end.isoformat(),scope='remaining' if start>begin else 'full_day',calibrationScope='none',
                sourceSupport=None,projectionSha256=None)
            try:
                # Missing numerical coverage affects this day. Owner refusal
                # and resource/clock changes are checked again outside scope.
                original=self.project(forecast=forecast,positions=positions,start=start,end=end);originals.append(original);p=original['projection']
                row.update(status='available',reason=original['reason'],potentialKwh=p['potential_pv_kwh'],uncalibratedPotentialKwh=original['raw_projection']['potential_pv_kwh'],
                    calibrationScope=p['calibration_scope'],sourceSupport=p['source_support'],projectionSha256=original['window_sha256'])
            except (KeyError,TypeError,ValueError):
                self.verify()
            days.append(row)
        self.verify();return days,originals

    def daily_view(self,*,days,forecast,geometry_sha256):
        self.verify();digest(geometry_sha256);origin=instant(forecast['origin']);body=self.body;m=body['model'];support=m['support']
        applied=any(d['status']=='available' and d['calibrationScope'] in ('native_components_only','mixed_native_and_raw_fallback') for d in days)
        until=min(origin+timedelta(minutes=90),instant(forecast['issued_at'])+timedelta(hours=24))
        if until<=origin:raise ValueError('current native component source required')
        calibration=dict(modelSha256=m['model_sha256'],calibrationSha256=body['calibration_sha256'],procedureSha256=body['procedure_sha256'],policySha256=body['policy_sha256'],
            trainedAt=body['ready_at'],trainingThrough=body['cutoff'],validUntil=body['expires_at'],targets=support['unique_measured_targets'],localTargetDates=support['local_target_dates'],
            baselineRule=body['baseline_rule'],mode='experimental_production' if applied else 'raw_component_fallback',physicalCalibrationQualified=False)
        value=dict(schema='earthship-daily-pv-potential/v4',provider='weathernext3',generatedAt=origin.isoformat(),validUntil=until.isoformat(),
            timezone=forecast['site']['timezone'],weatherSha256=forecast['forecast_sha256'],geometrySha256=geometry_sha256,
            systemSha256=self.context['system_sha256'],horizonSha256=self.context['horizon_sha256'],confidence='experimental_native_component_model',
            calibration=calibration,days=days,automatic_actuation=False,physical_calibration_qualified=False)
        if len(canonical(value))>32768:raise ValueError('bounded daily component view required')
        return value
