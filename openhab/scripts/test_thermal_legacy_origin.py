"""Legacy diagnostic capture must never relabel a v4 model as native-qualified."""
from copy import deepcopy
from dataclasses import asdict
from datetime import timedelta
from hashlib import sha256
import importlib,json
import pytest
from thermal_model.forcing_capture import _canonical
from test_thermal_sensor_epoch_origins import sensor_inputs
from test_thermal_origin_capture import NOW


def module():
    assert importlib.util.find_spec('thermal_legacy_origin') is not None, 'missing legacy diagnostic capture'
    return importlib.import_module('thermal_legacy_origin')


def inputs():
    data=sensor_inputs()
    artifact=asdict(data['artifact']);artifact['schema']='earthship-thermal-model/v4'
    # Synthetic old-model payload for engineering only, never household evidence.
    values=dict(output=data['output'],artifact=artifact,raw_forecast=data['snapshot'],
        forecast_rows=data['rows'],current=data['current'])
    forcing=dict(schema='earthship-thermal-shadow-forcing-capture/v2',
        decision_at=NOW.isoformat(),inputs_available_at=NOW.isoformat(),
        published_at=(NOW+timedelta(seconds=2)).isoformat(),
        sha256={key:sha256(_canonical(value)).hexdigest() for key,value in values.items()},**values)
    return dict(forcing=forcing,native_origin=data['origin_temperatures'],
        runtime=dict(code_revision='a'*64,interpreter_sha256='b'*64,
            python_version='3.12.3',dependencies={'numpy':'1.26.4','scipy':'1.11.4','psycopg2':'2.9.10'},
            source_sha256={'thermal_intel.py':'c'*64,'thermal_model/behavior.py':'d'*64},observer_sha256='e'*64),
        captured_at=NOW+timedelta(seconds=3))


def test_legacy_record_preserves_original_model_and_receipts_without_release_authority():
    data=inputs();r=module().build_legacy_origin(**data)
    assert r['schema']=='earthship-thermal-legacy-shadow-origin/v1'
    assert r['forcing']['artifact']['schema']=='earthship-thermal-model/v4'
    assert r['native_origin']['roles']['air']['identity']['sensor_epoch']==data['native_origin']['roles']['air']['identity']['sensor_epoch']
    assert r['release_authority'] is False
    assert r['artifact_native_phase_fit_claimed'] is False
    assert r['raw_native_source_binding_verified'] is False
    data['forcing']['current']['air']['value']=99.
    assert r['forcing']['current']['air']['value']==74.


@pytest.mark.parametrize('damage',['forcing_digest','native_phase','future_receipt','partial_grid','wrong_initial_receipt','new_artifact','future_capture','runtime_digest'])
def test_refuses_unbound_legacy_diagnostics(damage):
    data=inputs()
    if damage=='forcing_digest':data['forcing']['raw_forecast']['fixture_weather']=False
    elif damage=='native_phase':data['native_origin']['roles']['air']['grid'][-1][1]['sensorEpoch']=data['native_origin']['roles']['mass']['identity']['sensor_epoch']
    elif damage=='future_receipt':data['native_origin']['roles']['air']['grid'][-1][1]['storedAt']=NOW+timedelta(seconds=1)
    elif damage=='partial_grid':data['native_origin']['roles']['air']['grid'].pop()
    elif damage=='wrong_initial_receipt':
        data['forcing']['current']['air']['at']=NOW
        data['forcing']['sha256']['current']=sha256(_canonical(data['forcing']['current'])).hexdigest()
    elif damage=='new_artifact':
        data['forcing']['artifact']['schema']='earthship-thermal-model/v6'
        data['forcing']['sha256']['artifact']=sha256(_canonical(data['forcing']['artifact'])).hexdigest()
    elif damage=='future_capture':data['captured_at']=NOW
    else:data['runtime']['code_revision']='short'
    with pytest.raises(ValueError):module().build_legacy_origin(**data)


def test_immutable_private_roundtrip_and_graduation_reader_refusal(tmp_path):
    tmp_path.chmod(0o700);m=module();r=m.build_legacy_origin(**inputs())
    path=m.write_legacy_origin(tmp_path,r)
    assert m.read_legacy_origin(tmp_path,path)==r
    assert m.write_legacy_origin(tmp_path,r)==path
    assert path.stat().st_mode&0o777==0o600
    from thermal_model.origin_capture import read_observed_origin_capture
    with pytest.raises(ValueError):read_observed_origin_capture(path)
    path.write_bytes(path.read_bytes()+b' ')
    with pytest.raises(ValueError):m.read_legacy_origin(tmp_path,path)


