"""Decoder omissions cannot erase independent station measurements."""
import ast
import json
import math
from pathlib import Path
import pytest


def api():
    tree=ast.parse(Path(__file__).with_name('rtl_weather.py').read_text())
    names={'normalize_wh65b_packet','packet_payload','decode_packet','_finite_field','_unique_object','_reject_constant'}
    scope={'math':math,'json':json,'WH65B_STATION_ID':206}
    exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names],type_ignores=[]),'relay-fields','exec'),scope)
    return scope


def test_partial_outdoor_packet_retains_temperature_and_rain_without_wind_light_uv():
    p=api()['packet_payload']({'model':'Fineoffset-WH65B','id':206,'temperature_C':20,'rain_mm':.254})
    assert p['tempf']==68 and p['totalrainin']==pytest.approx(.01,abs=1e-6)
    assert 'windspeedmph' not in p and 'solarradiation' not in p


def test_invalid_rain_is_omitted_without_discarding_valid_temperature():
    p=api()['packet_payload']({'model':'Fineoffset-WH24','id':206,'temperature_C':20,'rain_mm':10})
    assert p['tempf']==68 and 'totalrainin' not in p


def test_solar_has_distinct_supported_v2_and_unchanged_v1_fields():
    p=api()['packet_payload']({'model':'Fineoffset-WH65B','id':206,'light_lux':200000})
    assert p['solarradiation']==1200 and p['solarproxywm2_v2']==round(200000/126.7,2)


def test_indoor_pressure_is_absolute_with_compatibility_alias_explicit():
    p=api()['packet_payload']({'model':'Fineoffset-WH32B','id':235,'pressure_hPa':800})
    assert p['baromabsin']==p['baromrelin']==round(800*.02953,2)
    assert api()['packet_payload']({'model':'Fineoffset-WH32B','id':236,'temperature_C':20}) is None


def test_invalid_optional_fields_and_foreign_identity_cannot_escape_validation():
    p=api()['packet_payload']({'model':'Fineoffset-WH65B','id':206,'temperature_C':20,'humidity':float('nan'),'uvi':99,'light_lux':-1})
    assert p=={'model':'Fineoffset-WH65B','id':206,'tempf':68.}
    assert api()['packet_payload']({'model':'AmbientWeather-WH31E','id':999,'temperature_C':20}) is None


@pytest.mark.parametrize('raw',['{"model":"x","model":"y"}','{"value":NaN}','[1]','{broken'])
def test_invalid_json_is_a_packet_error_not_radio_process_failure(raw):
    with pytest.raises(ValueError):api()['decode_packet'](raw)
