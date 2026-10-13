from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import pytest
from household.codec import canonical
from household.snapshot import build_snapshot
from household.sensor_observations import prepare_sensor_observations, attach_sensor_observations
from services.lorawan.tests.test_core import config,NOW
from services.observations.contract import normalize
from services.observations.registry import Registry


def source(synthetic=False):
    cfg=config(radio_verified=True);cfg['environment']='production'
    reg=Registry(cfg);sensor=next(iter(reg.devices.values()))
    point=normalize(sensor=sensor,kind='contact_state',value='OPEN',unit='state',observed_at=NOW,received_at=NOW,
        valid_until=NOW+timedelta(seconds=120),source_identity='chirpstack/device/'+sensor['device_id'],
        raw_sha256='a'*64,source_epoch=sensor['hardware_epoch'],timestamp_basis='network_reception',synthetic=synthetic,qualified=not synthetic)
    raw=canonical(point).decode();registry_raw=canonical(reg.config).decode()
    collector=canonical(dict(schema='earthship-sensor-view/v1',environment='production',authority='observation_only',
        registry_sha256=reg.sha256,generated_at=NOW.isoformat(),expires_at=(NOW+timedelta(seconds=45)).isoformat(),
        normalized_observations={'opening_01:contact_state':point},sensors=[dict(sensor_id='opening_01',valid=True,
            quality='qualified',health='ONLINE',source_epoch=sensor['hardware_epoch'],hardware_epoch=sensor['hardware_epoch'],
            last_received_at=NOW.isoformat(),last_observed_at=NOW.isoformat(),current_state='OPEN')])).decode()
    return collector,registry_raw,sha256(registry_raw.encode()).hexdigest(),{'opening_01:contact_state':dict(raw=raw,sha256=sha256(raw.encode()).hexdigest(),
        available_at=NOW.isoformat(),expected_source_epoch=sensor['hardware_epoch'])}


def base():
    return build_snapshot([],as_of=NOW,created_at=NOW,code_revision='a'*40,config_revision='b'*64,
        requirements={'thermal_current':['air_temperature']},max_age_seconds={'air_temperature':120},max_skew_seconds=120)


def test_explicit_disabled_adapter_preserves_original_snapshot():
    collector,reg,sha,sources=source();prepared=prepare_sensor_observations(registry_raw=reg,registry_sha256=sha,sources=sources,collector_raw=collector,collector_sha256=sha256(collector.encode()).hexdigest(),as_of=NOW)
    parent=base();assert attach_sensor_observations(parent,prepared,enabled=False) is parent
    extended=attach_sensor_observations(parent,prepared,enabled=True)
    document=extended.to_dict()
    assert document['domains']['thermal']['ventilation']['opening_01']['value']=='OPEN'
    assert document['parent_snapshot_id']==parent.snapshot_id
    assert document['planner_authority']=='none'
    assert extended.to_dict()['domains']['energy']==parent.to_dict()['domains']['energy']


def test_synthetic_expired_and_wrong_epoch_never_qualified():
    for fault in ('synthetic','expired','epoch'):
        collector,reg,sha,sources=source(synthetic=fault=='synthetic')
        if fault=='epoch':sources['opening_01:contact_state']['expected_source_epoch']='33333333-3333-4333-8333-333333333333'
        at=NOW+timedelta(seconds=121) if fault=='expired' else NOW
        prepared=prepare_sensor_observations(registry_raw=reg,registry_sha256=sha,sources=sources,collector_raw=collector,collector_sha256=sha256(collector.encode()).hexdigest(),as_of=at)
        assert prepared.to_dict()['observations']['opening_01:contact_state']['value'] is None


def test_original_digest_and_future_availability_refused():
    collector,reg,sha,sources=source();sources['opening_01:contact_state']['sha256']='b'*64
    with pytest.raises(ValueError):prepare_sensor_observations(registry_raw=reg,registry_sha256=sha,sources=sources,collector_raw=collector,collector_sha256=sha256(collector.encode()).hexdigest(),as_of=NOW)
    collector,reg,sha,sources=source();sources['opening_01:contact_state']['available_at']=(NOW+timedelta(seconds=1)).isoformat()
    with pytest.raises(ValueError):prepare_sensor_observations(registry_raw=reg,registry_sha256=sha,sources=sources,collector_raw=collector,collector_sha256=sha256(collector.encode()).hexdigest(),as_of=NOW)


