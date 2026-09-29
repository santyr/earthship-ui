from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / 'file-config'


def test_rain_resources_are_file_owned_read_only_and_distinct():
    thing = (ROOT / 'things/weather-rain-evidence.things').read_text()
    item = (ROOT / 'items/weather-rain-evidence.items').read_text()
    assert 'Thing http:url:weatherRainEvidence ' in thing
    assert 'baseURL="http://127.0.0.1:5000/rain_evidence"' in thing
    assert 'refresh=30' in thing
    assert 'stateMethod="GET"' in thing
    assert 'Type string : snapshot' in thing
    assert 'mode="READONLY"' in thing
    assert 'String Weather_Rain_Evidence_JSON ' in item
    assert 'channel="http:url:weatherRainEvidence:snapshot"' in item
    assert 'weatherTemperatureEvidence' not in thing + item
