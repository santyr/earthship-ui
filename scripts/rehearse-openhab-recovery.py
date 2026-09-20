#!/usr/bin/env python3
"""Attended, private, networkless OpenHAB recovery test. Never deploys to production.

Uses the already verified database recovery point; captures current runtime files.
Those two recovery times are explicitly NOT an atomic whole-system snapshot.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid

ROOT = Path('/home/sat/backups/earthship-energy')
DATABASE = ROOT / 'full-restore-0lnrkogj'
IMAGE = 'openhab/openhab@sha256:bfd4a60e90da18cf917a9004bbc22354fc818825f3c6f0351e471a2e938d6c3c'
PATCH = '/home/sat/.codex/tmp/arg0/codex-arg0eauJfY/apply_patch'


def archive_fingerprints(path):
    result = {}
    with tarfile.open(path) as archive:
        for member in archive:
            if member.isfile():
                stream = archive.extractfile(member)
                if member.sparse is not None:
                    # Hash nonzero blocks without expanding the LMDB holes.
                    h = hashlib.sha256()
                    for offset, length in member.sparse:
                        stream.seek(offset)
                        for position in range(offset, offset + length, 512):
                            data = stream.read(min(512, offset + length - position))
                            if any(data):
                                h.update(position.to_bytes(8, 'big'))
                                h.update(data)
                    digest = h.hexdigest()
                else:
                    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
                result[member.name.removeprefix('./')] = [member.size, digest]
            elif member.issym() or member.islnk():
                result[member.name.removeprefix('./')] = ['link', member.linkname]
    return result


def main():
    os.umask(0o077)
    if shutil.disk_usage(ROOT).free < 40 * 1024**3:
        raise RuntimeError('40 GiB free disk space required')
    dest = Path(tempfile.mkdtemp(prefix='runtime-recovery-', dir=ROOT))
    print('private_receipt=' + str(dest), flush=True)
    log = (dest / 'commands.log').open('xb')
    containers = []
    marker = uuid.uuid4().hex
    report = {'status': 'incomplete', 'database_recovery_point': str(DATABASE),
              'atomic_system_snapshot': False, 'integrated_jdbc_boot_verified': False,
              'hardware_validation': False, 'external_services_restored': False,
              'omitted_rebuildable_userdata': ['tmp', 'cache', '.cache', 'backups', '*.log'],
              'runtime_uid_gid_remapped': '9001:9001'}

    def run(args, data=None, stdin=None, timeout=7200):
        p = subprocess.run(args, input=data, stdin=stdin, stdout=subprocess.PIPE,
                           stderr=log, timeout=timeout)
        if p.returncode:
            raise RuntimeError('private command failed: ' + args[0])
        return p.stdout

    def save(name, value):
        body = json.dumps(value, indent=2, sort_keys=True)
        patch = '*** Begin Patch\n*** Add File: ' + str(dest / name) + '\n'
        patch += ''.join('+' + line + '\n' for line in body.splitlines()) + '*** End Patch\n'
        run([PATCH], data=patch.encode())

    def container(args):
        cid = run(['docker', 'run', '-d', '--label', 'hex.recovery=' + marker,
                   '--network', 'none', '--cpus', '1', *args]).decode().strip()
        if not re.fullmatch('[a-f0-9]{64}', cid):
            raise RuntimeError('bad container identity')
        containers.append(cid)
        inspection = json.loads(run(['docker', 'inspect', cid]))[0]
        host = inspection['HostConfig']
        if (host['NetworkMode'] != 'none' or host['Privileged'] or host.get('Devices')
                or host.get('Binds') or host.get('PortBindings')):
            raise RuntimeError('container isolation verification failed')
        return cid

    def query(cid, sql, db='openhab'):
        return run(['docker', 'exec', '-i', cid, 'psql', '-X', '-q', '-At',
                    '-U', 'postgres', '-d', db, '-v', 'ON_ERROR_STOP=1'],
                   data=sql.encode()).decode().strip()

    pid = run(['systemctl', 'show', 'openhab', '-p', 'MainPID']).decode().strip()
    try:
        # Retain credentials only inside this private archive, never console/Git.
        scopes = [('conf', '/etc/openhab', []),
                  ('userdata', '/var/lib/openhab', ['tmp', 'cache', '.cache', 'backups', '*.log']),
                  ('addons', '/usr/share/openhab/addons', [])]
        for name, path, excludes in scopes:
            archive = dest / (name + '.tar')
            run(['sudo', '-n', 'tar', '--sparse', '-cf', str(archive),
                 *['--exclude=./' + x for x in excludes], '-C', path, '.'])
            run(['sudo', '-n', 'chown', str(os.getuid()) + ':' + str(os.getgid()), str(archive)])
            archive.chmod(0o600)
        print('durable_runtime_archives_captured=true', flush=True)
        report['runtime_archive_sha256'] = {}
        for name, _, _ in scopes:
            with (dest / (name + '.tar')).open('rb') as f:
                report['runtime_archive_sha256'][name] = hashlib.file_digest(f, 'sha256').hexdigest()
        db_manifest = json.loads((DATABASE / 'backup-manifest.json').read_text())
        with (DATABASE / 'openhab.dump').open('rb') as f:
            if hashlib.file_digest(f, 'sha256').hexdigest() != db_manifest['archive_sha256']:
                raise RuntimeError('database archive hash mismatch')
        roles = run(['sudo', '-n', '-u', 'postgres', 'pg_dumpall', '--roles-only'])
        # The bootstrap role already exists. Preserve its ALTER/attributes/password.
        roles = roles.replace(b'CREATE ROLE postgres;', b'-- bootstrap role already exists')
        save('roles-private.json', {'sql': roles.decode()})
        pg = container(['--memory', '1536m', '--memory-swap', '1536m',
                        '-e', 'POSTGRES_HOST_AUTH_METHOD=trust', 'postgres:16'])
        for _ in range(60):
            p = subprocess.run(['docker', 'exec', pg, 'pg_isready', '-U', 'postgres'],
                               stdout=subprocess.DEVNULL, stderr=log)
            if p.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError('database startup timeout')
        query(pg, roles.decode(), 'postgres')
        with (DATABASE / 'openhab.dump').open('rb') as f:
            run(['docker', 'exec', '-i', pg, 'pg_restore', '--exit-on-error',
                 '--create', '-U', 'postgres', '-d', 'postgres'], stdin=f)
        print('database_restored_with_owners_and_acls=true', flush=True)
        spec = importlib.util.spec_from_file_location('backup', Path(__file__).with_name('verify-openhab-full-backup.py'))
        backup = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(backup)
        expected = db_manifest['fingerprints']
        actual = query(pg, "SELECT schemaname||'.'||tablename FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema') ORDER BY 1;").splitlines()
        if actual != sorted(expected):
            raise RuntimeError('database table inventory mismatch')
        for n, (table, fingerprint) in enumerate(expected.items()):
            schema, name = table.split('.')
            sql = "SET timezone='UTC'; SET statement_timeout='300s'; SET work_mem='16MB'; " + backup.fingerprint_query(schema, name)
            if query(pg, sql).split('|') != fingerprint:
                raise RuntimeError('database row fingerprint mismatch')
            if n % 50 == 0:
                print('database_tables_verified=' + str(n + 1), flush=True)
        report['database_tables_verified'] = len(expected)
        report['database_restore_with_owners_acls'] = True
        # Keep database immutable during runtime boot; no network attachment to it.
        # This pass deliberately tests runtime independently, not live JDBC service.
        oh = container(['--hostname', 'localhost', '--read-only', '--user', '9001:9001',
                        '--cap-drop', 'ALL', '--pids-limit', '384', '--memory', '3g',
                        '--tmpfs', '/tmp:rw,nosuid,nodev,size=128m,uid=9001,gid=9001',
                        '--tmpfs', '/openhab/conf:rw,size=64m,uid=9001,gid=9001',
                        '--tmpfs', '/openhab/userdata:rw,size=512m,uid=9001,gid=9001',
                        '--tmpfs', '/openhab/addons:rw,size=800m,uid=9001,gid=9001',
                        '-e', 'EXTRA_JAVA_OPTS=-Xmx768m -Duser.timezone=America/Denver -Duser.home=/openhab/userdata',
                        '--entrypoint', '/bin/sh', IMAGE, '-c',
                        'while [ ! -f /tmp/ready ]; do sleep 1; done; exec /openhab/start.sh server'])
        save('containers.json', {'ids': containers, 'marker': marker})
        for name, _, _ in scopes:
            archive = dest / (name + '.tar')
            with archive.open('rb') as f:
                run(['docker', 'exec', '-i', oh, 'tar', '--no-same-owner', '--no-same-permissions',
                     '-xf', '-', '-C', '/openhab/' + name], stdin=f)
            expected_files = archive_fingerprints(archive)
            restored_archive = dest / ('restored-' + name + '.tar')
            with restored_archive.open('xb') as output:
                p = subprocess.run(['docker', 'exec', oh, 'tar', '--sparse', '-cf', '-',
                                    '-C', '/openhab/' + name, '.'], stdout=output, stderr=log)
            if p.returncode:
                raise RuntimeError('restored archive capture failed')
            actual_files = archive_fingerprints(restored_archive)
            if expected_files != actual_files:
                raise RuntimeError('runtime file hash mismatch: ' + name)
            restored_archive.unlink()
            report[name + '_files_verified'] = len(expected_files)
        print('all_runtime_files_restored_byte_exact=true', flush=True)
        label = run(['docker', 'inspect', '--format', '{{index .Config.Labels "hex.recovery"}}', oh]).decode().strip()
        if label != marker:
            raise RuntimeError('file-verifier ownership mismatch')
        run(['docker', 'rm', '-f', '-v', oh])
        containers.remove(oh)
        # Content verification is complete; startup writes can now use this same
        # disposable database. No extra database clone or redundant boot needed.
        runtime = run([sys.executable, str(Path(__file__).with_name('rehearse-openhab-runtime.py')),
                       str(dest), pg, '--allow-isolated-writes']).decode().splitlines()
        report['integrated_runtime'] = json.loads(runtime[-1])
        report['integrated_jdbc_boot_verified'] = report['integrated_runtime']['status'] == 'integrated_boot_tested'
        report['production_pid_unchanged'] = run(['systemctl', 'show', 'openhab', '-p', 'MainPID']).decode().strip() == pid
        report['status'] = 'component_restore_tested' if report['integrated_jdbc_boot_verified'] else 'runtime_boot_failed'
    except Exception as exc:
        report['status'] = 'failed'
        report['error_type'] = type(exc).__name__
        raise
    finally:
        for cid in reversed(containers):
            label = run(['docker', 'inspect', '--format', '{{index .Config.Labels "hex.recovery"}}', cid]).decode().strip()
            if label != marker:
                raise RuntimeError('cleanup ownership mismatch')
            run(['docker', 'rm', '-f', '-v', cid])
        report['owned_containers_and_volumes_removed'] = True
        save('recovery-report.json', report)
        log.close()
        print(json.dumps(report, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