def observer_case(tmp_path):
    from thermal_temperature_runtime import shadow_temperatures_v2
    from test_thermal_sensor_epoch_origins import native_grid,EPOCHS
    import gzip
    data=inputs();archive=tmp_path/'legacy';archive.mkdir(mode=0o700)
    native=lambda now,*,origin_observer=None:shadow_temperatures_v2(now,native_grid(),sensor_epochs=EPOCHS,origin_observer=origin_observer)
    original=tmp_path/'original.json.gz';original.write_bytes(gzip.compress(_canonical(data['forcing']),mtime=0));original.chmod(0o600)
    m=module();assert hasattr(m,'LegacyOriginObserver'),'missing observational wrapper'
    observer=m.LegacyOriginObserver(archive,runtime_provider=lambda:deepcopy(data['runtime']),clock=lambda:NOW+timedelta(seconds=3))
    return observer,native,original,archive


def test_observational_wrappers_preserve_selected_values_and_original_writer_result(tmp_path):
    observer,native,original,archive=observer_case(tmp_path)
    plain=native(NOW);observed=observer.wrap_native(native)(NOW)
    assert observed==plain
    wrapped=observer.wrap_capture(lambda *args,**kwargs:original)
    assert wrapped('unchanged directory',output='unchanged payload')==original
    paths=list(archive.glob('*.legacy-shadow-origin-v1.json'));assert len(paths)==1
    record=module().read_legacy_origin(archive,paths[0])
    assert record['forcing']['current']['air']['value']==74.
    assert record['publication_delivery_verified'] is False


def test_runtime_drift_never_changes_original_capture_result(tmp_path):
    observer,native,original,archive=observer_case(tmp_path);gaps=[]
    observer.on_gap=gaps.append
    observer.wrap_native(native)(NOW)
    changed=inputs()['runtime'];changed['code_revision']='f'*64
    observer.runtime_provider=lambda:changed
    assert observer.wrap_capture(lambda:original)()==original
    assert list(archive.iterdir())==[] and gaps==['legacy_origin_capture_gap']


def test_missing_native_proof_cannot_make_diagnostic(tmp_path):
    observer,native,original,archive=observer_case(tmp_path)
    assert observer.wrap_capture(lambda:original)()==original
    assert list(archive.iterdir())==[]


def test_optional_runtime_failure_preserves_native_reader_and_capture(tmp_path):
    observer,native,original,archive=observer_case(tmp_path)
    def failed():raise ValueError('private diagnostic failure detail')
    observer.runtime_provider=failed
    assert observer.wrap_native(native)(NOW)==native(NOW)
    assert observer.wrap_capture(lambda:original)()==original
    assert list(archive.iterdir())==[]


def test_original_writer_failure_is_preserved(tmp_path):
    observer,native,original,archive=observer_case(tmp_path)
    observer.wrap_native(native)(NOW)
    def failed():raise OSError('original capture failed')
    with pytest.raises(OSError,match='original capture failed'):observer.wrap_capture(failed)()
    assert list(archive.iterdir())==[]


def test_runtime_binding_reads_original_sources_without_executing_them(tmp_path,monkeypatch):
    from test_thermal_origin_capture import private_interpreter
    executable=private_interpreter(tmp_path,monkeypatch)
    root=tmp_path/'runtime';root.mkdir(mode=0o700)
    (root/'thermal_intel.py').write_text('raise RuntimeError("must never execute")\n')
    (root/'thermal_temperature_runtime.py').write_text('# original native worker\n')
    for p in root.iterdir():p.chmod(0o600)
    m=module();assert hasattr(m,'bind_legacy_runtime'),'missing actual legacy runtime binding'
    r=m.bind_legacy_runtime(root,['thermal_intel.py','thermal_temperature_runtime.py'])
    assert r['source_sha256']['thermal_intel.py']==sha256(b'raise RuntimeError("must never execute")\n').hexdigest()
    assert set(r['dependencies'])=={'numpy','scipy','psycopg2'}
    assert r['interpreter_sha256']==sha256(executable.read_bytes()).hexdigest()
    (root/'thermal_intel.py').write_text('# changed original source\n')
    changed=m.bind_legacy_runtime(root,['thermal_intel.py','thermal_temperature_runtime.py'])
    assert changed['code_revision']!=r['code_revision']


def test_runtime_binding_refuses_source_escape_and_writable_source(tmp_path):
    root=tmp_path/'runtime';root.mkdir(mode=0o700)
    (root/'thermal_intel.py').write_text('# original\n');(root/'helper.py').write_text('# original\n')
    for p in root.iterdir():p.chmod(0o600)
    m=module();assert hasattr(m,'bind_legacy_runtime'),'missing actual legacy runtime binding'
    with pytest.raises(ValueError):m.bind_legacy_runtime(root,['thermal_intel.py','../outside.py'])
    (root/'helper.py').chmod(0o666)
    with pytest.raises(ValueError):m.bind_legacy_runtime(root,['thermal_intel.py','helper.py'])
