"""Labeled synthetic original-query fixtures; no household/private observations."""
from dataclasses import FrozenInstanceError, asdict
from datetime import datetime, timedelta, timezone
import gzip
from hashlib import sha256
import importlib
import importlib.util
import json
from pathlib import Path
import stat

import pytest

from weather_source_files import _canonical
from weather_temperature_evidence import MODELS, TemperaturePolicy
from weather_temperature_reader import select_temperature_grid_v2
import weather_temperature_sources as legacy
from test_weather_temperature_history import Connection

AT = datetime(2026, 1, 1, 0, 0, 0, 123456, tzinfo=timezone.utc)
SESSION = '12111111-1111-4111-8111-111111111111'
RESET = '13111111-1111-4111-8111-111111111111'
EPOCHS = {role: f'{index}2111111-1111-4111-8111-111111111111'
          for index, role in enumerate(('air', 'mass', 'outdoor'), 1)}


def module():
    assert importlib.util.find_spec('weather_temperature_source_segments') is not None, \
        'missing bounded lossless shared temperature source'
    return importlib.import_module('weather_temperature_source_segments')


def contexts():
    return {role: dict(stream=stream, policy=TemperaturePolicy(model, index, -100, 180, 120),
                       sensor_epoch=EPOCHS[role])
            for index, (role, stream, model) in enumerate((
                ('air', 'indoor', 'Fineoffset-WH32B'),
                ('mass', 'bedroom', 'AmbientWeather-WH31E'),
                ('outdoor', 'outdoor', 'Fineoffset-WH65B')), 1)}


def envelope(at, *, received=None, session=SESSION, padding='', damage=None):
    received = at if received is None else received
    records = {}
    for role, context in contexts().items():
        policy = context['policy']
        records[context['stream']] = dict(version=2, streamEpoch=session,
            recordedAt=received.isoformat(), receivedAt=received.isoformat(),
            validUntil=(received + timedelta(seconds=120)).isoformat(), model=policy.model,
            sensorId=policy.sensor_id, field=MODELS[policy.model][1], status='valid',
            reason='accepted', temperatureF=60 + policy.sensor_id,
            sensorEpoch=context['sensor_epoch'])
    if padding:
        records['synthetic_label'] = padding
    document = dict(version=2, streamEpoch=session, records=records)
    if damage:
        damage(document)
    return json.dumps(document, ensure_ascii=False, separators=(',', ':'))


def request(rows, targets=None):
    targets = targets or [rows[0][0], rows[-1][0]]
    if len(targets) == 2 and targets[0] == targets[1]:
        targets = targets[:1]
    return dict(rows=rows, targets=targets, assessed_at=targets[-1], contexts=contexts())


def oracle(args):
    return {role: select_temperature_grid_v2(args['rows'], targets=args['targets'],
        assessed_at=args['assessed_at'],
        history_start=args['targets'][0] - timedelta(seconds=120), **context)
        for role, context in args['contexts'].items()}


def retain(m, root, source):
    root.mkdir(mode=0o700)
    path = m.write_shared_temperature_source(root, source)
    return path, m.read_shared_temperature_source(root, path)


def documents(root, path):
    manifest = json.loads(path.read_bytes())
    parts = [json.loads(gzip.decompress((root / descriptor['name']).read_bytes()))
             for descriptor in manifest['segments']]
    return manifest, parts


def republish_manifest(root, manifest, *, account=False):
    if account:
        # Independent wire accounting, including this manifest's own decimal widths.
        for _ in range(8):
            size = len(_canonical(manifest))
            decoded = size + sum(d['decoded_bytes'] for d in manifest['segments'])
            stored = size + sum(d['stored_bytes'] for d in manifest['segments'])
            if (decoded, stored) == (manifest['decoded_bytes'], manifest['stored_bytes']):
                break
            manifest.update(decoded_bytes=decoded, stored_bytes=stored)
    raw = _canonical(manifest)
    path = root / (sha256(raw).hexdigest() + '.native-temperature-shared-v1.json')
    path.write_bytes(raw)
    path.chmod(0o600)
    return path


