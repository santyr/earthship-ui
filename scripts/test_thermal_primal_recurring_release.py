"""Pinned release authority tests: fixture files only, no secrets or services."""
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    spec = importlib.util.spec_from_file_location('recurring_release_test', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def write(path, value):
    path.write_bytes(json.dumps(value).encode() if isinstance(value, dict) else value)
    path.chmod(0o600)
    return dict(path=str(path), sha256=sha256(path.read_bytes()).hexdigest())


@pytest.fixture
def profile(tmp_path):
    tmp_path.chmod(0o700)
    runtime = tmp_path/'runtime'; runtime.mkdir(mode=0o700)
    launcher = runtime/'run.py'
    shutil.copyfile(ROOT/'scripts/thermal-primal-recurring-release.py', launcher); launcher.chmod(0o600)
    release = load(launcher)
    verifier = load(ROOT/'scripts/thermal-primal-runtime.py')
    staged = tmp_path/'frozen'
    pin = verifier.stage(ROOT/'openhab/scripts', staged)['manifest_sha256']
    vfile = runtime/'verify.py'; shutil.copyfile(ROOT/'scripts/thermal-primal-runtime.py', vfile); vfile.chmod(0o600)
    # The verifier must select the separately frozen closure, not live repo files.
    state = tmp_path/'state'; state.mkdir(mode=0o700)
    data = tmp_path/'data'; data.mkdir(mode=0o700)
    files = {}
    for name in ('credentials', 'followup_policy', 'base_policy', 'routes'):
        files[name] = write(tmp_path/(name+'.json'), {'synthetic': name})
    qualification = dict(version=1, scope=release.RECOVERY_SCOPE, status='passed',
        runtime_manifest_sha256=pin, data_snapshot=str(data), data_manifest_sha256='a'*64,
        original_trial_event_id='b'*64, cold_runtime_qualified=True, cold_journal_qualified=True,
        cold_state_qualified=True, cleanup_complete=True, controls_enabled=False,
        **{name+'_sha256': entry['sha256'] for name, entry in files.items()})
    files['qualification'] = write(tmp_path/'qualification.json', qualification)
    files['launcher'] = dict(path=str(launcher), sha256=sha256(launcher.read_bytes()).hexdigest())
    files['verifier'] = dict(path=str(vfile), sha256=sha256(vfile.read_bytes()).hexdigest())
    value = dict(version=1, scope=release.SCOPE, runtime=str(staged), runtime_manifest_sha256=pin,
        state_dir=str(state), interpreter=sys.executable,
        interpreter_sha256=sha256(Path(sys.executable).resolve().read_bytes()).hexdigest(),
        collector='1'*64, operator='2'*64,
        signer=dict(path='/synthetic/signer', sha256='3'*64, version='synthetic'), **files)
    # Actual release verifier is installed beside the frozen runtime; mirror that.
    copied = staged/'verify.py'; shutil.copyfile(vfile, copied); copied.chmod(0o600)
    value['verifier'] = dict(path=str(copied), sha256=sha256(copied.read_bytes()).hexdigest())
    path = tmp_path/'profile.json'; write(path, value)
    return release, path, value, qualification


def verify(bundle):
    release, path, _, _ = bundle
    return release.verify_profile(path, sha256(path.read_bytes()).hexdigest())


def test_every_profile_file_and_frozen_code_pin_is_verified(profile):
    value, qualification = verify(profile)
    assert value == profile[2] and qualification == profile[3]


@pytest.mark.parametrize('name', ['launcher', 'verifier', 'credentials', 'followup_policy',
                                  'base_policy', 'routes', 'qualification'])
def test_changed_component_fails_before_application_import(profile, name):
    path = Path(profile[2][name]['path'])
    path.write_bytes(path.read_bytes()+b'changed')
    with pytest.raises(ValueError): verify(profile)


@pytest.mark.parametrize('field,value', [('controls_enabled', True), ('cleanup_complete', False),
    ('cold_runtime_qualified', False), ('cold_journal_qualified', False), ('cold_state_qualified', False),
    ('status', 'planned'), ('runtime_manifest_sha256', 'f'*64), ('credentials_sha256', 'f'*64)])
def test_incomplete_or_wrong_recovery_proof_cannot_release(profile, field, value):
    release, path, manifest, qualification = profile
    qualification[field] = value
    manifest['qualification'] = write(Path(manifest['qualification']['path']), qualification)
    write(path, manifest)
    with pytest.raises(ValueError): verify(profile)


@pytest.mark.parametrize('problem', ['profile_pin', 'duplicate', 'unknown', 'permissions', 'symlink', 'identity'])
def test_unsafe_profile_refuses(profile, problem):
    release, path, manifest, _ = profile
    if problem == 'profile_pin':
        with pytest.raises(ValueError): release.verify_profile(path, '0'*64)
        return
    if problem == 'duplicate':
        raw = path.read_text(); path.write_text(raw[:-1]+',"version":1}')
    elif problem == 'unknown':
        manifest['arbitrary_command'] = '/synthetic/control'; write(path, manifest)
    elif problem == 'permissions': path.chmod(0o644)
    elif problem == 'symlink':
        link = path.parent/'alias.json'; link.symlink_to(path); path = link
    elif problem == 'identity':
        manifest['operator'] = manifest['collector']; write(path, manifest)
    with pytest.raises(ValueError):
        release.verify_profile(path, sha256(path.read_bytes()).hexdigest())


def test_check_mode_never_opens_publication_or_invokes_the_collector(profile, monkeypatch, capsys):
    release, path, _, _ = profile
    calls = []
    cli = SimpleNamespace(n=SimpleNamespace(PRIMAL_RELEASE_READY=False), main=lambda args:calls.append(args))
    followup = SimpleNamespace(AUTOMATIC_RELEASE_READY=False)
    monkeypatch.setattr(release, 'preflight', lambda *args:(cli, followup))
    assert release.main(['--check-release', '--profile', str(path),
                         '--profile-sha256', sha256(path.read_bytes()).hexdigest()]) == 0
    assert calls == [] and not cli.n.PRIMAL_RELEASE_READY and not followup.AUTOMATIC_RELEASE_READY
    assert json.loads(capsys.readouterr().out)['controls_enabled'] is False


def test_run_opens_only_selected_gates_and_calls_fixed_recurring_mode(profile, monkeypatch):
    release, path, value, _ = profile
    calls = []
    cli = SimpleNamespace(n=SimpleNamespace(PRIMAL_RELEASE_READY=False), main=lambda args:calls.append(args) or 0)
    followup = SimpleNamespace(AUTOMATIC_RELEASE_READY=False)
    monkeypatch.setattr(release, 'preflight', lambda *args:(cli, followup))
    assert release.main(['--run', '--profile', str(path),
                         '--profile-sha256', sha256(path.read_bytes()).hexdigest()]) == 0
    assert cli.n.PRIMAL_RELEASE_READY and followup.AUTOMATIC_RELEASE_READY
    assert calls[0][0] == '--follow-recommendations'
    assert calls[0][calls[0].index('--followup-config')+1] == value['followup_policy']['path']
    assert '--relay-auth' not in calls[0] and '--send-prompts' not in calls[0]


def test_bad_pin_or_arguments_never_echo_private_values(profile, capsys):
    release, path, _, _ = profile
    assert release.main(['--run', '--profile', str(path), '--profile-sha256', 'synthetic-secret']) == 2
    assert 'synthetic-secret' not in capsys.readouterr().err
    with pytest.raises(SystemExit):
        release.main(['--run', '--arbitrary-command', 'synthetic-secret'])
    assert 'synthetic-secret' not in capsys.readouterr().err


def authenticated_profile(bundle, *, enabled=True):
    release, path, manifest, _ = bundle
    manifest.update(version=2, relay_authentication=dict(enabled=enabled,
                                                        relays=list(release.APPROVED_RELAYS)))
    write(path, manifest)
    return release, path, manifest


@pytest.mark.parametrize('enabled', [False, True])
def test_auth_is_selected_only_by_the_exact_pinned_profile(profile, monkeypatch, enabled):
    release, path, value = authenticated_profile(profile, enabled=enabled)
    assert verify(profile)[0] == value
    calls = []
    cli = SimpleNamespace(n=SimpleNamespace(PRIMAL_RELEASE_READY=False), main=lambda args:calls.append(args) or 0)
    monkeypatch.setattr(release, 'preflight', lambda *args:(cli, SimpleNamespace(AUTOMATIC_RELEASE_READY=False)))
    assert release.main(['--run', '--profile', str(path),
                         '--profile-sha256', sha256(path.read_bytes()).hexdigest()]) == 0
    assert ('--relay-auth' in calls[0]) is enabled
    assert '--send-prompts' not in calls[0] and '--process-reply' not in calls[0]


@pytest.mark.parametrize('change', ['string', 'integer', 'other_relay', 'duplicate', 'extra', 'v1'])
def test_auth_consent_cannot_be_coerced_or_expanded(profile, change):
    release, path, value = authenticated_profile(profile)
    auth = value['relay_authentication']
    if change == 'string': auth['enabled'] = 'true'
    elif change == 'integer': auth['enabled'] = 1
    elif change == 'other_relay': auth['relays'][0] = 'wss://unapproved.example'
    elif change == 'duplicate': auth['relays'].append(auth['relays'][0])
    elif change == 'extra': auth['operator_signer'] = True
    elif change == 'v1': value['version'] = 1
    write(path, value)
    with pytest.raises(ValueError): verify(profile)


@pytest.mark.parametrize('side', ['collector', 'operator'])
def test_runtime_routes_cannot_expand_auth_consent(profile, side):
    release, _, value = authenticated_profile(profile)
    routes = {value['collector']:release.APPROVED_RELAYS, value['operator']:release.APPROVED_RELAYS}
    obj = SimpleNamespace(routes=routes, for_recipient=lambda identity:routes[identity])
    release.verify_auth_routes(value, obj)
    routes[value[side]] = (*release.APPROVED_RELAYS, 'wss://unapproved.example')
    with pytest.raises(ValueError): release.verify_auth_routes(value, obj)
