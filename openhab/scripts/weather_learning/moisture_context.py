"""Read-only forecast moisture comparison using existing qualified observations."""
from datetime import timedelta
from .contracts import identity,instant,finite
from .evidence import utc
from .atmospheric_context import vapor_pressure_hpa
from household.sensor_observations import PreparedSensorObservations,prepare_sensor_observations
from household.codec import loads



def current_sensor_context(indoor,decision):
    if type(indoor) is not PreparedSensorObservations:raise ValueError('replayed qualified sensor context required')
    original=indoor.to_dict();decision=utc(decision)
    if instant(original['as_of'])>decision:raise ValueError('indoor collection unavailable at assessment')
    return prepare_sensor_observations(registry_raw=original['registry_raw'],registry_sha256=original['registry_sha256'],
        sources=original['sources'],as_of=decision,collector_raw=original['collector_raw'],collector_sha256=original['collector_sha256'])

def build_moisture_context(*,outdoor,indoor=None,zone=None,decision):
    decision=utc(decision)
    if indoor is not None and type(indoor) is not PreparedSensorObservations:raise ValueError('replayed qualified sensor context required')
    if (not isinstance(outdoor,dict) or outdoor.get('schema')!='earthship-atmospheric-context/v1' or
            outdoor.get('context_sha256')!=identity({k:v for k,v in outdoor.items() if k!='context_sha256'}) or
            outdoor.get('automatic_actuation') is not False or instant(outdoor['assessed_at'])>decision):
        raise ValueError('original read-only atmospheric context required')
    dew=outdoor['dewpoint'];vapor=None
    if (dew is not None and finite(dew['value']) and instant(dew['available_at'])<=decision<instant(dew['initialized_at'])+timedelta(hours=24)):
        vapor=vapor_pressure_hpa(dew['value'])
    result=dict(schema='earthship-forecast-moisture-context/v1',assessed_at=decision.isoformat(),outdoor_target_at=outdoor['valid_at'],
        mode='outdoor_only',outdoor_vapor_pressure_hpa=vapor,indoor_vapor_pressure_hpa=None,indoor_temperature_c=None,
        indoor_relative_humidity_pct=None,comparison=None,valid_until=None,indoor_evidence_sha256s=[],indoor_context_sha256=None,
        missing_dependencies=['qualified_indoor_temperature_and_relative_humidity'],
        scope='forecast_outdoor_vapor_pressure_vs_current_indoor_at_comparable_local_total_pressure',
        condensation_assessed=False,automatic_actuation=False,release_authorized=False)
    def finish():result['context_sha256']=identity(result);return result
    if indoor is None or not isinstance(zone,str) or not 1<=len(zone)<=128:return finish()
    prepared=current_sensor_context(indoor,decision).to_dict()
    choices={kind:[] for kind in ('air_temperature','relative_humidity')}
    for key,row in prepared['observations'].items():
        kind=key.rsplit(':',1)[-1]
        if kind in choices and row['zone']==zone and row['value'] is not None and row['reason'] is None:
            observed=instant(row['evidence']['observed_at'] or row['evidence']['received_at'])
            if decision-observed<=timedelta(seconds=120):choices[kind].append((key,row))
    if any(len(rows)!=1 for rows in choices.values()):return finish()
    temp_key,temp=choices['air_temperature'][0];rh_key,rh=choices['relative_humidity'][0]
    a,b=temp['evidence'],rh['evidence']
    if temp['unit']!='degC' or rh['unit']!='percent' or abs((instant(a['observed_at'] or a['received_at'])-instant(b['observed_at'] or b['received_at'])).total_seconds())>120:
        result['missing_dependencies']=['compatible_same_zone_indoor_temperature_and_humidity'];return finish()
    if not -100<=temp['value']<=70:
        result['missing_dependencies']=['indoor_temperature_outside_diagnostic_domain'];return finish()
    if vapor is None:
        result['missing_dependencies']=['forecast_dewpoint'];return finish()
    if not decision<instant(outdoor['valid_at'])<=decision+timedelta(hours=2):
        result['missing_dependencies']=['outdoor_target_within_two_hours'];return finish()
    indoor_vapor=vapor_pressure_hpa(temp['value'])*rh['value']/100;difference=vapor-indoor_vapor
    until=min(instant(a['valid_until']),instant(b['valid_until']),instant(dew['initialized_at'])+timedelta(hours=24),
        min(instant(e['observed_at'] or e['received_at']) for e in (a,b))+timedelta(seconds=120))
    points=[loads(prepared['sources'][key]['raw']) for key in (temp_key,rh_key)]
    if any(p['transport']=='lorawan' for p in points):
        until=min(until,instant(loads(prepared['collector_raw'])['expires_at']))
    result.update(mode='qualified_comparison',indoor_vapor_pressure_hpa=indoor_vapor,indoor_temperature_c=temp['value'],
        indoor_relative_humidity_pct=rh['value'],comparison='forecast_air_drier' if difference<-.5 else 'forecast_air_wetter' if difference>.5 else 'similar_vapor_pressure',
        valid_until=until.isoformat(),indoor_evidence_sha256s=sorted([identity(a),identity(b)]),indoor_context_sha256=identity(prepared),missing_dependencies=[])
    return finish()
