from datetime import timedelta
from hashlib import sha256
import json
import pytest
from services.observations.contract import measurement, normalize
from services.observations.water import calibrated_volume
from services.observations.replay import chronological_split
from services.lorawan.generate_openhab import generate
from services.lorawan.tests.test_core import config, NOW
from services.observations.registry import Registry


def test_generic_measurements_have_explicit_units_and_no_invented_volume():
    assert measurement('water_depth',1.2,'m')['value']==1.2
    for kind,value,unit in [('water_depth',1,'L'),('soil_moisture',101,'percent'),('leak',1,'boolean'),('air_temperature',float('nan'),'degC')]:
        with pytest.raises(ValueError):measurement(kind,value,unit)


def test_nonlinear_cistern_calibration_and_hydraulic_isolation():
    calibration=dict(schema='earthship-volume-calibration/v1',revision='survey_1',
        points=[[0,0],[1,100],[2,350]],tank_ids=['tank_a','tank_b'],equalized=True,usable_reserve_litres=20)
    estimate=calibrated_volume(1.5,calibration,connected_tanks=['tank_a','tank_b'],parent_sha256='a'*64)
    assert estimate['estimated_litres']==225 and estimate['estimated_usable_litres']==205
    assert estimate['kind']=='derived_estimate'
    with pytest.raises(ValueError):calibrated_volume(1.5,calibration,connected_tanks=['tank_a'],parent_sha256='a'*64)
    with pytest.raises(ValueError):calibrated_volume(3,calibration,connected_tanks=['tank_a','tank_b'],parent_sha256='a'*64)


def test_chronological_split_has_purge_and_never_trains_on_synthetic():
    rows=[dict(observed_at=(NOW+timedelta(days=i)).isoformat(),synthetic=False,day=i) for i in range(10)]
    train,test=chronological_split(rows,cutoff=NOW+timedelta(days=6),purge_seconds=86400)
    assert max(row['day'] for row in train)==4 and min(row['day'] for row in test)==6
    rows[0]['synthetic']=True
    with pytest.raises(ValueError):chronological_split(rows,cutoff=NOW+timedelta(days=6),purge_seconds=86400)


def test_normalization_never_claims_synthetic_is_qualified():
    sensor=next(iter(Registry(config()).devices.values()))
    args=dict(sensor=sensor,kind='contact_state',value='OPEN',unit='state',observed_at=NOW,received_at=NOW,
        valid_until=NOW+timedelta(seconds=120),source_identity='simulation/test',raw_sha256='a'*64,
        source_epoch=sensor['hardware_epoch'],timestamp_basis='network_reception',synthetic=True)
    assert normalize(**args)['quality']=='synthetic'
    with pytest.raises(ValueError):normalize(**args,qualified=True)


def test_generated_openhab_is_inbound_only_and_has_supervision():
    files=generate(Registry(config()),dict(host='broker',port=1883,username='openhab',password='development-test'))
    assert 'commandTopic' not in files['things/earthship-sensors.things']
    assert 'Contact Sensor_opening_01_Contact' in files['items/earthship-sensors.items']
    assert 'Sensor_opening_01_Valid' in files['items/earthship-sensors.items']
    assert 'postUpdate' in files['automation/js/earthship-sensor-supervision.js']
    assert 'sendCommand' not in ''.join(files.values())
    assert 'Earthship_Sensor_View_JSON' in files['items/earthship-sensors.items']


def test_secret_strings_are_escaped_in_openhab():
    files=generate(Registry(config()),dict(host='broker',port=1883,username='x',password='"\\\n'))
    assert 'password="\\"\\\\\\n"' in files['things/earthship-sensors.things']


def test_registry_removal_keeps_originals_without_breaking_publisher():
    from services.lorawan.engine import Engine
    from services.lorawan.storage import Store
    from services.lorawan.tests.test_core import packet
    from services.lorawan.runtime import publish_view,synthetic_ingest
    from services.lorawan.simulate import registry,environmental_events
    class Client:
        def is_connected(self):return True
        def publish(self,*args,**kwargs):pass
    engine=Engine(Registry(registry()),Store.sqlite())
    engine.ingest(*packet(),received_at=NOW)
    for raw,topic in environmental_events(NOW):synthetic_ingest(engine,raw,topic,NOW)
    before=engine.store.count('observations')
    cfg=registry();cfg['devices']=[];engine.registry=Registry(cfg)
    view=publish_view(Client(),engine,NOW,{})
    assert view['sensors']==[] and view['environmental']==[] and view['normalized_observations']=={}
    assert engine.store.count('observations')==before


def test_station_render_preserves_vendor_radio_profile_and_usb_schema():
    from services.lorawan.prepare_station import render_station
    profile={'SX1302_conf':{'device':'spi:/dev/spidev0.0','radio_0':{'tx_gain_lut':[{'rf_power':12}]},'radio_1':{'type':'SX1250'}},'station_conf':{'routerid':''}}
    result=render_station(profile,'aaaaaaaaaaaaaaaa')
    assert result['SX1302_conf']['device']=='usb:/dev/ttyACM0'
    assert result['SX1302_conf']['radio_0']==profile['SX1302_conf']['radio_0']
    assert profile['SX1302_conf']['device']=='spi:/dev/spidev0.0'
    assert result['station_conf']['routerid']=='aaaaaaaaaaaaaaaa'
