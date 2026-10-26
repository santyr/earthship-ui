"""Inactive, lossless shared native-v2 query storage and continuous replay.

The new profile admits one logical query up to 24,000,000 bytes, in at most
three 8 MiB segments. Legacy query formats and limits are unchanged. A source
is original evidence only: it grants no model, publication or release authority.
"""
from dataclasses import asdict, dataclass
from contextlib import contextmanager
from datetime import timedelta
import gzip
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile
from uuid import UUID
import zlib

from weather_source_files import _canonical, _directory, _instant, _read, _write
from weather_temperature_evidence import MODELS, TemperaturePolicy, sensor_epoch_id
from weather_temperature_history import _fetch_rows
from weather_temperature_reader import FIELDS, _grid_context, _object, _reject_constant, _utc

SCHEMA = 'earthship-native-temperature-shared-query/v1'
SEGMENT_SCHEMA = 'earthship-native-temperature-query-segment/v1'
MANIFEST_SUFFIX = '.native-temperature-shared-v1.json'
SEGMENT_SUFFIX = '.native-temperature-segment-v1.json.gz'
MAX_SEGMENT_BYTES = 8388608
MAX_STORED_SEGMENT_BYTES = MAX_SEGMENT_BYTES + 4096
MAX_MANIFEST_BYTES = 65536
MAX_TOTAL_BYTES = 24000000
MAX_ROWS = 10000
MAX_SEGMENTS = 3
ROLES = ('air', 'mass', 'outdoor')
TRANSCRIPT_DOMAIN = b'earthship-native-temperature-ordered-transcript/v1\x00'
CONTEXT_FIELDS = {'contexts', 'targets', 'assessed_at', 'history_start'}
MANIFEST_FIELDS = {'schema', 'context', 'context_sha256', 'segments', 'row_count',
                   'carry_count', 'raw_bytes', 'decoded_bytes', 'stored_bytes',
                   'transcript_sha256', 'release_authority'}
SEGMENT_FIELDS = {'schema', 'context_sha256', 'ordinal', 'row_offset', 'native_rows'}
DESCRIPTOR_FIELDS = {'ordinal', 'row_offset', 'row_count', 'first_stored_at',
                     'last_stored_at', 'raw_bytes', 'decoded_bytes', 'stored_bytes',
                     'decoded_sha256', 'stored_sha256', 'name'}
_INVALID_SNAPSHOT = (ValueError, TypeError, KeyError, OverflowError, RecursionError)
_STRING_END = re.compile(rb'(?<!\\)(?:\\\\)*"')


@dataclass(frozen=True, slots=True)
class SharedTemperatureSource:
    """Deeply immutable source bytes or a complete, custody-pinned file inventory.

    ``manifest_bytes`` is canonical JSON. Build/fetch handles have no retained
    files; call write then read to obtain a retained handle. Replay always
    validates the complete source, including when constructed by a caller.
    """
    manifest_bytes: bytes
    _chunks: tuple[bytes, ...] = ()
    _files: tuple[Path, ...] = ()
    _fingerprints: tuple[tuple[int, ...], ...] = ()

    def __post_init__(self):
        if (type(self.manifest_bytes) is not bytes or type(self._chunks) is not tuple
                or any(type(raw) is not bytes for raw in self._chunks)
                or type(self._files) is not tuple or any(not isinstance(p, Path) for p in self._files)
                or type(self._fingerprints) is not tuple
                or any(type(fp) is not tuple or any(type(v) is not int for v in fp)
                       for fp in self._fingerprints)):
            raise ValueError('immutable original source representation required')


def _guard(guard):
    if guard is not None:
        if not callable(guard):
            raise ValueError('callable shared source deadline guard required')
        guard()


def _json(raw):
    try:
        return json.loads(raw, object_pairs_hook=_object, parse_constant=_reject_constant)
    except (ValueError, TypeError, RecursionError, UnicodeError) as error:
        raise ValueError('strict bounded source JSON required') from error


