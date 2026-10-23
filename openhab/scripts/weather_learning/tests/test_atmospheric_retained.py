"""A retained runner must verify measurements and origin inputs before fitting."""
from datetime import timedelta
import importlib
import pytest
from learning_fixtures import T
from weather_learning.contracts import identity


def test_replayed_parent_and_actual_origin_availability_are_both_required():
    api=importlib.import_module('weather_learning.atmospheric_retained')
    parent={'kind':'outdoor_temperature_c','origin':T.isoformat(),'target_at':(T+timedelta(hours=1)).isoformat(),'pair_sha256':'a'*64}
    assert api.verify_parent_replay(parent,dict(parent))==parent
    with pytest.raises(ValueError):api.verify_parent_replay(parent,dict(parent,pair_sha256='b'*64))
    available={(T.isoformat(),'outdoor'):(T+timedelta(days=1)).isoformat()}
    assert api.origin_inputs_available(parent,available,source_class='recorded_ingestion_availability') is False
    assert api.origin_inputs_available(parent,available,source_class='historical_assumed_availability') is True


def test_temperature_parent_replays_through_the_unchanged_serving_feature_function():
    from copy import deepcopy
    from learning_fixtures import full_snapshot
    from test_weather_historical_pairs import observations
    from weather_learning.historical_pairs import pair_temperatures
    api=importlib.import_module('weather_learning.atmospheric_retained');snapshot=full_snapshot();snapshot['historical']=True
    measurements=observations();parent=next(r for r in pair_temperatures(snapshot,measurements) if r['kind']=='outdoor_temperature_c')
    assert api.verify_temperature_parent(parent,snapshot,measurements)==parent
    bad=deepcopy(parent);bad['features']['origin_bias_decay_c']+=1;bad['pair_sha256']=identity({k:v for k,v in bad.items() if k!='pair_sha256'})
    with pytest.raises(ValueError):api.verify_temperature_parent(bad,snapshot,measurements)


def test_offline_audit_counts_and_refuses_connections_and_every_standard_child_launch():
    from atmospheric_ablation_experiment import offline_audit
    state={};hook=offline_audit(state)
    for event in ('socket.connect','subprocess.Popen','os.system','os.posix_spawn','os.fork','os.forkpty','os.exec'):
        with pytest.raises(RuntimeError):hook(event,())
    assert sum(state['blocked_attempts'].values())==7
    hook('open',('/retained/source','r',0));assert sum(state['blocked_attempts'].values())==7
