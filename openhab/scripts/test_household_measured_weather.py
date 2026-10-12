"""Original receiver points retain proxy/counter meaning and source clocks."""
import importlib,json
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
import pytest
from household.codec import canonical,identity
from test_household_energy_configuration import AT


def api():return importlib.import_module('household.measured_weather')


def sources(at=AT):
    from weather_radiation_evidence import RadiationPolicy
    from weather_radiation_receiver import RadiationCollector
    from weather_rain_evidence import RainPolicy
    from weather_rain_receiver import RainCollector
    received=at-timedelta(seconds=2)
    rad=RadiationCollector(RadiationPolicy(32073),clock=lambda:received,monotonic=lambda:1.,process_id=lambda:123)
    rad.epoch='00000000-0000-0000-0000-000000000005'
    rad.observe({'model':'Fineoffset-WH65B','id':32073,'light_lux':12670,'solarradiation':100,
                 'radio_decode_utc':(at-timedelta(seconds=3)).strftime('%Y-%m-%d %H:%M:%S')})
    rain=RainCollector(RainPolicy(32073),clock=lambda:received,monotonic=lambda:1.,process_id=lambda:123)
    rain.epoch='00000000-0000-0000-0000-000000000006'
    rain.observe({'model':'Fineoffset-WH65B','id':32073,'totalrainin':12.3})
    rows={}
    for kind,record in [('radiation',rad.snapshot()),('rain',rain.snapshot())]:
        raw=json.dumps(record);policy={'version':1,'sensor_id':32073,'validity_seconds':120}
        if kind=='rain':policy['maximum_counter_in']=100000.
        policy_raw=json.dumps(policy)
        rows[kind]=dict(source_identity='Weather_Radiation_Evidence_JSON' if kind=='radiation' else 'Weather_Rain_Evidence_JSON',
            source_endpoint='http://127.0.0.1:5000/'+('radiation_evidence' if kind=='radiation' else 'rain_evidence'),
            raw=raw,sha256=sha256(raw.encode()).hexdigest(),available_at=(at-timedelta(seconds=1)).isoformat(),
            expected_epoch=record['streamEpoch'],policy_raw=policy_raw,policy_sha256=sha256(policy_raw.encode()).hexdigest(),
            policy_available_at=(at-timedelta(seconds=1)).isoformat())
    return rows


def prepare(rows=None):return api().prepare_measured_weather(sources=sources() if rows is None else rows,as_of=AT,created_at=AT+timedelta(seconds=1))


def set_raw(row,raw):
    row['raw']=raw;row['sha256']=None if raw is None else sha256(raw.encode()).hexdigest()


def test_original_points_and_policy_bytes_are_retained_without_calibration():
    original=sources();context=prepare(original);out=api().project_measured_weather(context);rows=out['observations']
    assert context.to_dict()['sources']==original
    assert rows['light_lux']['value']==12670 and rows['light_lux']['unit']=='lux'
    assert rows['solar_radiation_proxy_wm2']['value']==100 and rows['solar_radiation_proxy_wm2']['basis']=='lux_proxy_126_7'
    assert rows['rain_counter_in']['value']==12.3 and rows['rain_counter_in']['basis']=='original_cumulative_counter'
    assert out['calibrated_irradiance_qualified'] is False and out['rain_rate_qualified'] is False
    assert out['automatic_actuation'] is False and out['physical_action_effects_qualified'] is False
    assert 'solar_radiation_wm2' not in rows and 'rain_rate' not in rows
    for role,kind in [('light_lux','radiation'),('solar_radiation_proxy_wm2','radiation'),('rain_counter_in','rain')]:
        ref=rows[role]['evidence'];native=json.loads(original[kind]['raw'])['record']
        assert ref['quality']=='qualified' and ref['observed_at'] is None
        assert ref['received_at']==native['receivedAt'] and ref['valid_until']==native['validUntil']
        assert ref['available_at']==original[kind]['available_at'] and ref['source_epoch']==original[kind]['expected_epoch']
        assert ref['hardware_epoch'] is None
        assert original[kind]['sha256'] in ref['parent_digests'] and original[kind]['policy_sha256'] in ref['parent_digests']
    assert rows['light_lux']['evidence']['digest']!=rows['solar_radiation_proxy_wm2']['evidence']['digest']


@pytest.mark.parametrize('damage',['missing_source','malformed','wrong_epoch','missing_policy','conversion','legacy','invalid_barrier'])
def test_radiation_failure_preserves_valid_rain(damage):
    original=sources();row=original['radiation'];raw=json.loads(row['raw'])
    if damage=='missing_source':set_raw(row,None)
    elif damage=='malformed':set_raw(row,'broken JSON')
    elif damage=='wrong_epoch':row['expected_epoch']='00000000-0000-0000-0000-000000000007'
    elif damage=='missing_policy':row.update(policy_raw=None,policy_sha256=None)
    else:
        if damage=='conversion':raw['record']['irradianceWm2']+=1
        elif damage=='legacy':raw['version']=1;raw.pop('faultCount')
        else:
            raw['faultCount']=1;raw['record'].update(status='invalid',reason='expired',receivedAt=None,validUntil=None,lightLux=None,irradianceWm2=None)
        set_raw(row,json.dumps(raw))
    out=api().project_measured_weather(prepare(original));rows=out['observations']
    assert rows['light_lux']['value'] is None and rows['solar_radiation_proxy_wm2']['value'] is None
    assert rows['rain_counter_in']['value']==12.3 and rows['rain_counter_in']['evidence']['quality']=='qualified'
    assert prepare(original).to_dict()['sources']['radiation']['raw']==row['raw']