def _closed(value, fields):
    if type(value) is not dict or set(value) != fields:
        raise ValueError('closed original source schema required')


def _integer(value, maximum):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError('bounded original source accounting required')


def _digest(value):
    if not isinstance(value, str) or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise ValueError('exact source digest required')


def _context(*, targets, assessed_at, contexts):
    _closed(contexts, set(ROLES))
    if not isinstance(targets, (list, tuple)) or not 1 <= len(targets) <= 289:
        raise ValueError('bounded original target grid required')
    targets = [_utc(at) for at in targets]
    assessed = _utc(assessed_at)
    start = targets[0] - timedelta(seconds=120)
    frozen = {}
    for role in ROLES:
        context = contexts[role]
        _closed(context, {'stream', 'policy', 'sensor_epoch'})
        stream, policy = context['stream'], context['policy']
        if (not isinstance(stream, str) or re.fullmatch('[a-z][a-z0-9_]{0,31}', stream) is None
                or not isinstance(policy, TemperaturePolicy) or policy.validity_seconds != 120):
            raise ValueError('explicit stream and unchanged 120-second native policy required')
        _grid_context(targets, assessed, start, stream, policy)
        frozen[role] = dict(stream=stream, policy=asdict(policy),
                            sensor_epoch=sensor_epoch_id(context['sensor_epoch']))
    if len({value['stream'] for value in frozen.values()}) != len(ROLES):
        raise ValueError('three distinct thermal streams required')
    return dict(contexts=frozen, targets=[at.isoformat() for at in targets],
                assessed_at=assessed.isoformat(), history_start=start.isoformat())


def _restore_context(context):
    _closed(context, CONTEXT_FIELDS)
    _closed(context['contexts'], set(ROLES))
    contexts = {}
    for role in ROLES:
        value = context['contexts'][role]
        _closed(value, {'stream', 'policy', 'sensor_epoch'})
        _closed(value['policy'], set(TemperaturePolicy.__dataclass_fields__))
        contexts[role] = dict(stream=value['stream'], policy=TemperaturePolicy(**value['policy']),
                              sensor_epoch=value['sensor_epoch'])
    frozen = _context(targets=context['targets'], assessed_at=context['assessed_at'], contexts=contexts)
    if _canonical(frozen) != _canonical(context):
        raise ValueError('canonical frozen original query context required')
    return contexts


def _transcript(context_digest):
    return sha256(TRANSCRIPT_DOMAIN + bytes.fromhex(context_digest))


def _record_transcript(transcript, row_bytes):
    transcript.update(len(row_bytes).to_bytes(8, 'big'))
    transcript.update(row_bytes)


def _segment_frame(context_digest, ordinal, offset):
    # Canonical order; append each row once, rather than serializing the whole
    # accumulated query on every observation. Suffix bytes count toward 8 MiB.
    prefix = b'{"context_sha256":"' + context_digest.encode('ascii') + b'","native_rows":['
    suffix = (b'],"ordinal":' + str(ordinal).encode('ascii') + b',"row_offset":'
              + str(offset).encode('ascii') + b',"schema":' + _canonical(SEGMENT_SCHEMA) + b'}')
    return prefix, suffix


def _manifest_bytes(manifest):
    decoded = sum(d['decoded_bytes'] for d in manifest['segments'])
    stored = sum(d['stored_bytes'] for d in manifest['segments'])
    # Only the decimal widths of these two totals affect the manifest size.
    for _ in range(8):
        raw = _canonical(manifest)
        totals = (decoded + len(raw), stored + len(raw))
        if totals == (manifest['decoded_bytes'], manifest['stored_bytes']):
            if len(raw) > MAX_MANIFEST_BYTES or max(totals) > MAX_TOTAL_BYTES:
                raise ValueError('shared source aggregate exceeds bound')
            return raw
        manifest['decoded_bytes'], manifest['stored_bytes'] = totals
    raise ValueError('source accounting did not converge')