def test_new_supervision_barrier_revokes_previously_qualified_observation():
    collector,reg,sha,sources=source()
    view=json.loads(collector);view['sensors'][0].update(valid=False,quality='counter_conflict',current_state='UNKNOWN')
    collector=canonical(view).decode()
    prepared=prepare_sensor_observations(registry_raw=reg,registry_sha256=sha,sources=sources,as_of=NOW,
        collector_raw=collector,collector_sha256=sha256(collector.encode()).hexdigest())
    point=prepared.to_dict()['observations']['opening_01:contact_state']
    assert point['value'] is None and point['reason']=='supervision_unavailable'


def test_existing_household_provider_reuses_qualified_original():
    from household.evidence import EvidenceRef,Observation
    from services.observations.provider import adapt_provider
    cfg=config(radio_verified=True,transport='zigbee',device_id='zigbee-original',decoder=None,
        capabilities=['air_temperature'],observation_types=['air_temperature'],units={'air_temperature':'degC'})
    sensor=next(iter(Registry(cfg).devices.values()));original=b'original qualified temperature receipt';sha=sha256(original).hexdigest()
    ref=EvidenceRef('air_temperature','existing-temperature-source',sha,sensor['hardware_epoch'],sensor['hardware_epoch'],
        NOW,NOW,NOW,NOW+timedelta(seconds=120),NOW,'qualified',None)
    result=adapt_provider(sensor=sensor,observation=Observation(ref,68,'degF'),original_raw=original,
        expected_sha256=sha,kind='air_temperature',unit='degC',as_of=NOW)
    assert result['value']==20 and result['transport']=='zigbee' and result['quality']=='qualified'


def test_snapshot_reassesses_communication_age_from_real_collector():
    from services.lorawan.engine import Engine
    from services.lorawan.storage import Store
    from services.lorawan.tests.test_core import packet
    cfg=config(radio_verified=True,communication_stale_seconds=10);cfg['environment']='production'
    reg=Registry(cfg);engine=Engine(reg,Store.sqlite());engine.ingest(*packet(),received_at=NOW)
    view=engine.snapshot(NOW)
    point=next(p for row in engine.store.history() for p in row.get('measurements',[]) if p['observation_type']=='contact_state')
    view['normalized_observations']={'opening_01:contact_state':point}
    raw=canonical(point).decode();collector=canonical(view).decode();registry_raw=canonical(reg.config).decode()
    sources={'opening_01:contact_state':dict(raw=raw,sha256=sha256(raw.encode()).hexdigest(),available_at=NOW.isoformat(),expected_source_epoch=point['provenance']['source_epoch'])}
    prepared=prepare_sensor_observations(registry_raw=registry_raw,registry_sha256=sha256(registry_raw.encode()).hexdigest(),
        sources=sources,as_of=NOW+timedelta(seconds=11),collector_raw=collector,collector_sha256=sha256(collector.encode()).hexdigest())
    assert prepared.to_dict()['observations']['opening_01:contact_state']['value'] is None


def test_provider_cannot_relabel_battery_percent_as_humidity():
    from household.evidence import EvidenceRef,Observation
    from services.observations.provider import adapt_provider
    cfg=config(radio_verified=True,transport='wired',device_id='provider-original',decoder=None,
        capabilities=['relative_humidity'],observation_types=['relative_humidity'],units={'relative_humidity':'percent'})
    sensor=next(iter(Registry(cfg).devices.values()));original=b'original qualified battery receipt';sha=sha256(original).hexdigest()
    ref=EvidenceRef('battery_soc','battery-source',sha,sensor['hardware_epoch'],sensor['hardware_epoch'],
        NOW,NOW,NOW,NOW+timedelta(seconds=120),NOW,'qualified',None)
    with pytest.raises(ValueError):adapt_provider(sensor=sensor,observation=Observation(ref,68,'percent'),original_raw=original,
        expected_sha256=sha,kind='relative_humidity',unit='percent',as_of=NOW)
