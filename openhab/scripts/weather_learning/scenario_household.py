"""Replay household targets from original local sources; forecasts stay conditional."""
from dataclasses import dataclass
from datetime import timedelta
from math import fsum
import json
from .contracts import canonical,identity,instant,finite

FIELDS={'schema','request','sources','targets','target_sha256'}
REQUEST={'start','end','assessed_at','source_epoch','sensor_epochs','bank_config_raw','bank_epoch','nominal_bank_kwh','initial_soc_pct'}
NAMES=('potential_array_proxy_kwh','captured_controller_dc_kwh','minimum_hour_grid_soc_pct','indoor_air_f','north_wall_f')


def _target(value,reason,basis,**extra):
    return dict(value=value,status='observed' if value is not None else 'unavailable',reason=reason,basis=basis,physical_calibration_qualified=False,**extra)


def _build(request,sources):
    from household.evidence import epoch
    from household.energy_outcome_sources import _bank
    if (not isinstance(request,dict) or set(request)!=REQUEST or not isinstance(sources,dict) or set(sources)!={'energy','battery','temperature'} or len(canonical(sources))>16*1024**2):raise ValueError('closed bounded original household target context required')
    start,end,assessed=map(instant,(request['start'],request['end'],request['assessed_at']));hours=(end-start).total_seconds()/3600
    if not 1<=hours<=24 or hours!=int(hours) or assessed<end+timedelta(minutes=5):raise ValueError('mature complete elapsed-hour household horizon required')
    epoch(request['source_epoch'])
    if not finite(request['nominal_bank_kwh']) or not .001<=request['nominal_bank_kwh']<=10000 or not finite(request['initial_soc_pct']) or not 0<=request['initial_soc_pct']<=100:raise ValueError('original nominal storage assumptions required')
    if not isinstance(request['sensor_epochs'],dict) or set(request['sensor_epochs'])!={'air','mass'}:raise ValueError('explicit household sensor phase map required')
    bank_start=None
    if request['bank_config_raw'] is not None:
        bank_start,bank_end=_bank(request['bank_config_raw'],request['bank_epoch']);bank=json.loads(request['bank_config_raw']);row=next(b for b in bank['epochs'] if b['id']==request['bank_epoch'])
        if bank_start>start or bank_end is not None and bank_end<end or row.get('nominal_usable_kwh')!=request['nominal_bank_kwh']:raise ValueError('original model capacity or physical bank interval differs')
    targets=_energy(sources['energy'],start,end,assessed,bank_start)
    targets['minimum_hour_grid_soc_pct']=_battery(sources['battery'],request,start,end,assessed,bank_start)
    temperatures=_temperatures(sources['temperature'],request,end,assessed)
    targets.update(temperatures)
    result=dict(schema='earthship-original-scenario-household-targets/v1',request=request,sources=sources,targets=targets)
    result['target_sha256']=identity(result);return result