def build_shared_temperature_source(*, rows, targets, assessed_at, contexts, guard=None):
    """Freeze one complete original query; no selection, DB or file authority."""
    _guard(guard)
    context = _context(targets=targets, assessed_at=assessed_at, contexts=contexts)
    if not isinstance(rows, list) or len(rows) > MAX_ROWS:
        raise ValueError('bounded complete original row list required')
    context_digest = sha256(_canonical(context)).hexdigest()
    transcript = _transcript(context_digest)
    start, end = _instant(context['history_start']), _instant(context['targets'][-1])
    chunks, descriptors = [], []
    ordinal = offset = segment_count = segment_raw = total_raw = carry = 0
    first = last = previous_at = previous_raw = None
    prefix, suffix = _segment_frame(context_digest, ordinal, offset)
    buffer = bytearray(prefix)

    def seal():
        _guard(guard)
        decoded = bytes(buffer) + suffix
        stored = gzip.compress(decoded, compresslevel=1, mtime=0)
        _guard(guard)
        if len(stored) > MAX_STORED_SEGMENT_BYTES:
            raise ValueError('stored segment exceeds bound')
        digest = sha256(stored).hexdigest()
        descriptors.append(dict(ordinal=ordinal, row_offset=offset, row_count=segment_count,
            first_stored_at=first, last_stored_at=last, raw_bytes=segment_raw,
            decoded_bytes=len(decoded), stored_bytes=len(stored), decoded_sha256=sha256(decoded).hexdigest(),
            stored_sha256=digest, name=digest + SEGMENT_SUFFIX))
        chunks.append(stored)

    for row in rows:
        _guard(guard)
        if not isinstance(row, (list, tuple)) or len(row) != 2:
            raise ValueError('original timestamp/raw pair required')
        at, raw = _utc(row[0]), row[1]
        if raw is not None and not isinstance(raw, str):
            raise ValueError('raw text or null barrier required')
        size = 0 if raw is None else len(raw.encode('utf-8'))
        if size > 8192:
            raise ValueError('original row exceeds raw UTF-8 byte bound')
        if previous_at is not None and (at < previous_at or (at == previous_at and raw != previous_raw)):
            raise ValueError('unordered or conflicting original history')
        previous_at, previous_raw = at, raw
        carry += at < start
        total_raw += size
        if carry > 1 or at > end or total_raw > MAX_TOTAL_BYTES:
            raise ValueError('original query exceeds global bounds')
        instant = at.isoformat()
        row_bytes = _canonical([instant, raw])
        if (segment_raw + size > MAX_SEGMENT_BYTES
                or len(buffer) + bool(segment_count) + len(row_bytes) + len(suffix) > MAX_SEGMENT_BYTES):
            seal()
            offset += segment_count
            ordinal += 1
            if ordinal >= MAX_SEGMENTS:
                raise ValueError('shared source exceeds segment count')
            segment_count = segment_raw = 0
            first = last = None
            prefix, suffix = _segment_frame(context_digest, ordinal, offset)
            buffer = bytearray(prefix)
        if len(buffer) + len(row_bytes) + len(suffix) > MAX_SEGMENT_BYTES:
            raise ValueError('single canonical row exceeds segment bound')
        if segment_count:
            buffer.extend(b',')
        buffer.extend(row_bytes)
        segment_count += 1
        segment_raw += size
        first = first or instant
        last = instant
        _record_transcript(transcript, row_bytes)
    seal()
    manifest = dict(schema=SCHEMA, context=context, context_sha256=context_digest, segments=descriptors,
        row_count=len(rows), carry_count=carry, raw_bytes=total_raw, decoded_bytes=0, stored_bytes=0,
        transcript_sha256=transcript.hexdigest(), release_authority=False)
    raw_manifest = _manifest_bytes(manifest)
    _guard(guard)
    return SharedTemperatureSource(raw_manifest, tuple(chunks))


