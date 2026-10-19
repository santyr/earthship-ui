"""Generic container/JDBC REST adapters, with no forecast or AQI candidates.

These preserve existing qualification-tool APIs; no new recovery work is run.
"""
import importlib.util
import io
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'isolated_jdbc', ROOT / 'scripts/qualify-persistence-jdbc.py')
isolated = importlib.util.module_from_spec(spec)
spec.loader.exec_module(isolated)
Database = isolated.Database
run = isolated.run
IMAGE = isolated.provider.isolated.IMAGE


def install(container, name, body):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w') as archive:
        member = tarfile.TarInfo(name)
        member.mode = 0o644
        member.size = len(body)
        archive.addfile(member, io.BytesIO(body))
    run(['docker', 'exec', '-i', container, 'tar', '-xf', '-', '-C', '/openhab/conf'],
        output.getvalue())


def request(container, header, path, method='GET', body=None, content_type='text/plain'):
    command = ['docker', 'exec', '-i', container, 'curl', '-sS', '--max-time', '6',
               '-X', method, '-H', '@-', '-w', '\n%{http_code}',
               'http://127.0.0.1:8080/rest' + path]
    if body is not None:
        command += ['-H', 'Content-Type: ' + content_type, '--data-binary', body]
    result = run(command, header).decode()
    payload, code = result.rsplit('\n', 1)
    return int(code), payload