@pytest.mark.parametrize('damage',['missing_source','malformed','counter','policy'])
def test_rain_failure_preserves_valid_radiation(damage):
    original=sources();row=original['rain']
    if damage=='missing_source':set_raw(row,None)
    elif damage=='malformed':set_raw(row,'not JSON')
    elif damage=='counter':
        raw=json.loads(row['raw']);raw['record']['totalRainIn']=-1;set_raw(row,json.dumps(raw))
    else:
        row['policy_raw']='invalid';row['policy_sha256']=sha256(row['policy_raw'].encode()).hexdigest()
    rows=api().project_measured_weather(prepare(original))['observations']
    assert rows['rain_counter_in']['value'] is None and rows['light_lux']['value']==12670


def test_common_clock_expiry_preserves_originals_and_cannot_backdate():
    context=prepare();original=context.to_dict()
    rows=api().project_measured_weather(context,as_of=AT+timedelta(seconds=120))['observations']
    assert all(row['value'] is None and row['reason']=='expired_source' for row in rows.values())
    assert context.to_dict()==original
    with pytest.raises(ValueError):api().project_measured_weather(context,as_of=AT-timedelta(seconds=1))


@pytest.mark.parametrize('damage',['future_available','raw_digest','endpoint','extra'])
def test_closed_original_context_refuses_structural_corruption(damage):
    original=sources();row=original['radiation']
    if damage=='future_available':row['available_at']=(AT+timedelta(seconds=1)).isoformat()
    elif damage=='raw_digest':row['raw']+=' '
    elif damage=='endpoint':row['source_endpoint']='http://example.invalid/radiation_evidence'
    else:row['calibrated']=True
    with pytest.raises(ValueError):prepare(original)


def test_zero_lux_and_counter_are_valid_point_values():
    original=sources()
    for kind in original:
        raw=json.loads(original[kind]['raw'])
        if kind=='radiation':raw['record'].update(lightLux=0,irradianceWm2=0)
        else:raw['record']['totalRainIn']=0
        set_raw(original[kind],json.dumps(raw))
    rows=api().project_measured_weather(prepare(original))['observations']
    assert all(row['value']==0 and row['evidence']['quality']=='qualified' for row in rows.values())


def test_frozen_context_is_immutable_and_replay_performs_no_reads(monkeypatch):
    original=sources();context=prepare(original);expected=api().project_measured_weather(context)
    original['rain']['raw']='changed';returned=context.to_dict();returned['sources']['radiation']['raw']='changed'
    import builtins
    def forbidden(*a,**k):pytest.fail('I/O inside frozen measured weather')
    monkeypatch.setattr(builtins,'open',forbidden);monkeypatch.setattr(Path,'read_bytes',forbidden)
    restored=api().PreparedMeasuredWeather(context.content)
    assert api().project_measured_weather(restored)==expected


@pytest.mark.parametrize('kind,field,maximum',[('radiation','raw',8192),('rain','raw',4096),('rain','policy_raw',4096)])
def test_original_text_byte_bounds_are_enforced(kind,field,maximum):
    original=sources();row=original[kind];row[field]='x'*(maximum+1)
    row['sha256' if field=='raw' else 'policy_sha256']=sha256(row[field].encode()).hexdigest()
    with pytest.raises(ValueError):prepare(original)


@pytest.mark.parametrize('damage',['policy_available','policy_digest','identity','missing_key'])
def test_policy_and_fixed_source_identity_cannot_be_resealed_away(damage):
    original=sources();row=original['rain']
    if damage=='policy_available':row['policy_available_at']=(AT+timedelta(seconds=1)).isoformat()
    elif damage=='policy_digest':row['policy_raw']+=' '
    elif damage=='identity':row['source_identity']='arbitrary_counter'
    else:row.pop('expected_epoch')
    with pytest.raises(ValueError):prepare(original)


@pytest.mark.parametrize('created',[AT-timedelta(seconds=1),AT+timedelta(seconds=16),AT.replace(tzinfo=None)])
def test_collection_completion_requires_bounded_aware_original_clock(created):
    with pytest.raises(ValueError):api().prepare_measured_weather(sources=sources(),as_of=AT,created_at=created)


def test_each_point_expires_at_its_original_deadline_independently():
    context=prepare();rows=api().project_measured_weather(context,as_of=AT+timedelta(seconds=117))['observations']
    assert rows['light_lux']['value'] is None and rows['light_lux']['reason']=='expired_source'
    assert rows['rain_counter_in']['value']==12.3


def test_missing_explicit_owner_binding_cannot_qualify_a_point():
    original=sources();original['rain']['expected_epoch']=None
    rows=api().project_measured_weather(prepare(original))['observations']
    assert rows['rain_counter_in']['value'] is None and rows['rain_counter_in']['reason']=='missing_owner_binding'
    assert rows['light_lux']['value']==12670