def fetch_shared_temperature_source(connection_factory, *, targets, assessed_at, contexts,
                                    remaining_timeout=None, guard=None):
    """Exactly one unchanged read-only REPEATABLE READ query, after freezing context."""
    _guard(guard)
    context = _context(targets=targets, assessed_at=assessed_at, contexts=contexts)
    frozen_contexts = _restore_context(context)
    _guard(guard)
    rows = _fetch_rows(connection_factory, _instant(context['history_start']),
                       _instant(context['targets'][-1]), remaining_timeout=remaining_timeout)
    _guard(guard)
    return build_shared_temperature_source(rows=rows, targets=context['targets'],
        assessed_at=context['assessed_at'], contexts=frozen_contexts, guard=guard)


def _parse_manifest(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_MANIFEST_BYTES:
        raise ValueError('bounded manifest bytes required')
    manifest = _json(raw)
    _closed(manifest, MANIFEST_FIELDS)
    if manifest['schema'] != SCHEMA or manifest['release_authority'] is not False or _canonical(manifest) != raw:
        raise ValueError('canonical shared source with no release authority required')
    _restore_context(manifest['context'])
    _digest(manifest['context_sha256'])
    _digest(manifest['transcript_sha256'])
    if sha256(_canonical(manifest['context'])).hexdigest() != manifest['context_sha256']:
        raise ValueError('original context digest differs')
    for key, maximum in (('row_count', MAX_ROWS), ('carry_count', 1), ('raw_bytes', MAX_TOTAL_BYTES),
                          ('decoded_bytes', MAX_TOTAL_BYTES), ('stored_bytes', MAX_TOTAL_BYTES)):
        _integer(manifest[key], maximum)
    segments = manifest['segments']
    if not isinstance(segments, list) or not 1 <= len(segments) <= MAX_SEGMENTS:
        raise ValueError('bounded ordered segments required')
    offset = 0
    for ordinal, descriptor in enumerate(segments):
        _closed(descriptor, DESCRIPTOR_FIELDS)
        for key, maximum in (('ordinal', MAX_SEGMENTS - 1), ('row_offset', MAX_ROWS), ('row_count', MAX_ROWS),
            ('raw_bytes', MAX_SEGMENT_BYTES), ('decoded_bytes', MAX_SEGMENT_BYTES),
            ('stored_bytes', MAX_STORED_SEGMENT_BYTES)):
            _integer(descriptor[key], maximum)
        if descriptor['ordinal'] != ordinal or descriptor['row_offset'] != offset:
            raise ValueError('consecutive original row offsets required')
        offset += descriptor['row_count']
        for key in ('decoded_sha256', 'stored_sha256'):
            _digest(descriptor[key])
        if descriptor['name'] != descriptor['stored_sha256'] + SEGMENT_SUFFIX:
            raise ValueError('exact child content address required')
        if descriptor['row_count'] == 0:
            if len(segments) != 1 or descriptor['first_stored_at'] is not None or descriptor['last_stored_at'] is not None:
                raise ValueError('only empty query may have empty segment')
        else:
            first, last = (_instant(descriptor[key]) for key in ('first_stored_at', 'last_stored_at'))
            if first > last:
                raise ValueError('ordered segment endpoints required')
    actual = dict(row_count=offset, raw_bytes=sum(d['raw_bytes'] for d in segments),
                  decoded_bytes=len(raw) + sum(d['decoded_bytes'] for d in segments),
                  stored_bytes=len(raw) + sum(d['stored_bytes'] for d in segments))
    if any(manifest[key] != value for key, value in actual.items()):
        raise ValueError('global source accounting differs')
    return manifest


def _fingerprint(path):
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_nlink != 1 or path.resolve(strict=True) != path):
        raise ValueError('owned private non-aliased source required')
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
            info.st_mode, info.st_uid, info.st_nlink)


def _read_checked(path, maximum, guard, expected=None):
    _guard(guard)
    before = _fingerprint(path)
    if expected is not None and before != expected:
        raise ValueError('retained source custody changed')
    raw = _read(path, maximum)
    _guard(guard)
    if _fingerprint(path) != before:
        raise ValueError('source changed around read')
    return raw, before


