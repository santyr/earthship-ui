import json
from pathlib import Path


def test_disabled_descriptor_preserves_whole_envelope_with_no_control_or_policy_write():
    descriptor = json.loads((Path(__file__).parents[1] / 'weather-temperature-evidence-resources.json').read_text())
    assert set(descriptor) == {'version', 'createOnly', 'things', 'items', 'links', 'persistence'}
    assert descriptor['version'] == 1 and descriptor['createOnly'] is True
    assert len(descriptor['things']) == len(descriptor['items']) == len(descriptor['links']) == 1
    thing = descriptor['things'][0]
    assert thing['enabled'] is False
    assert thing['UID'] == 'http:url:weatherTemperatureEvidence'
    assert thing['thingTypeUID'] == 'http:url'
    assert thing['configuration'] == {'baseURL': 'http://127.0.0.1:5000/temperature_evidence',
        'refresh': 30, 'timeout': 3000, 'bufferSize': 16384, 'stateMethod': 'GET'}
    channel, = thing['channels']
    assert channel['kind'] == 'STATE' and channel['itemType'] == 'String'
    assert channel['id'] == 'snapshot' and channel['channelTypeUID'] == 'http:string'
    assert channel['defaultTags'] == []
    assert channel['properties'] == {}
    assert channel['configuration'] == {'mode': 'READONLY'}  # no field extraction or command transform
    assert channel['uid'] == 'http:url:weatherTemperatureEvidence:snapshot'
    item, = descriptor['items']
    assert item == {'name': 'Weather_Temperature_Evidence_JSON', 'type': 'String',
        'label': 'Weather temperature receipt evidence', 'category': '', 'tags': [], 'groupNames': []}
    assert descriptor['links'] == [{'itemName': item['name'], 'channelUID': channel['uid'],
        'configuration': {'profile': 'system:default'}}]
    assert descriptor['persistence'] == {'serviceId': 'jdbc', 'strategy': 'everyChange',
        'restoreOnStartup': True, 'existingWildcardPolicyOnly': True}
