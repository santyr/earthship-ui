#!/usr/bin/env python3
"""One-shot recurring release recovery; never starts a collector or actuator.

Initializes only approved daily-limit SQLite metadata under the shared lock.
Exports production PostgreSQL read-only; restores/idempotent ACK rehearsal only
in an owned disposable PostgreSQL container. Credentials never enter diagnostics.
Run with the dedicated private recurring EnvironmentFile; no operator secret.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
from uuid import uuid4

REPO = Path('/home/sat/earthship-ui')
RUNTIME = Path('/home/sat/.local/libexec/earthship-thermal/primal-v3')
RUNTIME_PIN = '490ef7f0d6bb628d12b1377225cd9ca316e42c849a5dde7b2bc3866667dbf1e2'
CONFIG = Path('/home/sat/.config/hex/thermal-primal')
ENVIRONMENT = Path('/home/sat/.config/hex/thermal-primal-followup.env')
ENVIRONMENT_PIN = '8b28140c708216b09859589f10ef128c2a53d75bce4a9bdf8afe9f1500e9efc4'
STATE = Path('/home/sat/.local/state/thermal-primal')
RECOVERY = Path('/home/sat/.local/state/thermal-intel/collector-recovery/2026-10-03-primal-recurring-v3')
BASELINE = RECOVERY.parent/'2026-10-01-primal-inactive'
TRIAL_EVENT = '66fd98c7bf7bfad7ae5041ee8f7d1c5732be43c3275b8c031a917f3249e980fe'
TRIAL_CIPHER = '5f42bc50bf00d23b56ecc02eaae3363b692192569e93115f0cecfff85a5ca207'
STEP = 'preflight'


def checkpoint(name):
    global STEP
    STEP = name


def require(value):
    if not value: raise ValueError('recurring recovery refused')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def modules(root):
    sys.path.insert(0, str(root/'code'))
    import thermal_primal as cli
    import thermal_followup as followup
    from thermal_model import journal, airflow_migration
    require(cli.n.PRIMAL_RELEASE_READY is False and followup.AUTOMATIC_RELEASE_READY is False
            and journal.V2_WRITE_RELEASE_READY is False)
    return cli, followup, journal


def current_args(policy, routes, signer=None):
    signer = signer or Path(os.environ['EARTHSHIP_PRIMAL_NAK'])
    return argparse.Namespace(policy=policy, routes=routes, nak=signer,
        nak_sha256=os.environ['EARTHSHIP_PRIMAL_NAK_SHA256'],
        nak_version=os.environ['EARTHSHIP_PRIMAL_NAK_VERSION'])


def cli_snapshot_valid(stage):
    stage.verify(RECOVERY/'runtime', RUNTIME_PIN)
    import thermal_state_backup as backup
    require(backup.verify_snapshot(RECOVERY/'data', transport='nip04')['verified_files'] == 5)
    return True


def cold_probe(working):
    """No relay calls; append/readback only the original receipt in fixture PG."""
    import psycopg2
    from psycopg2.extensions import parse_dsn
    params = parse_dsn(os.environ['THERMAL_DATABASE_URL'])
    require(params['host'] == '127.0.0.1' and params['dbname'] == 'postgres'
            and params['user'] == os.environ['THERMAL_DATABASE_RUNTIME_ROLE']
            and 1024 < int(params['port']) < 65536 and int(params['port']) != 5432)
    stage = load('cold_stage', working/'runtime/verify-runtime.py')
    stage.verify(working/'runtime', RUNTIME_PIN)
    cli, followup, journal = modules(working/'runtime')
    policy, routes, keyer = cli.configuration(current_args(working/'data/policy.json',
        working/'data/routes.json', working/'runtime/nak'))
    cli.check_primal_identity(keyer, policy.recipient)
    settings = followup.load_configuration((working/'followup.json').read_bytes(), now=cli.utc_now())
    followup.reader_dsn()
    ledger, outbox = cli.n.PrimalLedger(working/'state'), cli.n.PrimalOutbox(working/'state')
    try:
        followup.initialize(ledger.db)
        followup.pin_configuration(ledger.db, settings, policy=policy)
        policy = followup.combined_policy(ledger.db, policy=policy)
        row = ledger.get(TRIAL_EVENT)
        require(row is not None and row['digest'] == TRIAL_CIPHER
                and row['disposition'] == 'confirmed' and row['acknowledgement'] is not None)
        ledger._revalidate_prior(row, policy, cli.n.Nip04Codec(keyer), cli.utc_now())
        original_outbox = outbox.rows()
        journal.V2_WRITE_RELEASE_READY = True
        sink = cli.t.JournalSink(); sink.require_v2_storage()
        cli.n.PRIMAL_RELEASE_READY = True
        delivery = cli.n.PrimalDelivery(policy, routes, ledger, outbox,
            cli.n.Nip04Codec(keyer), cli.n.PrimalRelay(keyer, policy.recipient, policy.operators), sink)
        ack = next(item for item in original_outbox if item['intent'] == 'ack:'+TRIAL_EVENT)
        require(delivery.authorize(ack, cli.utc_now()) == cli.t.strict_json(ack['wrapped'].encode()))
        require(ledger.get(TRIAL_EVENT) == row and outbox.rows() == original_outbox)
        require(ledger.db.execute('SELECT count(*) FROM automatic_questions').fetchone()[0] == 0)
    finally:
        ledger.close(); outbox.close()
    print(json.dumps(dict(status='cold_probe_passed', local_identity_verified=True,
        original_receipt_verified=True, original_ack_cipher_verified=True,
        first_receipt_preserved=True, controls_enabled=False, relay_publications=0)))


def prepare_and_rehearse(resume_pin=None):
    import psycopg2
    from psycopg2 import sql
    stage = load('recurring_stage', REPO/'scripts/thermal-primal-runtime.py')
    stage.verify(RUNTIME, RUNTIME_PIN)
    require(sha256(stage.read(ENVIRONMENT, private=True)).hexdigest() == ENVIRONMENT_PIN)
    baseline_manifest = (BASELINE/'bundle-manifest.json').read_bytes()
    require(sha256(baseline_manifest).hexdigest() ==
            '4e99025c6652371cc51020be387bfd404481db33c4402f818f50d8985561dcc4')
    baseline = json.loads(baseline_manifest)
    for name, pin in baseline['files_sha256'].items():
        if name in ('runtime/requirements.txt', 'runtime/nak') or name.startswith('runtime/wheels/'):
            require(sha256((BASELINE/name).read_bytes()).hexdigest() == pin)
    if resume_pin is None:
        require(not RECOVERY.exists() and not (CONFIG/'followup-v3.json').exists()
                and not (RUNTIME/'run-recurring.py').exists() and not (RUNTIME/'verify-runtime.py').exists())
    else:
        require(not (RECOVERY/'qualification.json').exists()
                and sha256((RECOVERY/'data/manifest.json').read_bytes()).hexdigest() == resume_pin
                and sha256((RECOVERY/'credentials.env').read_bytes()).hexdigest() == ENVIRONMENT_PIN
                and cli_snapshot_valid(stage))
    for unit in ('thermal-primal.service', 'thermal-primal.timer'):
        result = subprocess.run(['systemctl', '--user', 'show', unit, '-p', 'ActiveState', '--value'],
                                capture_output=True, text=True, timeout=10)
        require(result.stdout.strip() == 'inactive')
    cli, followup, journal = modules(RUNTIME)
    policy, _, keyer = cli.configuration(current_args(CONFIG/'policy.json', CONFIG/'routes.json'))
    followup.reader_dsn(); cli.check_primal_identity(keyer, policy.recipient)
    journal.V2_WRITE_RELEASE_READY = True
    cli.t.JournalSink().require_v2_storage()  # Read-only exact production schema.
    settings = (dict(version=1, activated_at=cli.t.iso(datetime.now(timezone.utc)),
        bank_epoch='discover_4_module_2026', site_timezone='America/Denver', max_questions_per_day=1)
        if resume_pin is None else cli.t.strict_json(stage.read(CONFIG/'followup-v3.json', private=True)))
    settings = followup.load_configuration(cli.t.canonical(settings), now=cli.utc_now())
    checkpoint('private_metadata_preparation')
    if resume_pin is None:
        stage.write_new(CONFIG/'followup-v3.json', cli.t.canonical(settings)+b'\n')
        stage.write_new(RUNTIME/'verify-runtime.py', (REPO/'scripts/thermal-primal-runtime.py').read_bytes())
        stage.write_new(RUNTIME/'run-recurring.py', (REPO/'scripts/thermal-primal-recurring-release.py').read_bytes())
        RECOVERY.mkdir(mode=0o700)
    else:
        require(stage.read(CONFIG/'followup-v3.json', private=True) == stage.read(RECOVERY/'followup.json', private=True)
                and stage.read(CONFIG/'policy.json', private=True) == stage.read(RECOVERY/'data/policy.json', private=True)
                and stage.read(CONFIG/'routes.json', private=True) == stage.read(RECOVERY/'data/routes.json', private=True))
    # The original qualified authentic-observation recovery point remains intact.
    with cli.b.state_lock(STATE):
        ledger = cli.n.PrimalLedger(STATE)
        try:
            row = ledger.get(TRIAL_EVENT)
            require(row is not None and row['digest'] == TRIAL_CIPHER)
            followup.initialize(ledger.db)
            followup.pin_configuration(ledger.db, settings, policy=policy)
        finally: ledger.close()
    recovery = load('recurring_journal_restore', REPO/'scripts/qualify-thermal-journal-live-restore.py')
    checkpoint('read_only_journal_export')
    with closing(recovery.runtime_connection()[0]) as source:
        from psycopg2.extensions import parse_dsn
        params = parse_dsn(os.environ['THERMAL_DATABASE_URL'])
        with source.cursor() as cursor:
            cursor.execute('SELECT count(*) FROM pg_stat_activity WHERE usename=%s '
                           'AND pid<>pg_backend_pid() AND state<>%s', (params['user'], 'idle'))
            require(cursor.fetchone() == (0,))
            cursor.execute('SELECT pg_export_snapshot()'); snapshot = cursor.fetchone()[0]
        proofs = recovery.table_proofs(source)
        if resume_pin is None:
            cli.b.snapshot_state(STATE, RECOVERY/'data', transport='nip04',
                policy=CONFIG/'policy.json', routes=CONFIG/'routes.json',
                journal_exporter=lambda path:recovery.export_archive(path, params, snapshot))
        source.rollback()
    require(cli.b.verify_snapshot(RECOVERY/'data', transport='nip04')['verified_files'] == 5)
    if resume_pin is None:
        shutil.copytree(RUNTIME, RECOVERY/'runtime')
        for name in ('requirements.txt', 'wheels', 'nak'):
            source = BASELINE/'runtime'/name
            target = RECOVERY/'runtime'/name
            if source.is_dir(): shutil.copytree(source, target)
            else: shutil.copy2(source, target)
        stage.write_new(RECOVERY/'credentials.env', stage.read(ENVIRONMENT, private=True))
        stage.write_new(RECOVERY/'followup.json', stage.read(CONFIG/'followup-v3.json', private=True))
        stage.write_new(RECOVERY/'qualify.py', Path(__file__).read_bytes())
    require(sha256((RECOVERY/'runtime/nak').read_bytes()).hexdigest() == keyer.digest)
    container = 'thermal-recurring-recovery-'+uuid4().hex
    started = False
    try:
        with TemporaryDirectory(prefix='earthship-recurring-cold-') as temporary:
            checkpoint('offline_cold_runtime_rebuild')
            working = Path(temporary)
            for name in ('runtime', 'data'): shutil.copytree(RECOVERY/name, working/name)
            shutil.copy2(RECOVERY/'followup.json', working/'followup.json')
            # Latest verified orchestrator, no overwrite of retained backups.
            stage.write_new(working/'qualify.py', Path(__file__).read_bytes())
            (working/'state').mkdir(mode=0o700)
            for name in cli.b.PRIMAL_DATABASES: shutil.copy2(working/'data'/name, working/'state'/name)
            subprocess.run(['/usr/bin/python3', '-m', 'venv', '--without-pip', str(working/'venv')], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
            subprocess.run(['/usr/bin/python3', '-m', 'pip', '--python', str(working/'venv/bin/python'),
                'install', '--no-index', '--no-compile', '--require-hashes',
                '--find-links', str(working/'runtime/wheels'), '-r', str(working/'runtime/requirements.txt')],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90)
            password = secrets.token_urlsafe(32)
            started = True
            checkpoint('disposable_journal_restore')
            disposable = recovery.disposable_database(container, password, params['user'])
            require(recovery.restore_and_rehearse(working/'data/journal.dump', disposable,
                params['user'], source_schema='v2') == proofs)
            checkpoint('disposable_role_login')
            fixture_password = secrets.token_urlsafe(32)
            with closing(psycopg2.connect(**disposable)) as connection:
                with connection:
                    with connection.cursor() as cursor:
                        cursor.execute(sql.SQL('ALTER ROLE {} LOGIN PASSWORD %s').format(
                            sql.Identifier(params['user'])), (fixture_password,))
            checkpoint('cold_environment_staging')
            values = {name:os.environ[name] for name in stage.FOLLOWUP_ENVIRONMENT_KEYS}
            values['THERMAL_DATABASE_URL'] = psycopg2.extensions.make_dsn(**{
                **disposable, 'user':params['user'], 'password':fixture_password})
            values['THERMAL_DATABASE_EXPECTED_OWNER'] = 'postgres'
            values['EARTHSHIP_PRIMAL_NAK'] = str(working/'runtime/nak')
            stage.write_environment(working/'fixture.env', values)
            checkpoint('isolated_cold_consumer_probe')
            probe = subprocess.run(['systemd-run', '--user', '--wait', '--pipe', '--collect', '--quiet',
                '--property=EnvironmentFile='+str(working/'fixture.env'), '--setenv=PYTHONDONTWRITEBYTECODE=1',
                '--setenv=PYTHONPATH='+str(working/'runtime/code'), '--property=UMask=0077',
                '--property=TimeoutStartSec=120', '--property=TimeoutStopSec=10',
                '--property=KillMode=control-group', '--property=MemoryMax=192M',
                '--property=NoNewPrivileges=true', '--property=RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6',
                str(working/'venv/bin/python'), str(working/'qualify.py'), '--cold-probe', str(working)],
                capture_output=True, text=True, timeout=150)
            if probe.returncode != 0:
                require(False)
            result = json.loads(probe.stdout)
            require(result['status'] == 'cold_probe_passed' and result['relay_publications'] == 0)
            with closing(psycopg2.connect(**disposable)) as connection:
                connection.set_session(readonly=True, isolation_level='REPEATABLE READ')
                require(recovery.table_proofs(connection) == proofs)
        with closing(recovery.runtime_connection()[0]) as source:
            require(recovery.table_proofs(source) == proofs)
    finally:
        if started:
            subprocess.run(['docker', 'rm', '--force', '--volumes', container], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    qualification = dict(version=1, scope='earthship-primal-recurring-recovery/v1', status='passed',
        runtime_manifest_sha256=RUNTIME_PIN, credentials_sha256=ENVIRONMENT_PIN,
        followup_policy_sha256=sha256((RECOVERY/'followup.json').read_bytes()).hexdigest(),
        base_policy_sha256=sha256((RECOVERY/'data/policy.json').read_bytes()).hexdigest(),
        routes_sha256=sha256((RECOVERY/'data/routes.json').read_bytes()).hexdigest(),
        data_snapshot=str(RECOVERY/'data'), data_manifest_sha256=sha256((RECOVERY/'data/manifest.json').read_bytes()).hexdigest(),
        original_trial_event_id=TRIAL_EVENT, cold_runtime_qualified=True, cold_journal_qualified=True,
        cold_state_qualified=True, cleanup_complete=True, controls_enabled=False)
    stage.write_new(RECOVERY/'qualification.json', cli.t.canonical(qualification)+b'\n')
    print(json.dumps(dict(status='recurring_recovery_passed', runtime_manifest_sha256=RUNTIME_PIN,
        qualification_sha256=sha256((RECOVERY/'qualification.json').read_bytes()).hexdigest(),
        data_manifest_sha256=qualification['data_manifest_sha256'], table_proofs=proofs,
        activated_at=settings['activated_at'], controls_enabled=False, collector_activated=False)))


def stage_release():
    """Create the exact private release profile and complete backup, not a service."""
    stage = load('release_stage', REPO/'scripts/thermal-primal-runtime.py')
    stage.verify(RUNTIME, RUNTIME_PIN)
    qualification_path = RECOVERY/'qualification.json'
    require(sha256(stage.read(qualification_path, private=True)).hexdigest() ==
            'c0f014c94ee43c6269d01fbcd57f0afff3f7cfb20cccaf0b53be3c8e8bb75420')
    require(sha256(stage.read(ENVIRONMENT, private=True)).hexdigest() == ENVIRONMENT_PIN)
    cli, _, _ = modules(RUNTIME)
    policy, _, _ = cli.configuration(current_args(CONFIG/'policy.json', CONFIG/'routes.json'))
    profile_path = CONFIG/'recurring-v3-profile.json'
    require(not profile_path.exists() and not (RECOVERY/'bundle-manifest.json').exists())
    paths = dict(launcher=RUNTIME/'run-recurring.py', verifier=RUNTIME/'verify-runtime.py',
        credentials=ENVIRONMENT, followup_policy=CONFIG/'followup-v3.json',
        base_policy=CONFIG/'policy.json', routes=CONFIG/'routes.json', qualification=qualification_path)
    for name, source in (('launcher', REPO/'scripts/thermal-primal-recurring-release.py'),
                         ('verifier', REPO/'scripts/thermal-primal-runtime.py')):
        require(stage.read(paths[name], private=True) == stage.read(source))
    profile = dict(version=1, scope='earthship-primal-recurring-observation/v1',
        runtime=str(RUNTIME), runtime_manifest_sha256=RUNTIME_PIN, state_dir=str(STATE),
        interpreter=sys.executable,
        interpreter_sha256=sha256(Path(sys.executable).resolve().read_bytes()).hexdigest(),
        collector=policy.recipient, operator=next(iter(policy.operators)),
        signer=dict(path=os.environ['EARTHSHIP_PRIMAL_NAK'],
            sha256=os.environ['EARTHSHIP_PRIMAL_NAK_SHA256'],
            version=os.environ['EARTHSHIP_PRIMAL_NAK_VERSION']),
        **{name:dict(path=str(path), sha256=sha256(stage.read(path, private=True)).hexdigest())
           for name, path in paths.items()})
    encoded = cli.t.canonical(profile)+b'\n'
    profile_pin = sha256(encoded).hexdigest()
    release = load('staged_release', paths['launcher'])
    # Byte/profile/closure checks, without opening the collector or its gates.
    stage.write_new(profile_path, encoded)
    release.verify_profile(profile_path, profile_pin)
    stage.write_new(RECOVERY/'profile.json', encoded)
    service = (REPO/'deploy/thermal-primal-recurring.service.in').read_bytes()
    require(service.count(b'@PROFILE_SHA256@') == 1)
    stage.write_new(RECOVERY/'thermal-primal.service', service.replace(b'@PROFILE_SHA256@', profile_pin.encode()))
    stage.write_new(RECOVERY/'thermal-primal.timer', (REPO/'deploy/thermal-primal.timer').read_bytes())
    # Retain the exact orchestrator that finally passed, not only its first draft.
    stage.write_new(RECOVERY/'qualified-orchestrator.py', Path(__file__).read_bytes())
    mapping = dict(profile=str(profile_path), followup_policy=str(CONFIG/'followup-v3.json'),
        credentials=str(ENVIRONMENT), base_policy=str(CONFIG/'policy.json'),
        routes=str(CONFIG/'routes.json'), state_dir=str(STATE), runtime=str(RUNTIME),
        recovery=str(RECOVERY), interpreter=sys.executable,
        unit_dir='/home/sat/.config/systemd/user')
    files = {str(path.relative_to(RECOVERY)):sha256(path.read_bytes()).hexdigest()
             for path in sorted(RECOVERY.rglob('*')) if path.is_file()}
    manifest = dict(version=1, scope='earthship-primal-recurring-bundle/v1',
        profile_sha256=profile_pin, files_sha256=files, restore_paths=mapping,
        cold_recovery_qualification_sha256=profile['qualification']['sha256'],
        controls_enabled=False, off_host_backup_deferred=True)
    stage.write_new(RECOVERY/'bundle-manifest.json', cli.t.canonical(manifest)+b'\n')
    require(all(sha256((RECOVERY/name).read_bytes()).hexdigest() == pin for name,pin in files.items()))
    print(json.dumps(dict(status='release_staged', profile_sha256=profile_pin,
        bundle_manifest_sha256=sha256((RECOVERY/'bundle-manifest.json').read_bytes()).hexdigest(),
        bundle_files=len(files), collector_activated=False, controls_enabled=False)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare-and-rehearse', action='store_true')
    mode.add_argument('--cold-probe', type=Path)
    mode.add_argument('--rehearse-existing', metavar='DATA_MANIFEST_SHA256')
    mode.add_argument('--stage-release', action='store_true')
    args = parser.parse_args()
    try:
        if args.stage_release: stage_release()
        elif args.cold_probe is not None: cold_probe(args.cold_probe)
        else: prepare_and_rehearse(args.rehearse_existing)
        return 0
    except Exception as error:
        print('recurring recovery incomplete at '+STEP+' ['+type(error).__name__+']; retain backups and inspect before retrying', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
