"""Versioned as-issued release capture and replay, without services or fitting."""
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import json
import stat

import pytest

from test_thermal_release import inputs, shift, NOW
from test_thermal_origin_capture import capture_inputs, EPOCH
from thermal_model.forcing_capture import _canonical
from thermal_model import origin_capture, release


def data(monkeypatch):
    original = capture_inputs()
    source = shift(json.loads(_canonical({key: value for key, value in original.items() if key != 'artifact'})))
    source['artifact'] = original['artifact']
    publication = inputs(monkeypatch)
    source['rows'] = publication['forecast_rows']
    source['output'] = release.build_release_output(**publication)
    return source


def test_release_capture_preserves_full_output_and_native_origin(monkeypatch):
    source = data(monkeypatch)
    record = origin_capture.build_release_origin_capture(**source)
    assert record['schema'] == 'earthship-thermal-origin-capture/v2'
    assert record['output'] == source['output']
    assert record['known_actions'] is None
    assert record['sha256']['artifact'] == source['output']['release']['artifactSha256']
    assert record['sha256']['runtime'] == source['output']['release']['runtimeSha256']
    source['output']['forecast']['trajectory'].clear()
    assert record['output']['forecast']['trajectory']
    with pytest.raises(ValueError): origin_capture.validate_origin_capture(record)


@pytest.mark.parametrize('damage', ['artifact', 'runtime', 'epochs', 'expired', 'future_qualification', 'initial_state'])
def test_release_capture_refuses_rehashed_incompatible_identity_or_clocks(monkeypatch, damage):
    record = origin_capture.build_release_origin_capture(**data(monkeypatch))
    output = record['output']; metadata = output['release']
    if damage == 'artifact': metadata['artifactSha256'] = '0'*64
    elif damage == 'runtime': metadata['runtimeSha256'] = '0'*64
    elif damage == 'epochs': metadata['sensorEpochs']['air'] = '064142d5-99ee-4b7a-b5fc-e6a96e7274d8'
    elif damage == 'expired': metadata['expiresAt'] = (NOW+timedelta(seconds=1)).isoformat()
    elif damage == 'future_qualification': metadata['qualifiedAt'] = (NOW+timedelta(seconds=3)).isoformat()
    elif damage == 'initial_state': output['current']['hallwayF'] += 1
    record['sha256']['output'] = sha256(_canonical(output)).hexdigest()
    with pytest.raises(ValueError): origin_capture.validate_release_origin_capture(record)


