"""One publication's decoded points, bound to freshly read immutable originals.

The first call uses the complete original decoder. Reuse requires identical
arguments and all three original documents, with full byte reads and a stable
file/parent inventory on every call. This is not an admission or freshness rule.
"""
from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import json
from pathlib import Path
from types import FunctionType
from threading import get_ident

from weather_source_files import _read

MAX_BYTES = 8 * 1024**2
MAX_ENTRIES = 16
MAX_KEY_BYTES = 262144
_ACTIVE = ContextVar('household_production_point_reads', default=None)


def _encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _parent_identity(path):
    info = path.stat()
    return (str(path), info.st_dev, info.st_ino, info.st_mode, info.st_uid)


class _PointReads:
    def __init__(self, original, guard):
        self.original, self.guard = original, guard
        self.entries = OrderedDict()
        self.bytes = self.hits = self.misses = 0
        self.failure = None
        self.active = True
        self.owner_thread = get_ident()

    def check(self, guard):
        if self.failure is not None:
            raise self.failure
        try:
            self.guard()
            if guard is not self.guard:
                guard()
        except BaseException as error:
            self.failure = error
            self.entries.clear()
            self.bytes = 0
            raise

    def snapshot(self, selected, receipt, guard):
        root = Path(selected['state_directory'])
        paths = ((root/'production-views'/('view-'+receipt['report_sha256']+'.json'), 4096),
                 (root/'production-emissions'/(receipt['production_emission_sha256']+'.json'), 16*1024**2),
                 (root/'production-issues'/(receipt['issue_sha256']+'.json'), 16*1024**2))
        self.check(guard)
        parents = tuple(_parent_identity(p) for p in sorted({p.parent for p, _ in paths} | {root}))
        before = tuple(_identity(p.lstat()) for p, _ in paths)
        if sum(row[5] for row in before) > MAX_BYTES:
            return None
        documents = []
        for path, maximum in paths:
            self.check(guard)
            documents.append(_read(path, maximum))
        self.check(guard)
        if (tuple(_identity(p.lstat()) for p, _ in paths) != before or
                tuple(_parent_identity(Path(row[0])) for row in parents) != parents):
            raise ValueError('production point originals changed during full read')
        return (parents, before, tuple(documents))

    def read(self, selected, receipt, *, forecast, issue, available, epoch, site, timezone, guard):
        arguments = dict(forecast=forecast, issue=issue, available=available,
                         epoch=epoch, site=site, timezone=timezone, guard=guard)
        try:
            self.check(guard)
            # Preserve the original named early refusals before touching files.
            from household.control_contracts import instant
            if (selected.get('source_sensor_epoch') != epoch or
                    not instant(receipt['published_at']) <= available <= issue < instant(receipt['valid_until'])):
                return self.original(selected, receipt, **arguments)
            try:
                key = _encode(dict(selected=selected, receipt=receipt, forecast=forecast,
                                   issue=issue.isoformat(), available=available.isoformat(),
                                   epoch=epoch, site=site, timezone=timezone))
            except (TypeError, ValueError, OverflowError, RecursionError):
                return self.original(selected, receipt, **arguments)
            if len(key) > MAX_KEY_BYTES:
                return self.original(selected, receipt, **arguments)
            snapshot = self.snapshot(selected, receipt, guard)
            if snapshot is None:
                return self.original(selected, receipt, **arguments)
            entry = self.entries.get(key)
            if entry is not None and entry[0] == snapshot:
                value = json.loads(entry[1])
                self.check(guard)
                self.entries.move_to_end(key)
                self.hits += 1
                return value
            self.misses += 1
            value = self.original(selected, receipt, **arguments)
            if self.snapshot(selected, receipt, guard) != snapshot:
                raise ValueError('production point originals changed during decoding')
            self.check(guard)
            try:
                encoded = _encode(value)
            except (TypeError, ValueError, OverflowError, RecursionError):
                return value
            size = len(key) + len(encoded) + sum(map(len, snapshot[2]))
            previous = self.entries.pop(key, None)
            if previous is not None:
                self.bytes -= previous[2]
            if size <= MAX_BYTES:
                while self.entries and (self.bytes + size > MAX_BYTES or len(self.entries) >= MAX_ENTRIES):
                    _, retired = self.entries.popitem(last=False)
                    self.bytes -= retired[2]
                self.entries[key] = (snapshot, encoded, size)
                self.bytes += size
            return value
        except BaseException as error:
            self.entries.clear()
            self.bytes = 0
            raise


@contextmanager
def job_production_points(guard):
    """Install one explicit publication-local reader and always restore it."""
    if not callable(guard) or _ACTIVE.get() is not None:
        raise ValueError('one original publication guard and reader scope required')
    import production_thermal_source as source
    path = Path(__file__).absolute().with_name('production_thermal_source.py')
    original = source._points
    if (Path(source.__file__) != path or type(original) is not FunctionType or
            original.__globals__ is not source.__dict__ or Path(original.__code__.co_filename) != path):
        raise ValueError('original production point decoder required')
    state = _PointReads(original, guard)
    @wraps(original)
    def reader(*args, **kwargs):
        return state.read(*args, **kwargs) if state.active and _ACTIVE.get() is state and get_ident() == state.owner_thread else original(*args, **kwargs)
    token = _ACTIVE.set(state)
    source._points = reader
    try:
        guard()
        yield state
        state.check(guard)
    finally:
        state.active = False
        state.entries.clear()
        state.bytes = 0
        _ACTIVE.reset(token)
        if source._points is not reader:
            raise ValueError('production point reader changed during publication')
        source._points = original
