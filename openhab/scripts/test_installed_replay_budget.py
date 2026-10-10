"""One scoped calibration budget constrains nested replay and final publication."""
import importlib
from pathlib import Path
import pytest


def module():return importlib.import_module('thermal_model.replay_budget')


def test_numerical_deadlines_share_remaining_time_and_scope_restores_default(monkeypatch):
    from thermal_model import installed_shade_artifact as artifact
    budget=module();clock=[100.]
    monkeypatch.setattr(artifact.time,'monotonic',lambda:clock[0])
    with budget.shared_replay_budget(lambda:105.-clock[0]):
        assert artifact._deadline(60)==105.
        clock[0]=103.;assert artifact._deadline(60)==105.
        clock[0]=105.
        with pytest.raises(ValueError):artifact._deadline(60)
    assert artifact._deadline(60)==165.


@pytest.mark.parametrize('kind',['candidate','calibration'])
def test_budget_expiring_during_private_write_prevents_final_immutable_publication(tmp_path,monkeypatch,kind):
    from thermal_model import installed_shade_artifact as artifact,installed_shade_calibration as calibration,runtime_bundle
    budget=module();tmp_path.chmod(0o700);clock=[0.]
    owner=artifact if kind=='candidate' else runtime_bundle;original=owner._write_private
    def late(*args):original(*args);clock[0]=6.
    monkeypatch.setattr(owner,'_write_private',late)
    persist=artifact._persist if kind=='candidate' else calibration._persist
    with budget.shared_replay_budget(lambda:5.-clock[0]):
        with pytest.raises(ValueError):persist(tmp_path,{'synthetic':True},'a'*64,'.test.json')
    assert list(tmp_path.iterdir())==[]


def test_nested_budget_cannot_extend_the_outer_invocation():
    budget=module();clock=[0.]
    with budget.shared_replay_budget(lambda:5.-clock[0]):
        with budget.shared_replay_budget(lambda:100.):
            assert budget.remaining_budget(60)==5.
            clock[0]=5.
            with pytest.raises(ValueError):budget.check_shared_budget()


def test_raw_source_replay_uses_shared_budget_before_opening_any_source(monkeypatch):
    from thermal_model import installed_shade_qualification as qualification
    budget=module();clock=[0.]
    def preflight(packets,check_budget,**kwargs):clock[0]=6.;check_budget()
    monkeypatch.setattr(qualification,'_raw_replay_preflight',preflight)
    from thermal_model import installed_shade_raw_score_sources as sources
    monkeypatch.setattr(sources,'read_raw_score_sources',lambda *a,**kw:pytest.fail('source opened after shared deadline'))
    with budget.shared_replay_budget(lambda:5.-clock[0]):
        with pytest.raises(ValueError):qualification._score_packets([{'raw_score_sources_path':'/missing'}],assessed_at='2026-01-01T00:00:00Z',version=4)


def test_real_full_raw_runtime_binding_and_archive_include_budget_helper(tmp_path,monkeypatch):
    from thermal_model.installed_shade_publication import RAW_RUNTIME_PATHS
    from thermal_model.origin_capture import build_runtime_binding
    from thermal_model.runtime_bundle import capture_runtime_bundle,read_runtime_bundle
    root=tmp_path/'runtime';root.mkdir(mode=0o700);original=Path(__file__).resolve().parent
    for name in RAW_RUNTIME_PATHS:
        target=root/name;target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        target.write_bytes((original/name).read_bytes());target.chmod(0o600)
    # Retain actual interpreter bytes independently of hosted tool-cache permissions.
    import sys
    executable=tmp_path/'python';executable.write_bytes(Path(sys.executable).resolve().read_bytes())
    executable.chmod(0o777);monkeypatch.setattr(sys,'executable',str(executable))
    paths=sorted(RAW_RUNTIME_PATHS)
    with pytest.raises(ValueError,match='non-writable runtime source'):
        build_runtime_binding(root,paths)
    executable.chmod(0o700)
    actual=build_runtime_binding(root,paths)
    archive=tmp_path/'archive';archive.mkdir(mode=0o700)
    saved=capture_runtime_bundle(archive,root,paths,expected_binding=actual)
    loaded=read_runtime_bundle(saved)
    assert loaded['runtime']==actual and loaded['revision_paths']==paths
    assert set(actual['source_manifest'])==set(paths)
    assert 'thermal_model/replay_budget.py' in actual['source_manifest']


def test_legacy_preparation_requires_executed_budget_helper_in_its_runtime(monkeypatch,tmp_path):
    from thermal_model import installed_shade_publication as publication
    from thermal_model.forcing_capture import _canonical
    tmp_path.chmod(0o700)
    refs=dict(schema=publication.REFERENCE_SCHEMA,registration_path=None,candidate_path='base',runtime_bundle_path='runtime',original_pairs_path=None)
    path=tmp_path/'refs';path.write_bytes(_canonical(refs));path.chmod(0o600)
    runtime=dict(source_manifest={key:'a'*64 for key in publication.RUNTIME_PATHS if key!='thermal_model/replay_budget.py'})
    monkeypatch.setattr(publication,'read_runtime_bundle',lambda _:dict(runtime=runtime,revision_paths=list(runtime['source_manifest'])))
    monkeypatch.setattr(publication,'build_runtime_binding',lambda *a:runtime)
    monkeypatch.setattr(publication,'read_candidate_bundle',lambda *a,**kw:pytest.fail('unbound helper reached candidate preparation'))
    assert publication.prepare_installed_qualification(path).source_ready is False


def test_64_declared_files_cannot_add_an_unlisted_observer(monkeypatch,tmp_path):
    from thermal_model import origin_capture,runtime_bundle
    paths=['thermal_intel.py',*[f'file_{index}.py' for index in range(63)]]
    monkeypatch.setattr(origin_capture,'_source_bytes',lambda *a,**kw:pytest.fail('oversized observer closure opened source'))
    with pytest.raises(ValueError):origin_capture.build_runtime_binding(tmp_path,paths)
    with pytest.raises(ValueError):runtime_bundle._revision(paths,{name:b'x' for name in paths})