def test_release_capture_private_immutable_storage_and_old_reader_refusal(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    record = origin_capture.build_release_origin_capture(**data(monkeypatch))
    path = origin_capture.write_release_origin_capture(tmp_path, record)
    assert path.name.endswith('-origin-v2.json.gz')
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert origin_capture.read_release_origin_capture(path) == record
    assert origin_capture.write_release_origin_capture(tmp_path, record) == path
    with pytest.raises(ValueError): origin_capture.read_origin_capture(path)


def test_prospective_scorer_replays_exact_v2_publication_and_baselines(tmp_path, monkeypatch):
    from thermal_model.graduation_evidence import score_qualified_origin
    from test_thermal_graduation_evidence import receipt
    tmp_path.chmod(0o700)
    record = origin_capture.build_release_origin_capture(**data(monkeypatch))
    path = origin_capture.write_release_origin_capture(tmp_path, record)
    target = NOW+timedelta(hours=1)
    cycles = []
    for lag in range(1, 8):
        start = NOW-timedelta(days=lag); end = target-timedelta(days=lag)
        cycles.extend([[start.isoformat(), receipt(start, 70)], [end.isoformat(), receipt(end, 71)]])
    packet = dict(origin_path=path, publication=dict(time=int((NOW+timedelta(seconds=1)).timestamp()*1000), state=json.dumps(record['output'])),
        horizon_hours=1, outcome=dict(target_at=target.isoformat(), receipt=receipt(target, 74)),
        recent_cycle_grid=cycles, assessed_at=target+timedelta(minutes=10))
    result = score_qualified_origin(**packet)
    assert result['scored_pair']['model_error_f'] == 1
    assert result['scored_pair']['persistence_error_f'] == 0
    assert result['scored_pair']['recent_cycle_error_f'] == 1
    assert result['release_authorized'] is False
    packet['publication']['state'] = json.dumps({**record['output'], 'status': 'shadow'})
    with pytest.raises(ValueError): score_qualified_origin(**packet)


def test_release_emitter_archives_only_after_accepted_publication(tmp_path, monkeypatch):
    import thermal_intel
    from test_thermal_release_runtime import release_case
    thermal, args, _, now = release_case(tmp_path, monkeypatch)
    args.origin_capture_dir = tmp_path/'origins'
    args.origin_capture_dir.mkdir(mode=0o700)
    events = []
    def archive(directory, **source):
        assert events == ['accepted']
        assert directory == args.origin_capture_dir
        assert source['output']['version'] == 2
        assert source['published_at'] == now+timedelta(seconds=2)
        events.append('archived')
    monkeypatch.setattr(thermal, '_archive_release_publication', archive)
    assert thermal._release(args, now, put_state=lambda *_: events.append('accepted'),
        decision_clock=lambda: now, qualification_clock=lambda: now,
        published_clock=lambda: now+timedelta(seconds=2)) == 0
    assert events == ['accepted', 'archived']


def test_release_capture_failure_is_explicit_without_revoking_delivery(tmp_path, monkeypatch, capsys):
    from test_thermal_release_runtime import release_case
    thermal, args, _, now = release_case(tmp_path, monkeypatch)
    args.origin_capture_dir = tmp_path/'origins'
    args.origin_capture_dir.mkdir(mode=0o700)
    sent = []
    def refused(*_args, **_kwargs): raise OSError('storage unavailable')
    monkeypatch.setattr(thermal, '_archive_release_publication', refused)
    assert thermal._release(args, now, put_state=lambda *_: sent.append(True),
        decision_clock=lambda: now, qualification_clock=lambda: now,
        published_clock=lambda: now+timedelta(seconds=2)) == 0
    assert sent == [True]
    assert 'thermal release capture gap' in capsys.readouterr().err


def test_release_preview_does_not_archive_or_invent_acknowledgement(tmp_path, monkeypatch):
    from test_thermal_release_runtime import release_case
    thermal, args, _, now = release_case(tmp_path, monkeypatch)
    args.publish = False
    args.origin_capture_dir = tmp_path/'origins'
    def prohibited(*_args, **_kwargs): raise AssertionError('preview must not archive publication')
    monkeypatch.setattr(thermal, '_archive_release_publication', prohibited)
    assert thermal._release(args, now, decision_clock=lambda: now,
        qualification_clock=lambda: now, published_clock=prohibited) == 0


def test_release_archive_retains_actual_runtime_bundle_and_private_origin(tmp_path, monkeypatch):
    """Real storage transaction; synthetic publication is not release fitness proof."""
    import shutil
    import thermal_intel
    from thermal_model.runtime_bundle import read_runtime_bundle
    source = data(monkeypatch)
    runtime_source = __import__('pathlib').Path(thermal_intel.__file__).resolve().parent
    runtime = tmp_path/'runtime'; runtime.mkdir(mode=0o700)
    for relative in thermal_intel._release_runtime_paths():
        target = runtime/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(runtime_source/relative, target)
        target.chmod(0o600)
    monkeypatch.setattr(thermal_intel, '__file__', str(runtime/'thermal_intel.py'))
    from test_thermal_origin_capture import private_interpreter
    private_interpreter(tmp_path, monkeypatch)
    binding = thermal_intel._release_runtime_binding()
    source['runtime'] = binding
    source['output']['release']['runtimeSha256'] = sha256(_canonical(binding)).hexdigest()
    source.pop('known_actions')
    archive = tmp_path/'origins'; archive.mkdir(mode=0o700)
    path = thermal_intel._archive_release_publication(archive, **source)
    record = origin_capture.read_release_origin_capture(path)
    assert record['runtime'] == binding
    bundles = list((archive/'runtime-bundles').iterdir())
    bundles = [entry for entry in bundles if entry.is_dir()]
    assert len(bundles) == 1
    assert read_runtime_bundle(bundles[0])['release_authorized'] is False


@pytest.mark.parametrize('role',['air','mass','outdoor'])
def test_release_mixed_origin_epoch_withdraws_before_active_publication(tmp_path,monkeypatch,role):
    from test_thermal_release_runtime import release_case
    from test_thermal_release import shift
    from thermal_model.forcing_capture import _canonical
    thermal,args,_,now=release_case(tmp_path,monkeypatch)
    original=capture_inputs()
    proof=shift(json.loads(_canonical(original['origin_temperatures'])))
    current=shift(json.loads(_canonical(original['current'])))
    proof['roles'][role]['grid'][0][1]['streamEpoch']='064142d5-99ee-4b7a-b5fc-e6a96e7274d8'
    def observed(at,*,origin_observer):origin_observer(deepcopy(proof));return deepcopy(current)
    monkeypatch.setattr(thermal,'_current_states',observed)
    sent=[]
    assert thermal._release(args,now,put_state=lambda item,raw:sent.append(json.loads(raw)),decision_clock=lambda:now,qualification_clock=lambda:now)==1
    assert len(sent)==1 and sent[0]['status']=='unavailable'
    assert sent[0]['forecast']['trajectory']==[]
    assert sent[0]['release']['forecastQualified'] is False


@pytest.mark.parametrize('role',['air','mass','outdoor'])
def test_v2_origin_archive_refuses_mixed_epochs_after_rehash(monkeypatch,role):
    record=origin_capture.build_release_origin_capture(**data(monkeypatch))
    record['origin_temperatures']['roles'][role]['grid'][0][1]['streamEpoch']='064142d5-99ee-4b7a-b5fc-e6a96e7274d8'
    record['sha256']['origin_temperatures']=sha256(_canonical(record['origin_temperatures'])).hexdigest()
    with pytest.raises(ValueError,match='epoch'):origin_capture.validate_release_origin_capture(record)
