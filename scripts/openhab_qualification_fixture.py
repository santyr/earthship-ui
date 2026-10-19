"""Provider-neutral adapters for existing disposable OpenHAB qualification tools.

Importing does not restore data, start a container, or access production.
"""
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'openhab/scripts'))
import openhab_sanity_check as oh

SNAPSHOT = Path('/home/sat/backups/earthship-energy/runtime-recovery-1x76m17d')
IMAGE = 'openhab/openhab@sha256:bfd4a60e90da18cf917a9004bbc22354fc818825f3c6f0351e471a2e938d6c3c'


def run(args, data=None, *, check=True, timeout=45):
    result = subprocess.run(args, input=data, capture_output=True, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError('isolated command failed: ' + args[0] + ' ' + args[1])
    return result


def install_bytes(container, directory, name, body, *, mode=0o644):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w') as archive:
        member = tarfile.TarInfo(name)
        member.size = len(body)
        member.mode = mode
        archive.addfile(member, io.BytesIO(body))
    run(['docker', 'exec', '-i', container, 'tar', '--no-same-owner',
         '--no-same-permissions', '-xf', '-', '-C', directory], output.getvalue())


def restore(container, scope):
    with (SNAPSHOT / (scope + '.tar')).open('rb') as archive:
        result = subprocess.run(['docker', 'exec', '-i', container, 'tar',
                                 '--no-same-owner', '--no-same-permissions', '-xf',
                                 '-', '-C', '/openhab/' + scope], stdin=archive,
                                capture_output=True, timeout=110)
    if result.returncode:
        raise RuntimeError('isolated restore failed: ' + scope)


def snapshot_registry(name):
    with tarfile.open(SNAPSHOT / 'userdata.tar') as archive:
        member = archive.extractfile('./jsondb/' + name)
        if member is None:
            raise RuntimeError('snapshot registry missing')
        return json.loads(member.read())


def isolated_get(container, path, header):
    result = run(['docker', 'exec', '-i', container, 'curl', '-sS', '--max-time', '7',
                  '-w', '\nCODE:%{http_code}', '-H', '@-',
                  'http://127.0.0.1:8080/rest' + path], header,
                 check=False, timeout=11)
    body = result.stdout.decode(errors='replace')
    if '\nCODE:' not in body:
        return None, None
    body, code = body.rsplit('\nCODE:', 1)
    if code.strip() == '404':
        return 404, None
    if code.strip() != '200':
        return code.strip(), None
    try:
        return 200, json.loads(body)
    except ValueError:
        return None, None


def managed_item_dto(original):
    required = ('name', 'type', 'label')
    if any(field not in original for field in required):
        raise ValueError('managed Item identity is incomplete')
    optional = ('category', 'tags', 'groupNames')
    return {field: original[field] for field in (*required, *optional) if field in original}
