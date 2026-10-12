"""Exact native geometry cache contracts; numerical samples here are synthetic."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from hashlib import sha256
import importlib,json,math
import pytest

NOW=datetime(2026,10,12,21,20,tzinfo=timezone.utc)
TIMES=[datetime.fromisoformat(s) for s in ('2024-02-29T12:00:00+00:00','2026-03-08T01:30:00-07:00','2026-11-01T01:30:00-06:00','2026-11-01T01:30:00-07:00')]
RUNTIME={'binding_version':'5.2.3','collector_sha256':'e'*64,'libraries':{'astro_binding':'a'*64,'openhab_core':'b'*64,'unit_api':'c'*64}}

def api():return importlib.import_module('astro_geometry')

def fixture():
    request=api().build_request(TIMES,requested_at=NOW,latitude=38.3739919,longitude=-105.7744609,timezone_name='America/Denver')
    source=api().build_source(request,observed_at=NOW+timedelta(seconds=1),native_runtime=RUNTIME,source_status='ONLINE',latitude=38.3739919,longitude=-105.7744609,timezone_name='America/Denver',altitude_m=None)
    output=''.join(at+'\t'+str(el)+'\t'+str(az)+'\n' for at,el,az in zip(request['instants'],(-1,0,1,20),(50,100,150,200))).encode()
    cache=api().build_cache(request,source,native_output=output,computed_at=NOW+timedelta(seconds=2))
    return request,source,output,cache


def test_exact_leap_dst_and_both_fold_instants_replay_without_provider_calls():
    request,source,output,cache=fixture()
    restored=api().replay_cache(json.dumps(cache.to_dict()).encode(),request=request,expected_cache_sha256=cache.sha256,expected_native_runtime=RUNTIME)
    assert restored.to_dict()==cache.to_dict()
    assert len(request['instants'])==4 and request['instants'][-2]!=request['instants'][-1]
    assert restored.elevation_sin(TIMES[-1])==pytest.approx(math.sin(math.radians(20)))
    assert restored.is_thermal_night(TIMES[0]) and restored.is_thermal_night(TIMES[1])
    assert not restored.is_thermal_night(TIMES[2])
    assert restored.descriptor()['rule']=='earthship-native-solar-elevation/v2'
    assert restored.descriptor()['native_runtime']==RUNTIME


def test_equivalent_offset_instants_deduplicate_but_preserve_exact_millisecond():
    instant=NOW+timedelta(milliseconds=123)
    offset=instant.astimezone(timezone(timedelta(hours=-6)))
    request=api().build_request([offset,instant],requested_at=NOW,latitude=38.3739919,longitude=-105.7744609,timezone_name='America/Denver')
    assert request['instants']==[instant.isoformat()]


@pytest.mark.parametrize('bad',[NOW.replace(tzinfo=None),NOW+timedelta(microseconds=1)])
def test_naive_or_submillisecond_instants_refuse_without_rounding(bad):
    with pytest.raises(ValueError):api().build_request([bad],requested_at=NOW,latitude=38.3739919,longitude=-105.7744609,timezone_name='America/Denver')


@pytest.mark.parametrize('kind',['empty','oversize'])
def test_request_size_is_bounded(kind):
    points=[] if kind=='empty' else [NOW+timedelta(seconds=i) for i in range(257)]
    with pytest.raises(ValueError):api().build_request(points,requested_at=NOW,latitude=38.3739919,longitude=-105.7744609,timezone_name='America/Denver')


@pytest.mark.parametrize('version',['5.2.1','5.2.3-SNAPSHOT','5.2.3.extra','05.2.3'])
def test_unsupported_calculation_runtime_refuses(version):
    request,source,output,cache=fixture();native=deepcopy(RUNTIME);native['binding_version']=version
    with pytest.raises(ValueError):api().build_source(request,observed_at=NOW+timedelta(seconds=1),native_runtime=native,source_status='ONLINE',latitude=38.3739919,longitude=-105.7744609,timezone_name='America/Denver',altitude_m=None)


@pytest.mark.parametrize('damage',['missing','reordered','different_time','nan','infinite','outside_range','extra_column'])
def test_native_batch_must_exactly_cover_requested_instants(damage):
    request,source,output,_=fixture();lines=output.decode().splitlines()
    if damage=='missing':lines.pop()
    if damage=='reordered':lines.reverse()
    if damage=='different_time':lines[0]=lines[0].replace(request['instants'][0],NOW.isoformat())
    if damage=='nan':lines[0]=lines[0].replace('\t-1\t','\tNaN\t')
    if damage=='infinite':lines[0]=lines[0].replace('\t-1\t','\tInfinity\t')
    if damage=='outside_range':lines[0]=lines[0].replace('\t-1\t','\t-91\t')
    if damage=='extra_column':lines[0]+='\tunexpected'
    with pytest.raises(ValueError):api().build_cache(request,source,native_output=('\n'.join(lines)+'\n').encode(),computed_at=NOW+timedelta(seconds=2))


def test_missing_geometry_has_no_legacy_fallback_and_returned_records_are_copies():
    request,source,output,cache=fixture();record=cache.to_dict();record['positions'][0]['elevation_degrees']=80
    assert cache.is_thermal_night(TIMES[0])
    with pytest.raises(KeyError):cache.elevation_sin(NOW)


@pytest.mark.parametrize('damage',['geometry','runtime','request','source_time','cache_time','extra_field'])
def test_resealed_cache_cannot_change_pinned_runtime_request_or_native_output(damage):
    request,source,output,cache=fixture();record=cache.to_dict()
    if damage=='geometry':record['positions'][0]['elevation_degrees']=2
    if damage=='runtime':record['source']['native_runtime']['libraries']['astro_binding']='d'*64
    if damage=='request':record['request']['instants'][0]=NOW.isoformat()
    if damage=='source_time':record['source']['observed_at']=(NOW-timedelta(seconds=1)).isoformat()
    if damage=='cache_time':record['computed_at']=(NOW-timedelta(seconds=1)).isoformat()
    if damage=='extra_field':record['claim_authority']=True
    # An internally resealed artifact must still fail original contextual pins.
    for target,field in ((record['request'],'request_sha256'),(record['source'],'source_sha256'),(record,'cache_sha256')):
        target[field]=sha256(json.dumps({k:v for k,v in target.items() if k!=field},sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    with pytest.raises(ValueError):api().replay_cache(json.dumps(record).encode(),request=request,expected_cache_sha256=record['cache_sha256'],expected_native_runtime=RUNTIME)


def test_original_cache_identity_is_required_for_offline_replay():
    request,source,output,cache=fixture()
    with pytest.raises(ValueError):api().replay_cache(json.dumps(cache.to_dict()).encode(),request=request,expected_cache_sha256='f'*64,expected_native_runtime=RUNTIME)


def test_resealed_boolean_angle_is_not_a_native_numeric_quantity():
    request,source,output,cache=fixture();record=cache.to_dict()
    record['positions'][2]['elevation_degrees']=True
    record['cache_sha256']=sha256(json.dumps({k:v for k,v in record.items() if k!='cache_sha256'},sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    with pytest.raises(ValueError):api().replay_cache(json.dumps(record).encode(),request=request,expected_cache_sha256=record['cache_sha256'],expected_native_runtime=RUNTIME)


@pytest.mark.parametrize('damage',['offline','site','timezone','unknown_altitude','missing_library','source_before_request'])
def test_source_configuration_and_availability_must_match_original_request(damage):
    request,source,output,cache=fixture()
    args=dict(observed_at=NOW+timedelta(seconds=1),native_runtime=deepcopy(RUNTIME),source_status='ONLINE',latitude=38.3739919,longitude=-105.7744609,timezone_name='America/Denver',altitude_m=None)
    if damage=='offline':args['source_status']='OFFLINE'
    if damage=='site':args['latitude']+=1
    if damage=='timezone':args['timezone_name']='UTC'
    if damage=='unknown_altitude':args['altitude_m']='unknown'
    if damage=='missing_library':args['native_runtime']['libraries'].pop('astro_binding')
    if damage=='source_before_request':args['observed_at']=NOW-timedelta(seconds=1)
    with pytest.raises(ValueError):api().build_source(request,**args)


def test_native_batch_collector_code_identity_is_required():
    request,source,output,cache=fixture();weak=deepcopy(RUNTIME);weak.pop('collector_sha256',None)
    with pytest.raises(ValueError):api().build_source(request,observed_at=NOW+timedelta(seconds=1),native_runtime=weak,source_status='ONLINE',latitude=38.3739919,longitude=-105.7744609,timezone_name='America/Denver',altitude_m=None)