def _verify_files(files, fingerprints, guard):
    if len(files) != len(fingerprints):
        raise ValueError('complete retained source custody required')
    _guard(guard)
    for path in files:
        _guard(guard)
    # No user callback between this final bounded custody check and return.
    for directory in {path.parent for path in files}:
        _directory(directory)
    if any(_fingerprint(path) != original for path, original in zip(files, fingerprints)):
        raise ValueError('retained source changed before completion')


def shared_temperature_source_files(source):
    """Return manifest then every ordered segment; unretained bytes are not files."""
    if not isinstance(source, SharedTemperatureSource) or not source._files or source._chunks:
        raise ValueError('sealed retained source inventory required')
    manifest = _parse_manifest(source.manifest_bytes)
    root = source._files[0].parent
    expected = (root / (sha256(source.manifest_bytes).hexdigest() + MANIFEST_SUFFIX),) + tuple(
        root / descriptor['name'] for descriptor in manifest['segments'])
    if source._files != expected:
        raise ValueError('complete exact source inventory required')
    _verify_files(source._files, source._fingerprints, None)
    return source._files


def _scalar_string(raw, position, end, maximum, guard):
    """Admit only one bounded canonical string before decoding its scalar value."""
    _guard(guard)
    if raw[position:position + 1] != b'"':
        raise ValueError('flat original string scalar required')
    # At most six ASCII wire bytes per original UTF-8 byte (e.g. \u0000),
    # plus quotes. Find the first quote after an even run of backslashes in C;
    # nested objects and unbounded strings never reach a generic JSON parser.
    match = _STRING_END.search(raw, position + 1, min(end, position + 6 * maximum + 2))
    if match is None:
        raise ValueError('bounded original string scalar required')
    token = raw[position:match.end()]
    try:
        value, consumed = json.decoder.scanstring(token.decode('ascii'), 1, True)
        if consumed != len(token) or len(value.encode('utf-8')) > maximum or _canonical(value) != token:
            raise ValueError('canonical bounded original string required')
    except (ValueError, UnicodeError) as error:
        raise ValueError('canonical bounded original string required') from error
    _guard(guard)
    return value, match.end()


def _segment_rows(raw, descriptor, context_digest, guard):
    """Parse the closed flat wire grammar incrementally, without object graphs."""
    _guard(guard)
    prefix, suffix = _segment_frame(context_digest, descriptor['ordinal'], descriptor['row_offset'])
    if not raw.startswith(prefix) or not raw.endswith(suffix):
        raise ValueError('canonical context-bound consecutive segment required')
    position, end, count = len(prefix), len(raw) - len(suffix), 0
    while position < end:
        _guard(guard)
        if count >= descriptor['row_count'] or count >= MAX_ROWS:
            raise ValueError('original segment row count differs')
        row_start = position
        if raw[position:position + 1] != b'[':
            raise ValueError('flat original timestamp/raw row required')
        instant, position = _scalar_string(raw, position + 1, end, 64, guard)
        if raw[position:position + 1] != b',':
            raise ValueError('original timestamp/raw pair required')
        position += 1
        if raw[position:position + 4] == b'null':
            value, position = None, position + 4
        else:
            value, position = _scalar_string(raw, position, end, 8192, guard)
        if raw[position:position + 1] != b']':
            raise ValueError('original timestamp/raw pair required')
        position += 1
        count += 1
        # These exact admitted canonical row bytes are also the transcript,
        # avoiding another serialization of the decoded original text.
        yield [instant, value], raw[row_start:position]
        if position < end:
            if raw[position:position + 1] != b',' or position + 1 == end:
                raise ValueError('canonical original row separator required')
            position += 1
    if count != descriptor['row_count']:
        raise ValueError('original segment row count differs')