def _energy(sources,start,end,assessed,bank_start):
    from .energy_history import validate_source,summarize_hour
    from earthship_energy.power_evidence import build_power_intervals,PowerSequenceError
    from household_pv_window import policy_cutover
    if not isinstance(sources,list) or len(sources)>25:raise ValueError('bounded original household energy hours required')
    bins={};policy=None
    for source in sources:
        source=validate_source(source)
        if (instant(source['received_at'])>assessed or not instant(source['start'])<end or not start<instant(source['end'])):raise ValueError('matching actually available energy hour required')
        if bank_start is not None and instant(source['bank_start'])!=bank_start:raise ValueError('original energy bank boundary differs')
        if policy is not None and policy!=source['policy_raw']:raise ValueError('mixed original power policies refused')
        policy=source['policy_raw'];native={}
        for field in ('pv.input_power_w','pv.output_power_w'):
            try:native[field]=build_power_intervals([(instant(at),raw) for at,raw in source['rows']['power']],field,instant(source['start']),instant(source['end']),cutover=policy_cutover(policy))
            except (ValueError,PowerSequenceError):native[field]=[]
        for row in summarize_hour(source):
            left,right=max(start,instant(row['start'])),min(end,instant(row['end']))
            if left>=right:continue
            if row['start'] in bins:raise ValueError('duplicate original energy intervals refused')
            # Keep the original complete-bin censoring policy. Integrate native
            # qualified power intervals over the exact overlap, never prorate a
            # five-minute energy total or round a fractional forecast origin.
            fields={}
            for field,values in native.items():
                pieces=[(max(0.,(min(v.end,right)-max(v.start,left)).total_seconds()),v.watts) for v in values if v.start<right and left<v.end]
                fields[field]=dict(covered_seconds=fsum(t for t,w in pieces),positive_kwh=fsum(t*max(0,w) for t,w in pieces)/3600000)
            bins[row['start']]=dict(start=left,end=right,fields=fields,potential_proxy_eligible=row['potential_proxy_eligible'])
    cursor=start;full=True
    for row in sorted(bins.values(),key=lambda r:r['start']):
        full=full and row['start']==cursor;cursor=row['end']
    full=full and cursor==end;captured=potential=0.;capture_ok=potential_ok=full
    for row in bins.values():
        output=row['fields']['pv.output_power_w'];input_=row['fields']['pv.input_power_w'];seconds=(row['end']-row['start']).total_seconds()
        capture_ok=capture_ok and output['covered_seconds']>=seconds-1e-6
        potential_ok=potential_ok and row['potential_proxy_eligible'] and input_['covered_seconds']>=seconds-1e-6
        captured+=output['positive_kwh'];potential+=input_['positive_kwh']
    return dict(potential_array_proxy_kwh=_target(potential if potential_ok else None,None if potential_ok else 'complete_uncensored_potential_proxy_window_required','qualified_input_power_low_SOC_charging_proxy; not calibrated array potential'),captured_controller_dc_kwh=_target(captured if capture_ok else None,None if capture_ok else 'complete_qualified_controller_output_window_required','known_controller_DC_output_over_exact_elapsed_window'))


def _battery(sources,request,start,end,assessed,bank_start):
    from household.battery_outcomes import endpoint_value
    if not isinstance(sources,dict):raise ValueError('original hour-grid battery endpoint map required')
    targets=[start+timedelta(hours=i) for i in range(int((end-start).total_seconds()/3600)+1)]
    if not set(sources)<={t.isoformat() for t in targets}:raise ValueError('battery endpoints outside exact original forecast grid')
    reason=None;values=[]
    for at in targets:
        value,missing=endpoint_value(sources.get(at.isoformat()),target=at,assessed=assessed,source_epoch=request['source_epoch'])
        if value is None:reason=reason or missing
        values.append(value)
    if bank_start is None:reason=reason or 'independent_original_bank_binding_required'
    if values[0] is not None and abs(values[0]-request['initial_soc_pct'])>1e-9:reason=reason or 'original_model_SOC_origin_differs'
    return _target(min(values) if reason is None else None,reason,'origin_and_elapsed_hour_endpoints; not continuous trough',grid_targets=len(targets),qualified_endpoints=sum(v is not None for v in values))


def _temperatures(sources,request,end,assessed):
    from thermal_model.temperature_history import STREAMS,POLICY,_validate_sensor_receipt
    from weather_temperature_sources import replay_temperature_source
    from weather_temperature_evidence import sensor_epoch_id
    if not isinstance(sources,dict) or not set(sources)<={'air','mass'}:raise ValueError('closed original household temperature endpoint map required')
    output={}
    for role,name in [('air','indoor_air_f'),('mass','north_wall_f')]:
        packet=sources.get(role);value=None;reason='qualified_original_temperature_endpoint_required'
        if packet is not None:
            stream,model,sensor_id=STREAMS[role];phase=sensor_epoch_id(request['sensor_epochs'][role])
            if (packet['stream']!=stream or packet['policy']!=dict(model=model,sensor_id=sensor_id,**POLICY) or packet['sensor_epoch']!=phase or packet['targets']!=[end.isoformat()] or not end<=instant(packet['assessed_at'])<=assessed):raise ValueError('original temperature endpoint role/target/policy/phase differs')
            rows=replay_temperature_source(packet);receipt=rows[0][1]
            if receipt is not None:
                _validate_sensor_receipt(receipt,end,sensor_epoch=phase);value=float(receipt['temperatureF']);reason=None
        output[name]=_target(value,reason,'qualified_native_temperature_endpoint_F')
    return output


