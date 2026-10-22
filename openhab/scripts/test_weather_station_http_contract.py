"""Station resources must match the HTTP binding's advertised channel contract."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[2]

def test_station_http_channels_use_types_advertised_by_the_actual_binding():
    advertised=json.loads((ROOT/'tests/fixtures/openhab-http-channel-types-5.2.3.json').read_bytes())['types']
    resources=json.loads((ROOT/'openhab/weather-station-v2-resources.json').read_bytes())
    for channel in resources['things'][0]['channels']:
        assert channel['itemType']==advertised[channel['channelTypeUID']]['itemType'],channel['uid']


def test_quantity_dimensions_belong_to_linked_items_and_units_remain_explicit():
    resources=json.loads((ROOT/'openhab/weather-station-v2-resources.json').read_bytes());channels={c['uid']:c for c in resources['things'][0]['channels']};items={i['name']:i for i in resources['items']}
    numeric=0
    for link in resources['links']:
        c=channels[link['channelUID']];i=items[link['itemName']]
        if c['channelTypeUID']=='http:number':
            numeric+=1;assert i['type'].startswith('Number:');assert c['configuration']['unit']==i['metadata']['unit']['value'];assert c['configuration']['mode']=='READONLY'
    assert numeric==12


def test_incomplete_calendar_amounts_have_explicit_recorded_lower_bound_items():
    r=json.loads((ROOT/'openhab/weather-station-v2-resources.json').read_bytes());channels={c['uid']:c for c in r['things'][0]['channels']};links={x['itemName']:x['channelUID'] for x in r['links']};items={i['name']:i for i in r['items']}
    for period in ('Day','Week','Month'):
        name='WeatherStation_Rain'+period+'RecordedV2';item=items[name];channel=channels[links[name]]
        assert item['type']=='Number:Length' and 'lower bound' in item['label'].lower()
        assert item['metadata']['expire']['value']=='90s,state=UNDEF'
        assert 'partial' in item['metadata']['stateDescription']['config']['pattern']
        assert channel['configuration']['stateTransformation']==['JSONPATH:$.rain.products.'+period.lower()+'.recorded_in']


def test_rain_and_pressure_items_retain_hundredth_unit_display_precision():
    r=json.loads((ROOT/'openhab/weather-station-v2-resources.json').read_bytes())
    names={'WeatherStation_PressureAbsoluteV2',*('WeatherStation_Rain'+x+'V2' for x in ('Day','Week','Month','Event','Hour','Rate'))}
    for item in r['items']:
        if item['name'] in names:
            assert item['metadata']['stateDescription']['config']=={'pattern':'%.2f %unit%','readOnly':True}
