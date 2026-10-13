"""Native driver selection preserves forecast-first observer isolation."""
import json
import pytest
from test_household_cycle_driver import setup


def native_setup(tmp_path,monkeypatch):
    import native_thermal_live as native
    cycle,config,params,calls=setup(tmp_path,monkeypatch)
    from pathlib import Path
    body=json.loads(config.read_bytes());path=Path(body['forecast_config'])
    path.write_text(json.dumps({'schema':native.LIVE_SCHEMA}))
    settings=dict(schema=native.LIVE_SCHEMA,shared_lock=str(tmp_path/'lock'),token_file=str(tmp_path/'token'),
        openhab_base='http://127.0.0.1:8080/rest',artifact_sha256='a'*64,runtime_sha256='c'*64)
    monkeypatch.setattr(native,'load_settings',lambda *a,**kw:settings)
    monkeypatch.setattr(native,'current_runtime',lambda **kw:{'selected_runtime':'c'*64})
    def publish(value,*,guard,backend):
        assert value==settings;guard();calls.append('native_published');backend.collection={'status':'collected'}
        return dict(status='published',delivery_verified=True,origin_path='native-origin',delivery_path='native-delivery',
            capture_sha256='b'*64,artifact_sha256='a'*64,runtime_sha256='c'*64)
    monkeypatch.setattr(native,'publish_cycle',publish)
    monkeypatch.setattr(native,'withdraw',lambda *a,**kw:calls.append('native_withdrawn') or {'status':'withdrawn','delivery_verified':True})
    def complete(**kw):
        calls.append('native_observed');kw['guard']()
        assert kw['runtime']=={'selected_runtime':'c'*64}
        assert kw['expected_artifact_sha256']=='a'*64 and kw['expected_capture_sha256']=='b'*64
        return {'status':'observation_written','automatic_actuation':False}
    monkeypatch.setattr(cycle,'complete_cycle',complete)
    return cycle,native,config,calls


def test_native_config_selects_native_producer_and_passes_external_pins_to_observer(tmp_path,monkeypatch):
    cycle,native,config,calls=native_setup(tmp_path,monkeypatch)
    result=cycle.run_cycle(config,code_revision='e'*40)
    assert result['status']=='published' and result['observation']['status']=='observation_written'
    assert 'native_published' in calls and 'native_observed' in calls
    assert 'published' not in calls and 'withdrawn' not in calls
    assert 'native-origin' not in json.dumps(result)


def test_native_observer_failure_preserves_successful_forecast(tmp_path,monkeypatch):
    cycle,native,config,calls=native_setup(tmp_path,monkeypatch)
    def refused(**kw):raise ValueError('private diagnostic')
    monkeypatch.setattr(cycle,'complete_cycle',refused)
    result=cycle.run_cycle(config,code_revision='e'*40)
    assert result['status']=='published' and result['observation']['status']=='observation_refused'
    assert 'native_withdrawn' not in calls and 'withdrawn' not in calls


def test_native_producer_failure_uses_native_unavailable_withdrawal(tmp_path,monkeypatch):
    cycle,native,config,calls=native_setup(tmp_path,monkeypatch)
    def refused(*a,**kw):raise ValueError('private source failure')
    monkeypatch.setattr(native,'publish_cycle',refused)
    result=cycle.run_cycle(config,code_revision='e'*40)
    assert result['status']=='withheld_and_withdrawn' and result['delivery_verified'] is True
    assert 'native_withdrawn' in calls and 'withdrawn' not in calls
