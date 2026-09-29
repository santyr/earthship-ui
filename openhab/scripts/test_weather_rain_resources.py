import json
from pathlib import Path


MANIFEST = Path(__file__).resolve().parents[1] / 'weather-rain-evidence-resources.json'


def test_rain_resources_are_read_only_and_distinct_from_temperature():
    rain = json.loads(MANIFEST.read_text())
    temperature = json.loads((MANIFEST.parent /
                              'weather-temperature-evidence-resources.json').read_text())
    thing = rain['things'][0]
    item = rain['items'][0]
    link = rain['links'][0]
    assert rain['createOnly'] is True and thing['enabled'] is False
    assert thing['configuration']['baseURL'] == 'http://127.0.0.1:5000/rain_evidence'
    assert thing['channels'][0]['configuration'] == {'mode': 'READONLY'}
    assert thing['configuration']['stateMethod'] == 'GET'
    assert item['type'] == 'String'
    assert link['configuration'] == {'profile': 'system:default'}
    assert link['channelUID'] == thing['channels'][0]['uid']
    assert link['itemName'] == item['name']
    assert rain['persistence'] == temperature['persistence']
    assert thing['UID'] != temperature['things'][0]['UID']
    assert item['name'] != temperature['items'][0]['name']
