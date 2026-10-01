from datetime import datetime, timedelta, timezone
import gzip
from hashlib import sha256
import os

import pytest

import forecast_input_capture as capture


AT = datetime(2026, 10, 1, 12, 40, tzinfo=timezone.utc)
URL = 'https://api.open-meteo.com/v1/forecast?latitude=38&longitude=-105&forecast_days=10'


@pytest.fixture
def root(tmp_path):
    directory = tmp_path / 'weather-inputs'
    directory.mkdir(mode=0o700)
    return directory


def snapshot():
    return {'daily': {'shortwave_radiation_sum': [4.9], 'cloud_cover_mean': [71]},
            'hourly': {'temperature_2m': [61.2, None], 'shortwave_radiation': [0, 27]},
            'hourly_units': {'temperature_2m': '°F', 'shortwave_radiation': 'W/m²'}}


def store(root, **kwargs):
    return capture.capture(root, snapshot=kwargs.get('snapshot', snapshot()),
                           request_url=kwargs.get('request_url', URL),
                           captured_at=kwargs.get('captured_at', AT))


def test_exact_raw_input_round_trip_and_idempotence(root):
    raw = snapshot()
    reference = store(root, snapshot=raw)
    record = capture.read_as_of(root, reference, origin=AT)
    assert record['snapshot'] == raw
    assert record['requestUrl'] == URL
    assert store(root, snapshot=raw) == reference
    raw['daily']['cloud_cover_mean'][0] = 0
    assert capture.read_as_of(root, reference, origin=AT)['snapshot']['daily']['cloud_cover_mean'] == [71]
    assert os.stat(root / reference['path']).st_mode & 0o777 == 0o600
    assert len(list(root.rglob('*.json.gz'))) == 1
    assert not list(root.rglob('*.tmp'))


def test_later_revision_cannot_replace_origin_inputs(root):
    first = store(root)
    later = store(root, captured_at=AT + timedelta(hours=2))
    assert later['path'] != first['path']
    with pytest.raises(ValueError, match='unavailable'):
        capture.read_as_of(root, later, origin=AT)
    assert capture.read_as_of(root, first, origin=AT)['snapshot'] == snapshot()


@pytest.mark.parametrize('damage', ['future', 'naive', 'path', 'digest', 'month', 'timestamp', 'version'])
def test_reference_faults_are_not_learning_inputs(root, damage):
    reference = store(root)
    origin = AT
    if damage == 'future': origin -= timedelta(microseconds=1)
    elif damage == 'naive': origin = AT.replace(tzinfo=None)
    elif damage == 'path': reference['path'] = '../' + reference['path']
    elif damage == 'digest': reference['sha256'] = '0' * 64
    elif damage == 'month': reference['capturedAt'] = AT.replace(month=9).isoformat()
    elif damage == 'timestamp': reference['capturedAt'] = AT.replace(minute=39).isoformat()
    elif damage == 'version': reference['version'] = True
    with pytest.raises(ValueError):
        capture.read_as_of(root, reference, origin=origin)


@pytest.mark.parametrize('damage', ['root-mode', 'root-link', 'month-link', 'file-link', 'file-mode', 'corrupt'])
def test_private_archive_safety_and_integrity(root, tmp_path, damage):
    reference = store(root)
    path = root / reference['path']
    read_root = root
    if damage == 'root-mode': root.chmod(0o755)
    elif damage == 'root-link':
        read_root = tmp_path / 'link'
        read_root.symlink_to(root)
    elif damage == 'month-link':
        month = path.parent
        relocated = root / 'elsewhere'
        month.rename(relocated)
        month.symlink_to(relocated)
    elif damage == 'file-link':
        path.unlink()
        path.symlink_to(tmp_path / 'missing')
    elif damage == 'file-mode': path.chmod(0o644)
    elif damage == 'corrupt': path.write_bytes(b'not gzip')
    with pytest.raises((ValueError, OSError, EOFError)):
        capture.read_as_of(read_root, reference, origin=AT)


def test_corrupt_collision_is_never_overwritten(root):
    reference = store(root)
    path = root / reference['path']
    path.write_bytes(b'original corrupt evidence')
    with pytest.raises(ValueError, match='different content'):
        store(root)
    assert path.read_bytes() == b'original corrupt evidence'
    assert not list(root.rglob('*.tmp'))


@pytest.mark.parametrize('damage', ['nan', 'oversize', 'no-hourly', 'naive', 'secret-url'])
def test_invalid_capture_fails_before_creating_archive(root, damage):
    raw = snapshot()
    kwargs = {'snapshot': raw}
    if damage == 'nan': raw['daily']['bad'] = float('nan')
    elif damage == 'oversize': raw['extra'] = 'x' * capture.MAX_RAW_BYTES
    elif damage == 'no-hourly': del raw['hourly']
    elif damage == 'naive': kwargs['captured_at'] = AT.replace(tzinfo=None)
    elif damage == 'secret-url': kwargs['request_url'] = 'https://secret@api.open-meteo.com/v1/forecast?q=1'
    with pytest.raises(ValueError): store(root, **kwargs)
    assert not list(root.iterdir())


def test_decoded_gzip_bomb_is_bounded(root):
    raw = b'x' * (capture.MAX_RAW_BYTES + 1)
    digest = sha256(raw).hexdigest()
    month = root / '2026-10'
    month.mkdir(mode=0o700)
    path = month / (digest + '.json.gz')
    path.write_bytes(gzip.compress(raw, mtime=0))
    path.chmod(0o600)
    reference = {'version': 1, 'sha256': digest, 'capturedAt': AT.isoformat(),
                 'path': str(path.relative_to(root))}
    with pytest.raises(ValueError, match='size mismatch'):
        capture.read_as_of(root, reference, origin=AT)
