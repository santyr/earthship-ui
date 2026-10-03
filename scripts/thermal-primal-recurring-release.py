#!/usr/bin/env python3
"""Pinned observational release; never accepts an arbitrary collector command.

The user approved automatic recommendation follow-ups, one per Mountain day.
Only this separately qualified profile can open three process-local gates. The
repository and frozen generic sources stay off. No actuator or operator signer.
Errors never print private values or nested exception diagnostics.
"""
import argparse
from hashlib import sha256
import importlib.util
import importlib.metadata
import json
import os
from pathlib import Path
import re
import stat
import sys

SCOPE = 'earthship-primal-recurring-observation/v1'
RECOVERY_SCOPE = 'earthship-primal-recurring-recovery/v1'
FILES = ('launcher', 'verifier', 'credentials', 'followup_policy', 'base_policy',
         'routes', 'qualification')
FIELDS = {'version', 'scope', 'runtime', 'runtime_manifest_sha256', 'state_dir',
          'interpreter', 'interpreter_sha256', 'collector', 'operator', 'signer', *FILES}
AUTH_FIELD = 'relay_authentication'
APPROVED_RELAYS = ('wss://nos.lol', 'wss://relay.damus.io', 'wss://relay.primal.net')


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, 'recurring thermal release arguments refused; see --help\n')


def require(value):
    if not value:
        raise ValueError('recurring release refused')


def digest(value):
    require(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None)
    return value


def private_path(value, *, directory=False):
    require(isinstance(value, str))
    path = Path(value)
    require(path.is_absolute() and path.resolve() == path)
    info = path.lstat()
    require(info.st_uid == os.getuid())
    if directory:
        require(stat.S_ISDIR(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o700)
    else:
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                and stat.S_IMODE(info.st_mode) == 0o600)
        private_path(str(path.parent), directory=True)
    return path


def read(path, *, maximum=256*1024):
    path = private_path(str(path))
    require(0 < path.stat().st_size <= maximum)
    value = path.read_bytes()
    require(0 < len(value) <= maximum)
    return value


def document(raw):
    def pairs(values):
        result = {}
        for key, value in values:
            require(key not in result)
            result[key] = value
        return result
    def constant(_):
        raise ValueError('recurring release refused')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_profile(path, pin):
    raw = read(path)
    require(sha256(raw).hexdigest() == digest(pin))
    profile = document(raw)
    require(isinstance(profile, dict) and type(profile.get('version')) is int
            and profile['version'] in (1, 2)
            and set(profile) == (FIELDS if profile['version'] == 1 else FIELDS | {AUTH_FIELD})
            and profile['scope'] == SCOPE)
    if profile['version'] == 2:
        auth = profile[AUTH_FIELD]
        require(isinstance(auth, dict) and set(auth) == {'enabled', 'relays'}
                and type(auth['enabled']) is bool and auth['relays'] == list(APPROVED_RELAYS))
    root = private_path(profile['runtime'], directory=True)
    private_path(profile['state_dir'], directory=True)
    require(profile['collector'] != profile['operator'])
    digest(profile['collector']); digest(profile['operator'])
    require(profile['interpreter'] == sys.executable)
    require(importlib.metadata.version('websockets') == '15.0.1'
            and importlib.metadata.version('psycopg2-binary') == '2.9.10')
    interpreter = Path(sys.executable).resolve()
    info = interpreter.stat()
    require(stat.S_ISREG(info.st_mode) and not info.st_mode & 0o022
            and info.st_uid in (0, os.getuid())
            and sha256(interpreter.read_bytes()).hexdigest() == digest(profile['interpreter_sha256']))
    verified = {}
    for name in FILES:
        entry = profile[name]
        require(isinstance(entry, dict) and set(entry) == {'path', 'sha256'})
        verified[name] = read(entry['path'])
        require(sha256(verified[name]).hexdigest() == digest(entry['sha256']))
    require(Path(profile['launcher']['path']) == Path(__file__).absolute()
            and Path(profile['verifier']['path']).parent == root)
    signer = profile['signer']
    require(isinstance(signer, dict) and set(signer) == {'path', 'sha256', 'version'}
            and isinstance(signer['version'], str) and 0 < len(signer['version']) <= 128)
    digest(signer['sha256'])
    # Only the independently pinned pure verifier runs before any application
    # import. It compiles the entire exact closure and checks all gates are off.
    verifier = load_module('recurring_frozen_verifier', profile['verifier']['path'])
    verified_runtime = verifier.verify(root, digest(profile['runtime_manifest_sha256']))
    require(verified_runtime['files'] == 12 and verified_runtime['release_enabled'] is False)
    qualification = document(verified['qualification'])
    expected = {'version', 'scope', 'status', 'runtime_manifest_sha256', 'credentials_sha256',
        'followup_policy_sha256', 'base_policy_sha256', 'routes_sha256', 'data_snapshot',
        'data_manifest_sha256', 'original_trial_event_id', 'cold_runtime_qualified',
        'cold_journal_qualified', 'cold_state_qualified', 'cleanup_complete', 'controls_enabled'}
    require(isinstance(qualification, dict) and set(qualification) == expected
            and type(qualification['version']) is int and qualification['version'] == 1
            and qualification['scope'] == RECOVERY_SCOPE and qualification['status'] == 'passed'
            and qualification['runtime_manifest_sha256'] == profile['runtime_manifest_sha256']
            and qualification['controls_enabled'] is False
            and all(qualification[key] is True for key in ('cold_runtime_qualified',
                'cold_journal_qualified', 'cold_state_qualified', 'cleanup_complete')))
    for name in ('credentials', 'followup_policy', 'base_policy', 'routes'):
        require(qualification[name+'_sha256'] == profile[name]['sha256'])
    private_path(qualification['data_snapshot'], directory=True)
    digest(qualification['data_manifest_sha256']); digest(qualification['original_trial_event_id'])
    return profile, qualification