@pytest.mark.parametrize('kind', ['raw_day', 'canonical_only', 'three_role_aggregate'])
def test_synthetic_dense_queries_cross_old_bounds_and_preserve_every_field(tmp_path, kind):
    # Removing shared segmentation or repeating the query for each role breaks this.
    count = 1200 if kind == 'three_role_aggregate' else 1500
    rows = []
    for index in range(count):
        at = AT + timedelta(seconds=16 * index)
        raw = envelope(at, padding='\\' * 1600 if kind == 'canonical_only' else '')
        if kind != 'canonical_only':
            raw += ' ' * ((6650 if kind == 'three_role_aggregate' else 7000) - len(raw.encode()))
        rows.append((at, raw))
    args = request(rows)
    raw_bytes = sum(len(raw.encode()) for _, raw in rows)
    packets = []
    for context in args['contexts'].values():
        old_args = {key: value for key, value in args.items() if key != 'contexts'} | context
        if kind == 'three_role_aggregate':
            packets.append(legacy.build_temperature_source(**old_args))
        else:
            with pytest.raises(ValueError):
                legacy.build_temperature_source(**old_args)
    if kind == 'raw_day':
        assert raw_bytes > 8388608
    elif kind == 'canonical_only':
        assert raw_bytes < 8388608
    else:
        assert all(len(_canonical(packet)) <= 8388608 for packet in packets)
        assert sum(len(_canonical(packet)) for packet in packets) > 24000000
    expected = oracle(args)
    m = module()
    source = m.build_shared_temperature_source(**args)
    path, retained = retain(m, tmp_path / kind, source)
    assert m.replay_shared_temperature_source(source) == expected
    assert m.replay_shared_temperature_source(retained) == expected
    manifest, parts = documents(path.parent, path)
    assert manifest['row_count'] == count and manifest['raw_bytes'] == raw_bytes
    assert manifest['decoded_bytes'] == len(path.read_bytes()) + sum(
        len(gzip.decompress((path.parent / d['name']).read_bytes())) for d in manifest['segments'])
    assert manifest['stored_bytes'] == sum(p.stat().st_size for p in m.shared_temperature_source_files(retained))
    assert manifest['decoded_bytes'] <= 24000000 and manifest['stored_bytes'] <= 24000000
    assert [row for part in parts for row in part['native_rows']] == [
        [at.isoformat(), raw] for at, raw in rows]
    assert len(parts) >= (1 if kind == 'three_role_aggregate' else 2)
    assert m.write_shared_temperature_source(path.parent, source) == path
    for reader in (legacy.read_temperature_source, legacy.read_compressed_temperature_source):
        with pytest.raises(ValueError):
            reader(path.parent, path)