@dataclass(frozen=True)
class HouseholdTargets:
    content:bytes
    def __post_init__(self):
        if not isinstance(self.content,bytes) or len(self.content)>16*1024**2:raise ValueError('bounded original household targets required')
        value=json.loads(self.content)
        if (not isinstance(value,dict) or set(value)!=FIELDS or canonical(_build(value['request'],value['sources']))!=canonical(value)):raise ValueError('household targets differ from original source replay')
    def to_dict(self):return json.loads(self.content)


def household_targets(*,start,end,assessed_at,energy_sources,battery_endpoint_sources,temperature_sources,source_epoch,sensor_epochs,bank_config_raw,bank_epoch,nominal_bank_kwh,initial_soc_pct):
    request=dict(start=start.isoformat(),end=end.isoformat(),assessed_at=assessed_at.isoformat(),source_epoch=source_epoch,sensor_epochs=sensor_epochs,bank_config_raw=bank_config_raw,bank_epoch=bank_epoch,nominal_bank_kwh=nominal_bank_kwh,initial_soc_pct=initial_soc_pct)
    sources=dict(energy=energy_sources,battery=battery_endpoint_sources,temperature=temperature_sources)
    return HouseholdTargets(canonical(_build(request,sources)))


def score_household(projections,*,targets):
    if type(targets) is not HouseholdTargets or not isinstance(projections,list) or not 1<=len(projections)<=9:raise ValueError('bounded original household scenario/target batch required')
    target=HouseholdTargets(targets.content).to_dict();request=target['request'];rows=[];pins=set();bindings=set()
    for projection in projections:
        if projection.get('projection_sha256')!=identity({k:v for k,v in projection.items() if k!='projection_sha256'}) or projection.get('schema')!='earthship-conditional-weather-scenario-projection/v1':raise ValueError('original retained scenario projection required')
        pv=projection['pv'];storage=projection['nominal_storage']
        if (pv['origin']!=request['start'] or pv['through']!=request['end'] or storage['initial_soc_pct']!=request['initial_soc_pct'] or storage['nominal_bank_kwh']!=request['nominal_bank_kwh'] or projection['scenario_sha256'] in pins):raise ValueError('scenario window, storage assumptions or original identity differs')
        pins.add(projection['scenario_sha256']);bindings.add(projection['inputs_sha256'])
        predicted=dict(potential_array_proxy_kwh=pv['potential_pv_kwh'],captured_controller_dc_kwh=storage['modeled_captured_pv_kwh'],minimum_hour_grid_soc_pct=projection['minimum_nominal_soc_pct'],indoor_air_f=projection['thermal']['indoor_air_f'],north_wall_f=projection['thermal']['north_wall_f'])
        actual={name:target['targets'][name]['value'] for name in NAMES};errors={name:None if actual[name] is None or predicted[name] is None else predicted[name]-actual[name] for name in NAMES}
        rows.append(dict(scenario_sha256=projection['scenario_sha256'],recipe=projection['recipe'],predictions=predicted,actual=actual,errors=errors,absolute_errors={k:None if v is None else abs(v) for k,v in errors.items()}))
    if len(bindings)!=1:raise ValueError('weather-only scenarios must share original household/model assumptions')
    result=dict(schema='earthship-conditional-scenario-household-scores/v1',target_sha256=target['target_sha256'],window_start=request['start'],window_end=request['end'],window_semantics='rolling_elapsed_hours; not a local-calendar daily total or continuous trough',support=dict(forecast_origins=1,local_dates=1,scenarios=len(rows)),scenarios=rows,targets=target['targets'],evaluation_scope='conditional modeled trajectories versus later qualified measurements under actual behavior',causal_benefit_qualified=False,physical_calibration_qualified=False,as_issued_score=False,disposition='insufficient_evidence',probability_claim=False,automatic_actuation=False)
    result['score_sha256']=identity(result);return result