def preflight(profile, qualification):
    root = Path(profile['runtime'])/'code'
    sys.path.insert(0, str(root))
    import thermal_primal as cli
    import thermal_followup as followup
    from thermal_model import journal, airflow_migration  # Import full audited closure before path checks.
    for name in ('thermal_primal', 'thermal_confirmation', 'thermal_messaging', 'thermal_nip04',
                 'thermal_state_backup', 'thermal_followup', 'advisory_records', 'advisory_windows',
                 'thermal_model.journal', 'thermal_model.schema', 'thermal_model.airflow_migration'):
        require(Path(sys.modules[name].__file__) == root/Path(*name.split('.')).with_suffix('.py'))
    require(cli.n.PRIMAL_RELEASE_READY is False and followup.AUTOMATIC_RELEASE_READY is False
            and journal.V2_WRITE_RELEASE_READY is False)
    snapshot = Path(qualification['data_snapshot'])
    require(sha256(read(snapshot/'manifest.json')).hexdigest() == qualification['data_manifest_sha256'])
    require(cli.b.verify_snapshot(snapshot, transport='nip04')['verified_files'] == 5)
    args = argparse.Namespace(policy=Path(profile['base_policy']['path']),
        routes=Path(profile['routes']['path']), nak=Path(profile['signer']['path']),
        nak_sha256=profile['signer']['sha256'], nak_version=profile['signer']['version'])
    policy, routes, _ = cli.configuration(args)
    require(policy.recipient == profile['collector'] and policy.operators == {profile['operator']})
    verify_auth_routes(profile, routes)
    followup.load_configuration(read(profile['followup_policy']['path']), now=cli.utc_now())
    followup.reader_dsn()
    # Schema audit only. This gate alone cannot publish or ingest a message.
    journal.V2_WRITE_RELEASE_READY = True
    cli.t.JournalSink().require_v2_storage()
    return cli, followup


def verify_auth_routes(profile, routes):
    if profile['version'] == 2:
        # AUTH applies to the shared relay transport. Bind both incoming and
        # outgoing routes, so a future signed list cannot expand this consent.
        require(set(routes.routes) == {profile['collector'], profile['operator']}
                and all(set(routes.for_recipient(identity)) == set(APPROVED_RELAYS)
                        for identity in routes.routes))


def main(argv=None):
    parser = Parser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check-release', action='store_true')
    mode.add_argument('--run', action='store_true')
    parser.add_argument('--profile', required=True, type=Path)
    parser.add_argument('--profile-sha256', required=True)
    # No arbitrary command/argument/transport or environment-based gate override.
    try:
        args = parser.parse_args(argv)
        profile, qualification = verify_profile(args.profile, args.profile_sha256)
        cli, followup = preflight(profile, qualification)
        if args.check_release:
            print(json.dumps(dict(status='passed', scope=SCOPE, publication_enabled=False,
                                  journal_writes=0, messages_sent=0, controls_enabled=False)))
            return 0
        cli.n.PRIMAL_RELEASE_READY = True
        followup.AUTOMATIC_RELEASE_READY = True
        command = ['--follow-recommendations', '--policy', profile['base_policy']['path'],
            '--routes', profile['routes']['path'], '--state-dir', profile['state_dir'],
            '--followup-config', profile['followup_policy']['path'],
            '--nak', profile['signer']['path'], '--nak-sha256', profile['signer']['sha256'],
            '--nak-version', profile['signer']['version']]
        if profile['version'] == 2 and profile[AUTH_FIELD]['enabled']:
            command.append('--relay-auth')
        return cli.main(command)
    except Exception:
        print('recurring thermal release refused; profile or recovery not qualified', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
