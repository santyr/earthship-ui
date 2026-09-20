import json
import pytest
import install_temperature_resources as install


def test_dry_run_never_mutates(monkeypatch):
    monkeypatch.setattr(install.sys, 'argv', ['installer'])
    monkeypatch.setattr(install, 'absent', lambda _: True)
    monkeypatch.setattr(install.oh, 'get', lambda _: [])
    monkeypatch.setattr(install, 'request', lambda *_a, **_k: pytest.fail('dry-run mutation'))
    install.main()


@pytest.mark.parametrize('collision', ['things', 'items'])
def test_existing_resource_refuses_upsert(monkeypatch, collision):
    monkeypatch.setattr(install.sys, 'argv', ['installer', '--apply'])
    monkeypatch.setattr(install, 'absent', lambda path: not path.startswith('/' + collision))
    monkeypatch.setattr(install, 'request', lambda *_a, **_k: pytest.fail('collision mutation'))
    with pytest.raises(RuntimeError, match='Resource exists'):
        install.main()


def test_existing_link_refuses(monkeypatch):
    monkeypatch.setattr(install.sys, 'argv', ['installer', '--apply'])
    monkeypatch.setattr(install, 'absent', lambda _: True)
    manifest = json.loads(install.MANIFEST.read_text())
    monkeypatch.setattr(install.oh, 'get', lambda _: manifest['links'])
    monkeypatch.setattr(install, 'request', lambda *_a, **_k: pytest.fail('collision mutation'))
    with pytest.raises(RuntimeError, match='link collision'):
        install.main()


def test_resume_refuses_enabled_source_without_mutating(monkeypatch):
    monkeypatch.setattr(install.sys, 'argv', ['installer', '--resume-disabled-thing'])
    monkeypatch.setattr(install, 'absent', lambda _: True)
    monkeypatch.setattr(install.oh, 'get', lambda path: [] if path == '/links' else {
        'statusInfo': {'status': 'ONLINE', 'statusDetail': 'NONE'}})
    monkeypatch.setattr(install, 'request', lambda *_a, **_k: pytest.fail('unsafe resume'))
    with pytest.raises(RuntimeError, match='not disabled'):
        install.main()


def test_rule_cleanup_requires_exact_ownership():
    expected = {'uid': 'test', 'actions': [], 'triggers': []}
    assert install.same_rule({**expected, 'status': {'status': 'IDLE'}}, expected)
    assert not install.same_rule({**expected, 'triggers': ['foreign']}, expected)


def test_install_action_is_metadata_only_and_add_only():
    script = install.action('test_marker')
    assert 'ip.add(item)' in script and 'lp.add(link)' in script
    for forbidden in ('sendCommand', 'postUpdate', '.update(', '.remove(', 'executeCommandLine'):
        assert forbidden not in script
    assert 'DISABLED' in script and 'finally' in script and 'ungetService' in script