def _decode_segment(stored, descriptor, context_digest, guard):
    _guard(guard)
    if (len(stored) > MAX_STORED_SEGMENT_BYTES or len(stored) != descriptor['stored_bytes']
            or sha256(stored).hexdigest() != descriptor['stored_sha256']):
        raise ValueError('original stored segment digest or bound differs')
    try:
        decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        raw = decoder.decompress(stored, MAX_SEGMENT_BYTES + 1)
    except zlib.error as error:
        raise ValueError('invalid gzip source segment') from error
    _guard(guard)
    if (len(raw) > MAX_SEGMENT_BYTES or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail
            or len(raw) != descriptor['decoded_bytes'] or sha256(raw).hexdigest() != descriptor['decoded_sha256']):
        raise ValueError('single bounded original gzip member required')
    if gzip.compress(raw, compresslevel=1, mtime=0) != stored:
        raise ValueError('deterministic gzip level 1 source required')
    _guard(guard)
    return _segment_rows(raw, descriptor, context_digest, guard)


def _envelope(raw):
    """Decode and hash the shared raw envelope once; selected roles stay independent."""
    if not isinstance(raw, str):
        raise ValueError('raw envelope required')
    document = _json(raw)
    _closed(document, {'version', 'streamEpoch', 'records'})
    if type(document['version']) is not int or document['version'] != 2:
        raise ValueError('native-v2 envelope required')
    epoch, records = document['streamEpoch'], document['records']
    if not isinstance(epoch, str) or str(UUID(epoch)) != epoch:
        raise ValueError('canonical collector epoch required')
    if (not isinstance(records, dict) or not 1 <= len(records) <= 4
            or any(re.fullmatch('[a-z][a-z0-9_]{0,31}', name) is None for name in records)):
        raise ValueError('bounded stream registry required')
    return epoch, records, sha256(raw.encode('utf-8')).hexdigest()


def _candidate(epoch, records, digest, stored, context):
    stream, policy, sensor_epoch = context['stream'], context['policy'], context['sensor_epoch']
    record = records.get(stream)
    if record is None:
        return None
    _closed(record, FIELDS | {'sensorEpoch'})
    if type(record['version']) is not int or record['version'] != 2 or record['streamEpoch'] != epoch:
        raise ValueError('record version/epoch mismatch')
    if (record['model'] != policy.model or type(record['sensorId']) is not int or record['sensorId'] != policy.sensor_id
            or record['field'] != MODELS[policy.model][1] or sensor_epoch_id(record['sensorEpoch']) != sensor_epoch):
        raise ValueError('record identity or hardware phase differs')
    recorded = _utc(record['recordedAt'])
    if recorded > stored:
        raise ValueError('future source record')
    if record['status'] != 'valid':
        return None
    received, expires = _utc(record['receivedAt']), _utc(record['validUntil'])
    value = record['temperatureF']
    if (record['reason'] != 'accepted' or received != recorded or type(value) not in (int, float)
            or not math.isfinite(value) or not policy.minimum_f <= value <= policy.maximum_f
            or not 0 < (expires - received).total_seconds() <= policy.validity_seconds):
        raise ValueError('receipt outside selected policy')
    return dict(temperatureF=value, receivedAt=received, validUntil=expires, storedAt=stored,
                streamEpoch=epoch, snapshotSha256=digest, sensorEpoch=sensor_epoch, receiptVersion=2)


def _advance(state, candidate, next_epoch, stored):
    selected, barrier_at, epoch = state
    if candidate is not None and selected is not None and next_epoch == epoch:
        earlier = candidate['receivedAt'] < selected['receivedAt']
        conflicting = candidate['receivedAt'] == selected['receivedAt'] and any(
            candidate[key] != selected[key] for key in ('temperatureF', 'validUntil'))
        if earlier or conflicting:
            candidate = None
    if epoch is not None and next_epoch != epoch and selected is not None:
        barrier_at = selected['storedAt']
    if candidate is None:
        barrier_at = stored
    elif barrier_at is not None and candidate['receivedAt'] <= barrier_at:
        candidate = None
        barrier_at = stored
    return candidate, barrier_at, next_epoch