def test_ten_thousand_original_rows_full_grid_and_shared_decode(tmp_path, monkeypatch):
    m = module()
    rows = [(AT + timedelta(seconds=index * 8), envelope(AT + timedelta(seconds=index * 8)))
            for index in range(10000)]
    targets = [AT + timedelta(microseconds=(79992 * 1000000 * index) // 288)
               for index in range(289)]
    args = request(rows, targets)
    expected = oracle(args)
    source = m.build_shared_temperature_source(**args)
    path, retained = retain(m, tmp_path / 'ten-thousand', source)
    original_loads = m.json.loads
    decoded = 0
    def count_loads(raw, *a, **kw):
        nonlocal decoded
        if isinstance(raw, str) and raw.startswith('{"version":2,"streamEpoch":'):
            decoded += 1
        return original_loads(raw, *a, **kw)
    monkeypatch.setattr(m.json, 'loads', count_loads)
    assert m.replay_shared_temperature_source(retained) == expected
    assert decoded == 10000
    assert len(m.shared_temperature_source_files(retained)) >= 3


def test_moving_copied_barrier_chain_crosses_real_segments(tmp_path):
    m = module()
    rows = [(AT, envelope(AT) + ' ' * 5000), (AT + timedelta(seconds=1), None)]
    for index in range(2, 1900):
        at = AT + timedelta(seconds=index * 2)
        raw = envelope(at, received=at - timedelta(seconds=3))
        rows.append((at, raw + ' ' * (8192 - len(raw.encode()))))
    args = request(rows, [AT, AT + timedelta(seconds=1800), rows[-1][0]])
    expected = oracle(args)
    assert all([value is None for _, value in grid] == [False, True, True]
               for grid in expected.values())
    path, retained = retain(m, tmp_path / 'moving-barrier', m.build_shared_temperature_source(**args))
    assert len(json.loads(path.read_bytes())['segments']) >= 2
    assert m.replay_shared_temperature_source(retained) == expected


@pytest.mark.parametrize('damage', ['null', 'malformed', 'missing_role', 'wrong_epoch',
    'missing_epoch', 'wrong_identity', 'malformed_role', 'reset_copy', 'backwards',
    'conflicting_receipt', 'duplicate_key', 'invalid_status', 'future', 'bad_expiry'])
def test_independent_full_field_barriers_and_recovery(damage):
    m = module()
    at = AT + timedelta(seconds=10)
    corruptions = {
        'missing_role': lambda d: d['records'].pop('indoor'),
        'wrong_epoch': lambda d: d['records']['indoor'].update(sensorEpoch=EPOCHS['mass']),
        'missing_epoch': lambda d: d['records']['indoor'].pop('sensorEpoch'),
        'wrong_identity': lambda d: d['records']['indoor'].update(sensorId=99),
        'malformed_role': lambda d: d['records'].update(indoor=[]),
        'invalid_status': lambda d: d['records']['indoor'].update(status='invalid', reason='☃ label'),
        'future': lambda d: d['records']['indoor'].update(recordedAt=(at + timedelta(seconds=1)).isoformat()),
        'bad_expiry': lambda d: d['records']['indoor'].update(validUntil=(at + timedelta(seconds=121)).isoformat()),
        'conflicting_receipt': lambda d: d['records']['indoor'].update(temperatureF=99),
    }
    raw = envelope(at, received=AT if damage in ('reset_copy', 'conflicting_receipt') else
        AT - timedelta(seconds=1) if damage == 'backwards' else at,
        session=RESET if damage == 'reset_copy' else SESSION, damage=corruptions.get(damage))
    if damage == 'null': raw = None
    if damage == 'malformed': raw = '{synthetic malformed ☃'
    if damage == 'duplicate_key': raw = raw[:-1] + ',"version":2}'
    rows = [(AT, envelope(AT)), (at, raw), (at + timedelta(seconds=1), envelope(at, received=at)),
            (at + timedelta(seconds=2), envelope(at + timedelta(seconds=2), padding='é☃'))]
    args = request(rows, [AT, at, at + timedelta(seconds=1), at + timedelta(seconds=2), at + timedelta(seconds=122)])
    assert m.replay_shared_temperature_source(m.build_shared_temperature_source(**args)) == oracle(args)


def test_carry_exact_target_expiry_microseconds_and_equal_duplicates():
    m = module()
    carry = AT - timedelta(seconds=121)
    rows = [(carry, envelope(carry)), (AT, envelope(AT)), (AT, envelope(AT))]
    args = request(rows, [AT, AT + timedelta(seconds=120) - timedelta(microseconds=1), AT + timedelta(seconds=120)])
    result = m.replay_shared_temperature_source(m.build_shared_temperature_source(**args))
    assert result == oracle(args)
    assert all([value is None for _, value in grid] == [False, False, True] for grid in result.values())


@pytest.mark.parametrize('damage', ['row_plus_one', 'raw_row_plus_one', 'target_plus_one',
    'day_plus_one', 'carry_plus_one', 'future_row', 'conflicting_duplicate', 'unordered',
    'role_missing', 'role_extra', 'policy_ttl', 'bad_epoch'])
def test_global_input_bounds_and_context_refuse_before_connecting(damage):
    m = module()
    args = request([(AT, envelope(AT))])
    if damage == 'row_plus_one': args['rows'] *= 10001
    if damage == 'raw_row_plus_one': args['rows'] = [(AT, 'x' * 8193)]
    if damage == 'target_plus_one': args['targets'] = [AT + timedelta(seconds=i) for i in range(290)]
    if damage == 'day_plus_one': args['targets'].append(AT + timedelta(days=1, microseconds=1))
    if damage == 'carry_plus_one': args['rows'] = [(AT - timedelta(seconds=122), None), (AT - timedelta(seconds=121), None)]
    if damage == 'future_row': args['rows'] = [(AT + timedelta(microseconds=1), None)]
    if damage == 'conflicting_duplicate': args['rows'].append((AT, None))
    if damage == 'unordered': args['rows'].append((AT - timedelta(seconds=1), None))
    if damage == 'role_missing': args['contexts'].pop('air')
    if damage == 'role_extra': args['contexts']['extra'] = args['contexts']['air']
    if damage == 'policy_ttl': args['contexts']['air']['policy'] = TemperaturePolicy('Fineoffset-WH32B', 1, -100, 180, 121)
    if damage == 'bad_epoch': args['contexts']['air']['sensor_epoch'] = 'bad'
    args['assessed_at'] = args['targets'][-1]
    with pytest.raises(ValueError): m.build_shared_temperature_source(**args)
    if damage in ('target_plus_one', 'day_plus_one', 'role_missing', 'role_extra', 'policy_ttl', 'bad_epoch'):
        args.pop('rows')
        with pytest.raises(ValueError):
            m.fetch_shared_temperature_source(lambda: pytest.fail('invalid context connected'), **args)


def test_one_stable_read_only_snapshot_freezes_context_and_deadline():
    m = module()
    args = request([(AT, envelope(AT))])
    expected = oracle(args)
    connection = Connection(rows=args.pop('rows'))
    opened = []
    ticks = []
    def connect():
        opened.append(True)
        args['contexts']['air']['sensor_epoch'] = EPOCHS['mass']
        args['targets'].append(AT - timedelta(seconds=1))
        return connection
    def remaining():
        ticks.append(True)
        return 1.5
    source = m.fetch_shared_temperature_source(connect, remaining_timeout=remaining, **args)
    assert m.replay_shared_temperature_source(source) == expected
    assert len(opened) == 1 and connection.closed and len(ticks) > 2
    assert connection.session == dict(readonly=True, autocommit=False, isolation_level='REPEATABLE READ')
    assert sum('ORDER BY time LIMIT 10001' in query for query, _ in connection.calls) == 1
    assert all(query.startswith(('SET LOCAL', 'SHOW ', 'SELECT ')) for query, _ in connection.calls)


def test_deep_immutable_handle_and_complete_retained_inventory(tmp_path):
    m = module()
    args = request([(AT, envelope(AT))])
    source = m.build_shared_temperature_source(**args)
    expected = oracle(args)
    with pytest.raises(ValueError): m.shared_temperature_source_files(source)
    with pytest.raises((FrozenInstanceError, AttributeError)): source.manifest_bytes = b'{}'
    args['rows'].clear()
    args['contexts'].clear()
    assert m.replay_shared_temperature_source(source) == expected
    path, retained = retain(m, tmp_path / 'inventory', source)
    manifest, _ = documents(path.parent, path)
    assert m.shared_temperature_source_files(retained) == (path,) + tuple(path.parent / d['name'] for d in manifest['segments'])
    assert manifest['release_authority'] is False


@pytest.mark.parametrize('damage', ['rows', 'raw', 'decoded', 'stored', 'carry', 'offset',
    'count', 'digest', 'context', 'transcript', 'extra', 'four_segments', 'duplicate', 'alias'])
def test_closed_manifest_rejects_forged_accounting_and_addresses(tmp_path, damage):
    m = module()
    path, source = retain(m, tmp_path / damage, m.build_shared_temperature_source(**request([(AT, envelope(AT))])))
    manifest = json.loads(path.read_bytes())
    if damage in ('rows', 'raw', 'decoded', 'stored', 'carry'):
        key = dict(rows='row_count', raw='raw_bytes', decoded='decoded_bytes', stored='stored_bytes', carry='carry_count')[damage]
        manifest[key] += 1
    if damage == 'offset': manifest['segments'][0]['row_offset'] += 1
    if damage == 'count': manifest['segments'][0]['row_count'] += 1
    if damage == 'digest': manifest['segments'][0]['decoded_sha256'] = '0' * 64
    if damage == 'context': manifest['context']['contexts']['air']['sensor_epoch'] = EPOCHS['mass']
    if damage == 'transcript': manifest['transcript_sha256'] = '0' * 64
    if damage == 'extra': manifest['extra'] = False
    if damage == 'four_segments': manifest['segments'] *= 4
    if damage == 'duplicate': manifest['segments'] *= 2
    if damage == 'alias': manifest['segments'][0]['name'] = '../' + manifest['segments'][0]['name']
    forged = republish_manifest(path.parent, manifest)
    with pytest.raises(ValueError): m.read_shared_temperature_source(path.parent, forged)


@pytest.mark.parametrize('damage', ['truncated', 'concatenated', 'bomb', 'duplicate_key',
    'unknown_field', 'spliced', 'noncanonical'])
def test_segment_corruption_refused_even_with_rehashed_descriptor(tmp_path, damage):
    m = module()
    path, _ = retain(m, tmp_path / damage, m.build_shared_temperature_source(**request([(AT, envelope(AT))])))
    manifest, parts = documents(path.parent, path)
    desc = manifest['segments'][0]
    original = (path.parent / desc['name']).read_bytes()
    decoded = gzip.decompress(original)
    if damage == 'truncated': raw = original[:-1]
    elif damage == 'concatenated': raw = original + gzip.compress(b'')
    elif damage == 'bomb': raw = gzip.compress(b'x' * 8388609, compresslevel=1, mtime=0)
    else:
        if damage == 'duplicate_key': decoded = decoded[:-1] + b',"ordinal":0}'
        if damage == 'unknown_field': parts[0]['extra'] = None; decoded = _canonical(parts[0])
        if damage == 'spliced': parts[0]['context_sha256'] = '0' * 64; decoded = _canonical(parts[0])
        if damage == 'noncanonical': decoded += b' '
        raw = gzip.compress(decoded, compresslevel=1, mtime=0)
    desc.update(name=sha256(raw).hexdigest() + '.native-temperature-segment-v1.json.gz',
        stored_sha256=sha256(raw).hexdigest(), stored_bytes=len(raw),
        decoded_sha256=sha256(decoded).hexdigest(), decoded_bytes=len(decoded))
    changed = path.parent / desc['name']
    changed.write_bytes(raw); changed.chmod(0o600)
    forged = republish_manifest(path.parent, manifest, account=True)
    with pytest.raises(ValueError): m.read_shared_temperature_source(path.parent, forged)


@pytest.mark.parametrize('damage', ['object_row', 'nested_raw', 'nested_clock', 'row_plus_one',
    'column_plus_one', 'rows_object', 'unknown_field', 'raw_plus_one', 'noncanonical_scalar'])
def test_segment_structure_refuses_before_unrestricted_json_allocation(tmp_path, monkeypatch, damage):
    m = module()
    path, _ = retain(m, tmp_path / damage, m.build_shared_temperature_source(**request([(AT, envelope(AT))])))
    manifest, parts = documents(path.parent, path)
    part = parts[0]
    malformed = {
        'object_row': [{'': {}}],
        'nested_raw': [[AT.isoformat(), {'nested': [[], {}]}]],
        'nested_clock': [[[AT.isoformat()], None]],
        'row_plus_one': [[AT.isoformat(), None], [AT.isoformat(), None]],
        'column_plus_one': [[AT.isoformat(), None, None]],
        'rows_object': {'one': [AT.isoformat(), None]},
        'raw_plus_one': [[AT.isoformat(), 'x' * 8193]],
        'noncanonical_scalar': [[AT.isoformat(), 'synthetic']],
    }
    if damage == 'unknown_field': part['unknown'] = {'nested': [{}, []]}
    else: part['native_rows'] = malformed[damage]
    decoded = _canonical(part)
    if damage == 'noncanonical_scalar':
        decoded = decoded.replace(b'"synthetic"', b'"\\u0073ynthetic"')
    assert len(decoded) < 12000  # Deliberately small structural probes, not stress inputs.
    stored = gzip.compress(decoded, compresslevel=1, mtime=0)
    descriptor = manifest['segments'][0]
    descriptor.update(name=sha256(stored).hexdigest() + '.native-temperature-segment-v1.json.gz',
        stored_sha256=sha256(stored).hexdigest(), stored_bytes=len(stored),
        decoded_sha256=sha256(decoded).hexdigest(), decoded_bytes=len(decoded))
    child = path.parent / descriptor['name']; child.write_bytes(stored); child.chmod(0o600)
    forged = republish_manifest(path.parent, manifest, account=True)
    generic_segment_parses = []
    original_loads = m.json.loads
    def observe_loads(raw, *args, **kwargs):
        if isinstance(raw, bytes) and b'"native_rows"' in raw:
            generic_segment_parses.append(len(raw))
        return original_loads(raw, *args, **kwargs)
    monkeypatch.setattr(m.json, 'loads', observe_loads)
    with pytest.raises(ValueError):
        m.read_shared_temperature_source(path.parent, forged)
    assert generic_segment_parses == [], 'unrestricted segment object materialization preceded structural admission'


def test_flat_segment_parser_preserves_canonical_escaped_raw_scalars(tmp_path, monkeypatch):
    m = module()
    originals = ['synthetic', '"\\', '\\\\"', 'é☃🐐\x00\n\t', '\r\n', 'null', None]
    rows = [(AT + timedelta(seconds=i), raw) for i, raw in enumerate(originals)]
    rows.append((AT + timedelta(seconds=len(rows)), envelope(AT + timedelta(seconds=len(rows)))))
    args = request(rows, [at for at, _ in rows])
    expected = oracle(args)
    path, retained = retain(m, tmp_path / 'flat-scalars', m.build_shared_temperature_source(**args))
    original_loads = m.json.loads
    generic_segment_parses = []
    def observe_loads(raw, *a, **kw):
        if isinstance(raw, bytes) and b'"native_rows"' in raw: generic_segment_parses.append(True)
        return original_loads(raw, *a, **kw)
    monkeypatch.setattr(m.json, 'loads', observe_loads)
    assert m.replay_shared_temperature_source(retained) == expected
    assert generic_segment_parses == []


@pytest.mark.parametrize('damage', ['delete', 'replace_same_bytes', 'append', 'mode', 'symlink', 'hardlink'])
def test_retained_replay_rechecks_child_custody_after_prior_success(tmp_path, damage):
    m = module()
    path, source = retain(m, tmp_path / damage, m.build_shared_temperature_source(**request([(AT, envelope(AT))])))
    assert m.replay_shared_temperature_source(source)['air'][0][1] is not None
    child = m.shared_temperature_source_files(source)[1]
    if damage == 'delete': child.unlink()
    if damage == 'replace_same_bytes':
        copy = child.with_suffix('.replacement'); copy.write_bytes(child.read_bytes()); copy.chmod(0o600); copy.replace(child)
    if damage == 'append':
        with child.open('ab') as handle: handle.write(b'x')
    if damage == 'mode': child.chmod(0o644)
    if damage == 'symlink':
        copy = child.with_suffix('.original'); child.rename(copy); child.symlink_to(copy)
    if damage == 'hardlink': child.with_suffix('.alias').hardlink_to(child)
    with pytest.raises((ValueError, OSError)): m.replay_shared_temperature_source(source)


def test_guarded_cancellation_and_child_mutation_never_return_grid(tmp_path):
    m = module()
    args = request([(AT, envelope(AT))])
    def expired(): raise ValueError('synthetic deadline expired')
    with pytest.raises(ValueError, match='synthetic deadline'): m.build_shared_temperature_source(**args, guard=expired)
    source = m.build_shared_temperature_source(**args)
    path, retained = retain(m, tmp_path / 'guarded', source)
    child = m.shared_temperature_source_files(retained)[1]
    calls = []
    def mutate():
        calls.append(True)
        if len(calls) == 10: child.unlink()
    with pytest.raises((ValueError, OSError)): m.replay_shared_temperature_source(retained, guard=mutate)


def test_manifest_last_guard_after_temporary_write_prevents_publication(tmp_path):
    m = module()
    root = tmp_path / 'cancel-publication'; root.mkdir(mode=0o700)
    source = m.build_shared_temperature_source(**request([(AT, envelope(AT))]))
    reached = []
    def guard():
        for path in root.glob('.temperature-origin-*'):
            if b'earthship-native-temperature-shared-query/v1' in path.read_bytes():
                reached.append(True)
                raise ValueError('synthetic authority revoked after manifest temporary write')
    with pytest.raises(ValueError, match='synthetic authority'):
        m.write_shared_temperature_source(root, source, guard=guard)
    assert reached and not list(root.glob('*.native-temperature-shared-v1.json'))
    assert not list(root.glob('.temperature-origin-*'))


@pytest.mark.parametrize('damage', ['original_child', 'destination_directory'])
def test_last_publication_guard_cannot_mutate_original_source_unnoticed(tmp_path, damage):
    m = module()
    _, retained = retain(m, tmp_path / 'original', m.build_shared_temperature_source(**request([(AT, envelope(AT))])))
    calibration = tmp_path / 'calibration'; calibration.mkdir(mode=0o700)
    observed = []
    m.write_shared_temperature_source(calibration, retained, guard=lambda: observed.append(True))
    destination = tmp_path / 'final-guard'; destination.mkdir(mode=0o700)
    child = m.shared_temperature_source_files(retained)[1]
    calls = []
    def revoke_at_last_callback():
        calls.append(True)
        if len(calls) == len(observed):
            if damage == 'original_child':
                child.unlink()
            else:
                destination.chmod(0o755)
    with pytest.raises((ValueError, OSError)):
        m.write_shared_temperature_source(destination, retained, guard=revoke_at_last_callback)
    assert not list(destination.glob('*.native-temperature-shared-v1.json'))


@pytest.mark.parametrize('fault', ['directory_fsync', 'temporary_unlink'])
@pytest.mark.parametrize('prior', ['absent', 'existing', 'replacement'])
def test_manifest_post_link_failure_rolls_back_only_its_owned_link(tmp_path, monkeypatch, fault, prior):
    m = module()
    source = m.build_shared_temperature_source(**request([(AT, envelope(AT))]))
    root = tmp_path / (fault + '-' + prior); root.mkdir(mode=0o700)
    manifest = root / (sha256(source.manifest_bytes).hexdigest() + '.native-temperature-shared-v1.json')
    if prior == 'existing':
        m.write_shared_temperature_source(root, source)
        original_inode = manifest.stat().st_ino
    injected = []
    fsync, unlink = m.os.fsync, m.os.unlink
    def fail_after_link():
        if prior == 'replacement':
            replacement = root / 'replacement'
            replacement.write_bytes(source.manifest_bytes); replacement.chmod(0o600)
            replacement.replace(manifest)
        injected.append(True)
        raise OSError('synthetic manifest post-link failure')
    def fail_fsync(fd):
        if (fault == 'directory_fsync' and not injected and manifest.exists()
                and stat.S_ISDIR(m.os.fstat(fd).st_mode)
                and any(path.read_bytes() == source.manifest_bytes for path in root.glob('.temperature-origin-*'))):
            fail_after_link()
        return fsync(fd)
    def fail_unlink(path, *args, **kwargs):
        path = Path(path)
        if (fault == 'temporary_unlink' and not injected and manifest.exists()
                and path.name.startswith('.temperature-origin-')
                and path.read_bytes() == source.manifest_bytes):
            fail_after_link()
        return unlink(path, *args, **kwargs)
    monkeypatch.setattr(m.os, 'fsync', fail_fsync)
    monkeypatch.setattr(m.os, 'unlink', fail_unlink)
    with pytest.raises(OSError, match='synthetic manifest post-link failure'):
        m.write_shared_temperature_source(root, source)
    assert injected
    if prior == 'absent':
        assert not manifest.exists()
    else:
        assert manifest.read_bytes() == source.manifest_bytes
        if prior == 'existing': assert manifest.stat().st_ino == original_inode
        assert m.replay_shared_temperature_source(m.read_shared_temperature_source(root, manifest)) == oracle(request([(AT, envelope(AT))]))
    assert not list(root.glob('.temperature-origin-*'))


def test_replaced_manifest_temporary_is_not_published_or_removed(tmp_path):
    m = module()
    source = m.build_shared_temperature_source(**request([(AT, envelope(AT))]))
    root = tmp_path / 'temporary-owner'; root.mkdir(mode=0o700)
    replaced = []
    def replace_temporary():
        if replaced: return
        for path in root.glob('.temperature-origin-*'):
            if path.read_bytes() == source.manifest_bytes:
                path.rename(root / 'retained-original-temporary')
                path.write_bytes(b'synthetic replacement owned by another attempt')
                path.chmod(0o600)
                replaced.append(path)
    with pytest.raises((ValueError, OSError)):
        m.write_shared_temperature_source(root, source, guard=replace_temporary)
    assert replaced and replaced[0].read_bytes() == b'synthetic replacement owned by another attempt'
    assert not list(root.glob('*.native-temperature-shared-v1.json'))


def test_empty_source_exact_inventory_read_count_and_within_loop_deadline(tmp_path, monkeypatch):
    m = module()
    source = m.build_shared_temperature_source(rows=[], targets=[AT], assessed_at=AT, contexts=contexts())
    path, retained = retain(m, tmp_path / 'empty', source)
    observed = []
    original_read = m._read
    def read(path, *a, **kw):
        observed.append(path)
        return original_read(path, *a, **kw)
    monkeypatch.setattr(m, '_read', read)
    assert m.replay_shared_temperature_source(retained) == {role: [(AT, None)] for role in contexts()}
    assert tuple(observed) == m.shared_temperature_source_files(retained)
    rows = [(AT + timedelta(seconds=i), envelope(AT + timedelta(seconds=i))) for i in range(20)]
    source = m.build_shared_temperature_source(**request(rows))
    decoded = []
    original_envelope = m._envelope
    def decode(raw):
        decoded.append(True)
        return original_envelope(raw)
    monkeypatch.setattr(m, '_envelope', decode)
    def deadline():
        if len(decoded) == 5:
            raise ValueError('synthetic loop deadline')
    with pytest.raises(ValueError, match='synthetic loop deadline'):
        m.replay_shared_temperature_source(source, guard=deadline)
    assert len(decoded) == 5


def test_actual_global_raw_and_decoded_aggregate_bounds():
    m = module()
    # Original bytes are labeled synthetic malformed barriers, still retained.
    rows = [(AT + timedelta(seconds=i), 'x' * 8000) for i in range(3000)]
    with pytest.raises(ValueError, match='aggregate'):
        m.build_shared_temperature_source(**request(rows))  # Raw exactly 24M; canonical exceeds it.
    rows[-1] = (rows[-1][0], 'x' * 8001)
    with pytest.raises(ValueError):
        m.build_shared_temperature_source(**request(rows))  # 24,000,001 original bytes.


def test_exact_segment_boundary_then_one_more_byte_splits_without_reset():
    m = module()
    rows = [(AT + timedelta(seconds=i), 'x' * 8100) for i in range(1020)]
    source = m.build_shared_temperature_source(**request(rows))
    manifest = json.loads(source.manifest_bytes)
    remaining = 8388608 - manifest['segments'][0]['decoded_bytes']
    for i, (at, raw) in enumerate(rows):
        extra = min(8192 - len(raw), remaining)
        rows[i] = (at, raw + 'x' * extra)
        remaining -= extra
    assert remaining == 0
    exact = m.build_shared_temperature_source(**request(rows))
    manifest = json.loads(exact.manifest_bytes)
    assert len(manifest['segments']) == 1 and manifest['segments'][0]['decoded_bytes'] == 8388608
    assert m.replay_shared_temperature_source(exact) == oracle(request(rows))
    rows[-1] = (rows[-1][0], rows[-1][1] + 'x')
    split = m.build_shared_temperature_source(**request(rows))
    assert len(json.loads(split.manifest_bytes)['segments']) == 2
    assert m.replay_shared_temperature_source(split) == oracle(request(rows))


def test_existing_three_role_binding_refuses_aggregate_that_shared_query_fits(tmp_path):
    from thermal_model.installed_shade_raw_score_sources import build_native_origin_binding
    from thermal_model.temperature_history import STREAMS, POLICY
    m = module()
    observed = AT.replace(microsecond=0) + timedelta(days=1)
    targets = [observed - timedelta(minutes=5 * i) for i in reversed(range(288))]
    rows = [(targets[0] + timedelta(seconds=16 * i), 'synthetic barrier'.ljust(6650)) for i in range(1200)]
    selected_contexts = {role: dict(stream=stream, policy=TemperaturePolicy(model, sensor, **POLICY),
        sensor_epoch=EPOCHS[role]) for role, (stream, model, sensor) in STREAMS.items()}
    args = dict(rows=rows, targets=targets, assessed_at=observed, contexts=selected_contexts)
    expected = oracle(args)
    root = tmp_path / 'old-aggregate'; root.mkdir(mode=0o700)
    paths, proof_roles = {}, {}
    for role, context in selected_contexts.items():
        packet = legacy.build_temperature_source(rows=rows, targets=targets, assessed_at=observed, **context)
        paths[role] = str(legacy.write_temperature_source(root, packet))
        proof_roles[role] = dict(identity=dict(stream=context['stream'], model=context['policy'].model,
            sensor_id=context['policy'].sensor_id, sensor_epoch=context['sensor_epoch']), grid=expected[role])
    proof = dict(schema='earthship-thermal-origin-temperatures/v2', assessed_at=observed.isoformat(), roles=proof_roles)
    with pytest.raises(ValueError, match='aggregate issue-query bytes exceed bound'):
        build_native_origin_binding(proof, source_paths=paths, issue_at=observed)
    source = m.build_shared_temperature_source(**args)
    assert m.replay_shared_temperature_source(source) == expected
    assert json.loads(source.manifest_bytes)['decoded_bytes'] < 24000000


@pytest.mark.parametrize('damage', ['manifest_plus_one', 'manifest_duplicate', 'wrong_address',
    'segment_decoded_plus_one', 'segment_raw_plus_one', 'segment_stored_plus_one',
    'total_decoded_plus_one', 'total_stored_plus_one', 'total_raw_plus_one', 'bool_accounting'])
def test_wire_byte_plus_one_and_closed_manifest_limits(tmp_path, damage):
    m = module()
    path, _ = retain(m, tmp_path / damage, m.build_shared_temperature_source(**request([(AT, envelope(AT))])))
    manifest = json.loads(path.read_bytes())
    if damage.startswith('segment_'):
        field = damage.split('_')[1] + '_bytes'
        manifest['segments'][0][field] = 8388608 + (4096 if field == 'stored_bytes' else 0) + 1
    elif damage.startswith('total_'):
        manifest[damage.split('_')[1] + '_bytes'] = 24000001
    elif damage == 'bool_accounting':
        manifest['segments'][0]['ordinal'] = False
    if damage in ('manifest_plus_one', 'manifest_duplicate', 'wrong_address'):
        raw = (b' ' * 65537 if damage == 'manifest_plus_one' else
               path.read_bytes()[:-1] + b',"release_authority":false}' if damage == 'manifest_duplicate' else
               path.read_bytes())
        forged = path.parent / (('0' * 64 if damage == 'wrong_address' else sha256(raw).hexdigest())
                                  + '.native-temperature-shared-v1.json')
        forged.write_bytes(raw); forged.chmod(0o600)
    else:
        forged = republish_manifest(path.parent, manifest)
    with pytest.raises(ValueError):
        m.read_shared_temperature_source(path.parent, forged)


def rewrite_segments(root, manifest, parts):
    """Construct wire bytes independently, retaining the original transcript pin."""
    offset = 0
    descriptors = []
    for ordinal, part in enumerate(parts):
        part.update(ordinal=ordinal, row_offset=offset)
        rows = part['native_rows']
        decoded = _canonical(part)
        stored = gzip.compress(decoded, compresslevel=1, mtime=0)
        name = sha256(stored).hexdigest() + '.native-temperature-segment-v1.json.gz'
        child = root / name; child.write_bytes(stored); child.chmod(0o600)
        descriptors.append(dict(ordinal=ordinal, row_offset=offset, row_count=len(rows),
            first_stored_at=rows[0][0], last_stored_at=rows[-1][0],
            raw_bytes=sum(0 if row[1] is None else len(row[1].encode()) for row in rows),
            decoded_bytes=len(decoded), stored_bytes=len(stored), decoded_sha256=sha256(decoded).hexdigest(),
            stored_sha256=sha256(stored).hexdigest(), name=name))
        offset += len(rows)
    manifest.update(segments=descriptors, row_count=offset,
                    raw_bytes=sum(d['raw_bytes'] for d in descriptors))
    return republish_manifest(root, manifest, account=True)


@pytest.mark.parametrize('damage', [None, 'conflicting_boundary', 'reordered', 'truncated'])
def test_continuous_barrier_and_duplicate_state_across_independent_partition(tmp_path, damage):
    m = module()
    rows = [(AT, envelope(AT)), (AT + timedelta(seconds=1), None)]
    for i in range(2, 10):
        at = AT + timedelta(seconds=i)
        rows.append((at, envelope(at, received=at - timedelta(seconds=1))))
    rows.insert(5, rows[4])  # Equal original timestamp/bytes split across the boundary.
    args = request(rows, [AT, AT + timedelta(seconds=4), AT + timedelta(seconds=9)])
    path, _ = retain(m, tmp_path / str(damage), m.build_shared_temperature_source(**args))
    manifest, original_parts = documents(path.parent, path)
    all_rows = original_parts[0]['native_rows']
    parts = [{**original_parts[0], 'native_rows': all_rows[:5]},
             {**original_parts[0], 'native_rows': all_rows[5:]}]
    if damage == 'conflicting_boundary': parts[1]['native_rows'][0][1] = None
    if damage == 'reordered': parts.reverse()
    if damage == 'truncated': parts.pop()
    changed = rewrite_segments(path.parent, manifest, parts)
    if damage is None:
        retained = m.read_shared_temperature_source(path.parent, changed)
        assert m.replay_shared_temperature_source(retained) == oracle(args)
    else:
        with pytest.raises(ValueError): m.read_shared_temperature_source(path.parent, changed)