def replay_shared_temperature_source(source, *, guard=None):
    """Fresh complete original-source replay with continuous independent role states."""
    _guard(guard)
    if not isinstance(source, SharedTemperatureSource):
        raise ValueError('immutable original shared source required')
    manifest = _parse_manifest(source.manifest_bytes)
    if source._files:
        files = shared_temperature_source_files(source)
        raw, _ = _read_checked(files[0], MAX_MANIFEST_BYTES, guard, source._fingerprints[0])
        if raw != source.manifest_bytes:
            raise ValueError('original retained manifest differs')
    elif source._fingerprints or len(source._chunks) != len(manifest['segments']):
        raise ValueError('complete original source segments required')
    context = manifest['context']
    contexts = _restore_context(context)
    targets = list(map(_instant, context['targets']))
    start, end = _instant(context['history_start']), targets[-1]
    results = {role: [] for role in ROLES}
    states = {role: (None, None, None) for role in ROLES}
    transcript = _transcript(manifest['context_sha256'])
    previous_at = previous_raw = None
    carry = count = total_raw = target_index = 0

    def emit(target):
        for role in ROLES:
            selected = states[role][0]
            value = selected if selected is not None and selected['receivedAt'] <= target < selected['validUntil'] else None
            results[role].append((target, None if value is None else dict(value)))

    for index, descriptor in enumerate(manifest['segments']):
        _guard(guard)
        if source._files:
            stored, _ = _read_checked(source._files[index + 1], MAX_STORED_SEGMENT_BYTES, guard,
                                       source._fingerprints[index + 1])
        else:
            stored = source._chunks[index]
        rows = _decode_segment(stored, descriptor, manifest['context_sha256'], guard)
        segment_raw = 0
        first = last = None
        for row, row_bytes in rows:
            _guard(guard)
            if not isinstance(row, list) or len(row) != 2:
                raise ValueError('closed original source row required')
            at, raw = _instant(row[0]), row[1]
            if at.isoformat() != row[0] or (raw is not None and not isinstance(raw, str)):
                raise ValueError('canonical timestamp and original raw text required')
            size = 0 if raw is None else len(raw.encode('utf-8'))
            if size > 8192:
                raise ValueError('original raw row exceeds bound')
            if previous_at is not None and (at < previous_at or (at == previous_at and raw != previous_raw)):
                raise ValueError('unordered or conflicting original history')
            previous_at, previous_raw = at, raw
            carry += at < start
            count += 1
            segment_raw += size
            total_raw += size
            if carry > 1 or count > MAX_ROWS or at > end or segment_raw > MAX_SEGMENT_BYTES or total_raw > MAX_TOTAL_BYTES:
                raise ValueError('original query exceeds global or segment bounds')
            first = first or row[0]
            last = row[0]
            _record_transcript(transcript, row_bytes)
            while target_index < len(targets) and targets[target_index] < at:
                emit(targets[target_index])
                target_index += 1
            try:
                epoch, records, digest = _envelope(raw)
            except _INVALID_SNAPSHOT:
                epoch, records, digest = None, None, None
            for role in ROLES:
                try:
                    candidate = _candidate(epoch, records, digest, at, contexts[role]) if records is not None else None
                    next_epoch = epoch
                except _INVALID_SNAPSHOT:
                    candidate, next_epoch = None, None
                states[role] = _advance(states[role], candidate, next_epoch, at)
        if (segment_raw != descriptor['raw_bytes'] or first != descriptor['first_stored_at']
                or last != descriptor['last_stored_at']):
            raise ValueError('original segment accounting differs')
        del rows, stored
    if (count != manifest['row_count'] or total_raw != manifest['raw_bytes'] or carry != manifest['carry_count']
            or transcript.hexdigest() != manifest['transcript_sha256']):
        raise ValueError('complete original query transcript differs')
    while target_index < len(targets):
        _guard(guard)
        emit(targets[target_index])
        target_index += 1
    _verify_files(source._files, source._fingerprints, guard)
    return results


def read_shared_temperature_source(directory, path, *, guard=None):
    """Read and validate every original file before returning a custody-bound handle."""
    _guard(guard)
    root, path = _directory(Path(directory)), Path(path)
    if path.parent != root or re.fullmatch('[0-9a-f]{64}' + re.escape(MANIFEST_SUFFIX), path.name) is None:
        raise ValueError('exact original manifest content address required')
    raw, fingerprint = _read_checked(path, MAX_MANIFEST_BYTES, guard)
    if sha256(raw).hexdigest() + MANIFEST_SUFFIX != path.name:
        raise ValueError('manifest digest differs')
    manifest = _parse_manifest(raw)
    files = (path,) + tuple(root / descriptor['name'] for descriptor in manifest['segments'])
    fingerprints = (fingerprint,) + tuple(_fingerprint(child) for child in files[1:])
    source = SharedTemperatureSource(raw, _files=files, _fingerprints=fingerprints)
    replay_shared_temperature_source(source, guard=guard)
    return source


def _unlink_owned(path, identity):
    """Remove only this attempt's link; replacements and other writers survive."""
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    if stat.S_ISREG(info.st_mode) and (info.st_dev, info.st_ino) == identity:
        os.unlink(path)


@contextmanager
def _manifest_publication(root, path, raw, before_publish):
    """Keep ownership before linking and through every fallible publication step."""
    fd, name = tempfile.mkstemp(prefix='.temperature-origin-', dir=root)
    temporary = Path(name)
    info = os.fstat(fd)
    identity = (info.st_dev, info.st_ino)
    linked = False
    try:
        # Keep the original inode open through rollback so a replacement cannot
        # reuse its inode number. The file object does not own this descriptor.
        with os.fdopen(fd, 'wb', closefd=False) as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        original = _fingerprint(temporary)
        before_publish()
        if _fingerprint(temporary) != original:
            raise ValueError('manifest temporary custody changed')
        try:
            os.link(temporary, path, follow_symlinks=False)
        except FileExistsError:
            if _read(path, MAX_MANIFEST_BYTES) != raw:
                raise ValueError('immutable manifest collision')
        else:
            linked = True
        directory_fd = os.open(root, os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        _unlink_owned(temporary, identity)
        yield
        os.close(fd)
        fd = None
    except BaseException:
        try:
            if linked:
                _unlink_owned(path, identity)
        finally:
            try:
                _unlink_owned(temporary, identity)
            finally:
                if fd is not None:
                    os.close(fd)
        raise


def write_shared_temperature_source(directory, source, *, guard=None):
    """Guarded atomic private segments first, complete manifest last; return its path."""
    _guard(guard)
    root = _directory(Path(directory))
    replay_shared_temperature_source(source, guard=guard)
    manifest = _parse_manifest(source.manifest_bytes)
    files, fingerprints = [], []
    for index, descriptor in enumerate(manifest['segments']):
        _guard(guard)
        if source._files:
            raw, _ = _read_checked(source._files[index + 1], MAX_STORED_SEGMENT_BYTES, guard,
                                   source._fingerprints[index + 1])
        else:
            raw = source._chunks[index]
        path = _write(root, descriptor['name'], raw, before_publish=lambda: _guard(guard))
        retained, fingerprint = _read_checked(path, MAX_STORED_SEGMENT_BYTES, guard)
        if retained != raw:
            raise ValueError('retained child differs from original')
        files.append(path)
        fingerprints.append(fingerprint)

    def before_manifest():
        _verify_files(source._files + tuple(files), source._fingerprints + tuple(fingerprints), guard)

    path = root / (sha256(source.manifest_bytes).hexdigest() + MANIFEST_SUFFIX)
    with _manifest_publication(root, path, source.manifest_bytes, before_manifest):
        published = _fingerprint(path)
        _guard(guard)
        read_shared_temperature_source(root, path, guard=guard)
        _verify_files(source._files + tuple(files) + (path,),
                      source._fingerprints + tuple(fingerprints) + (published,), guard)
    return path
