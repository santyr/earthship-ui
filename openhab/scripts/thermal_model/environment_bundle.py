"""Stream an explicit dependency-file inventory into immutable private blobs.

Retaining declared bytes does not attest inventory completeness, relocation,
cold execution, restored journal compatibility or production readiness.
"""
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
from time import monotonic, sleep
from uuid import uuid4

from .forcing_capture import _canonical, _private_directory
from .origin_capture import _object
from .runtime_bundle import _write_private, _sync_directory
from .rollback import _rename_new

SCHEMA = 'earthship-thermal-environment-files/v1'
FIELDS = {'schema', 'files', 'total_bytes', 'cold_environment_qualified', 'production_qualified', 'bundle_sha256'}
MAX_FILES = 20000
MAX_FILE_BYTES = 256000000
MAX_TOTAL_BYTES = 1000000000
MAX_MANIFEST_BYTES = 8000000
CHUNK = 262144


def _name(value):
    if not isinstance(value, str): raise ValueError('absolute dependency path required')
    path = PurePosixPath(value)
    if not path.is_absolute() or str(path) != value or '..' in path.parts or len(value.encode()) > 1024:
        raise ValueError('normalized bounded dependency path required')
    return value


class _ReadPacer:
    def __init__(self, rate):
        if type(rate) is not int or rate <= 0:
            raise ValueError('positive integer read bytes per second required')
        self.rate = rate
        self.deadline = monotonic()

    def reserve(self, size):
        if size <= 0: return
        now = monotonic()
        # Idle time never earns credit for a later burst.
        self.deadline = max(now, self.deadline) + size / self.rate
        sleep(self.deadline - now)


def _pacer(rate):
    return None if rate is None else _ReadPacer(rate)


def _file_pin(path, *, private=False, destination=None, pace=None):
    path = Path(path)
    if not path.is_absolute() or path.resolve() != path: raise ValueError('resolved dependency source required')
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE_BYTES or
            info.st_uid not in ((os.getuid(),) if private else (0, os.getuid())) or
            info.st_mode & 0o022 or private and (stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1)):
        raise ValueError('bounded safe dependency file required')
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    output = None
    try:
        before = os.fstat(descriptor)
        if (before.st_dev, before.st_ino) != (info.st_dev, info.st_ino): raise ValueError('dependency changed before read')
        if destination is not None:
            output = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        digest = sha256(); size = 0
        while True:
            if pace is not None: pace.reserve(min(CHUNK, max(0, info.st_size-size)))
            chunk = os.read(descriptor, CHUNK)
            if not chunk: break
            size += len(chunk)
            if size > MAX_FILE_BYTES: raise ValueError('dependency exceeds file bound')
            digest.update(chunk)
            if output is not None:
                view = memoryview(chunk)
                while view:
                    wrote = os.write(output, view)
                    if wrote <= 0: raise OSError('dependency copy stalled')
                    view = view[wrote:]
        after = os.fstat(descriptor)
        if (size != info.st_size or (before.st_size, before.st_mtime_ns, before.st_ctime_ns) !=
                (after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
            raise ValueError('dependency changed during read')
        if output is not None: os.fsync(output)
        return dict(sha256=digest.hexdigest(), bytes=size)
    finally:
        os.close(descriptor)
        if output is not None: os.close(output)


def _copy_file(source, destination, *, pace=None):
    return _file_pin(source, destination=destination, pace=pace)


def _read(directory, *, addressed, pace=None):
    root = _private_directory(Path(directory))
    if {entry.name for entry in root.iterdir()} != {'manifest.json', 'blobs'}:
        raise ValueError('exact environment bundle membership required')
    manifest = root/'manifest.json'
    if manifest.stat().st_size > MAX_MANIFEST_BYTES: raise ValueError('environment manifest exceeds bound')
    _file_pin(manifest, private=True, pace=pace)
    def constant(_): raise ValueError('nonfinite environment manifest')
    descriptor = os.open(manifest, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        parts = []; count = 0; expected_size = os.fstat(descriptor).st_size
        while count <= MAX_MANIFEST_BYTES:
            if pace is not None: pace.reserve(min(CHUNK, max(0, expected_size-count)))
            chunk = os.read(descriptor, min(CHUNK, MAX_MANIFEST_BYTES+1-count))
            if not chunk: break
            parts.append(chunk); count += len(chunk)
        raw = b''.join(parts)
    finally: os.close(descriptor)
    if len(raw) > MAX_MANIFEST_BYTES: raise ValueError('environment manifest exceeds bound')
    value = json.loads(raw, object_pairs_hook=_object, parse_constant=constant)
    if (not isinstance(value, dict) or set(value) != FIELDS or value['schema'] != SCHEMA or
            value['cold_environment_qualified'] is not False or value['production_qualified'] is not False):
        raise ValueError('closed dependency retention manifest required')
    digest = sha256(_canonical({key: item for key, item in value.items() if key != 'bundle_sha256'})).hexdigest()
    if value['bundle_sha256'] != digest or addressed and root.name != digest:
        raise ValueError('environment manifest identity differs')
    files = value['files']; total = 0; expected = set()
    if not isinstance(files, dict) or not 1 <= len(files) <= MAX_FILES: raise ValueError('bounded dependency inventory required')
    for name, entry in files.items():
        _name(name)
        if (not isinstance(entry, dict) or set(entry) != {'sha256', 'bytes'} or
                type(entry['bytes']) is not int or not 0 <= entry['bytes'] <= MAX_FILE_BYTES or
                not isinstance(entry['sha256'], str) or len(entry['sha256']) != 64 or
                any(character not in '0123456789abcdef' for character in entry['sha256'])):
            raise ValueError('exact dependency file identity required')
        total += entry['bytes']; expected.add(entry['sha256'])
    if total > MAX_TOTAL_BYTES or type(value['total_bytes']) is not int or value['total_bytes'] != total:
        raise ValueError('environment inventory size differs or exceeds bound')
    blobs = _private_directory(root/'blobs')
    if {entry.name for entry in blobs.iterdir()} != expected: raise ValueError('environment blobs missing or extra')
    verified = {}
    for name in expected: verified[name] = _file_pin(blobs/name, private=True, pace=pace)
    if any(verified[entry['sha256']] != entry for entry in files.values()):
        raise ValueError('retained dependency bytes differ')
    return value


def read_environment_bundle(directory, *, max_read_bytes_per_second=None):
    return _read(directory, addressed=True, pace=_pacer(max_read_bytes_per_second))


def capture_environment_files(directory, files, *, max_read_bytes_per_second=None):
    """Retain explicit files; optional aggregate pacing covers all read passes.

    The limit is bytes read per second, including integrity rechecks. Metadata
    operations and fsync latency are not a kernel-enforced device I/O quota.
    """
    pace = _pacer(max_read_bytes_per_second)
    root = _private_directory(Path(directory))
    if not isinstance(files, dict) or not 1 <= len(files) <= MAX_FILES: raise ValueError('explicit bounded dependency map required')
    pins = {}; total = 0
    for name, source in files.items():
        _name(name); pin = _file_pin(Path(source), pace=pace); total += pin['bytes']
        if total > MAX_TOTAL_BYTES: raise ValueError('environment inventory exceeds total bound')
        pins[name] = pin
    body = dict(schema=SCHEMA, files=pins, total_bytes=total, cold_environment_qualified=False, production_qualified=False)
    body['bundle_sha256'] = sha256(_canonical(body)).hexdigest()
    raw = _canonical(body)
    if len(raw) > MAX_MANIFEST_BYTES: raise ValueError('environment manifest exceeds bound')
    stage = root/('.environment-'+uuid4().hex); stage.mkdir(mode=0o700)
    try:
        (stage/'blobs').mkdir(mode=0o700)
        copied = set()
        for name, source in files.items():
            expected = pins[name]
            if expected['sha256'] not in copied:
                options = {} if pace is None else {'pace': pace}
                if _copy_file(Path(source), stage/'blobs'/expected['sha256'], **options) != expected:
                    raise ValueError('dependency changed during capture')
                copied.add(expected['sha256'])
        for name, source in files.items():
            if _file_pin(Path(source), pace=pace) != pins[name]: raise ValueError('dependency changed across capture')
        _write_private(stage/'manifest.json', raw)
        _read(stage, addressed=False, pace=pace)
        _sync_directory(stage/'blobs'); _sync_directory(stage)
        target = root/body['bundle_sha256']
        try: _rename_new(stage, target)
        except ValueError:
            if not target.exists() or _read(target, addressed=True, pace=pace) != body: raise
        _sync_directory(root)
        return target
    finally:
        if stage.exists(): shutil.rmtree(stage)


def inventory_environment_files(roots, *, aliases):
    """List reviewed library trees, following only explicitly bound aliases.

    Bytecode cache directories are omitted. This is a finite file inventory,
    not a claim that the supplied roots cover every runtime dependency.
    """
    if not isinstance(roots, (list, tuple)) or not 1 <= len(roots) <= 16:
        raise ValueError('explicit bounded library roots required')
    if not isinstance(aliases, dict) or len(aliases) > MAX_FILES:
        raise ValueError('explicit bounded dependency aliases required')
    approved = {_name(name): Path(target) for name, target in aliases.items()}
    for target in approved.values():
        _name(str(target))
        if target.resolve() != target: raise ValueError('fully resolved alias destination required')
    inventory = {}; used = set(); visited = 0

    def visit(logical, source, ancestors):
        nonlocal visited
        _name(str(logical)); _name(str(source))
        visited += 1
        if visited > MAX_FILES*3 or len(ancestors) > 32:
            raise ValueError('dependency traversal exceeds bound')
        before = source.lstat()
        if stat.S_ISLNK(before.st_mode):
            name = str(logical)
            if name not in approved or source.resolve(strict=True) != approved[name]:
                raise ValueError('unreviewed or changed dependency alias')
            used.add(name)
            return visit(logical, approved[name], ancestors)
        if (source.resolve() != source or before.st_uid not in (0, os.getuid()) or
                before.st_mode & 0o022):
            raise ValueError('safe resolved library entry required')
        if stat.S_ISDIR(before.st_mode):
            identity = (before.st_dev, before.st_ino)
            if identity in ancestors: raise ValueError('dependency directory alias cycle')
            for child in source.iterdir():
                if child.name == '__pycache__' and child.is_dir(): continue
                visit(logical/child.name, child, (*ancestors, identity))
            after = source.lstat()
            if (before.st_dev, before.st_ino, before.st_mtime_ns, before.st_ctime_ns) != (
                    after.st_dev, after.st_ino, after.st_mtime_ns, after.st_ctime_ns):
                raise ValueError('dependency directory changed during inventory')
        elif stat.S_ISREG(before.st_mode):
            if before.st_size > MAX_FILE_BYTES: raise ValueError('dependency exceeds file bound')
            name = str(logical)
            if name in inventory: raise ValueError('overlapping dependency roots')
            inventory[name] = source
            if len(inventory) > MAX_FILES: raise ValueError('dependency file count exceeds bound')
        else: raise ValueError('unsupported dependency entry type')

    for root in roots:
        root = Path(root); _name(str(root))
        if not root.is_dir(): raise ValueError('library root must be a directory')
        visit(root, root, ())
    if used != set(approved): raise ValueError('unused dependency alias declaration')
    return inventory


RESTORE_SCHEMA = 'earthship-thermal-environment-restore/v1'
RESTORE_FIELDS = {'schema', 'bundle_sha256', 'installed', 'cold_environment_qualified', 'production_qualified'}


def _mirror_paths(files):
    names = set(files)
    for name in names:
        path = PurePosixPath(_name(name))
        if len(path.parts) < 2 or any(str(parent) in names for parent in path.parents):
            raise ValueError('dependency file paths conflict with mirror directories')
    return {name: Path(*PurePosixPath(name).parts[1:]) for name in names}


def _mirror_members(root):
    members = set(); pending = [root]; count = 0
    while pending:
        current = _private_directory(pending.pop())
        for entry in current.iterdir():
            count += 1
            if count > MAX_FILES*10: raise ValueError('environment mirror exceeds entry bound')
            info = entry.lstat()
            if stat.S_ISDIR(info.st_mode):
                members.add(str(entry.relative_to(root))+'/'); pending.append(entry)
            elif stat.S_ISREG(info.st_mode): members.add(str(entry.relative_to(root)))
            else: raise ValueError('environment mirror contains unsupported entry')
    return members


def verify_environment_restore(bundle, directory, *, max_read_bytes_per_second=None):
    """Verify an isolated mirror; never treats byte recovery as cold eligibility."""
    return _verify_environment_restore(bundle, directory, pace=_pacer(max_read_bytes_per_second))


def _verify_environment_restore(bundle, directory, *, pace):
    original = _read(bundle, addressed=True, pace=pace)
    root = _private_directory(Path(directory))
    if {entry.name for entry in root.iterdir()} != {'restore.json', 'rootfs'}:
        raise ValueError('exact isolated environment recovery required')
    receipt = root/'restore.json'; _file_pin(receipt, private=True, pace=pace)
    descriptor = os.open(receipt, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        if pace is not None: pace.reserve(min(8193, os.fstat(descriptor).st_size))
        with os.fdopen(descriptor, 'rb', closefd=False) as stream: raw = stream.read(8193)
    finally: os.close(descriptor)
    if len(raw) > 8192: raise ValueError('environment recovery receipt exceeds bound')
    def constant(_): raise ValueError('nonfinite recovery receipt')
    value = json.loads(raw, object_pairs_hook=_object, parse_constant=constant)
    if (not isinstance(value, dict) or set(value) != RESTORE_FIELDS or value['schema'] != RESTORE_SCHEMA or
            value['bundle_sha256'] != original['bundle_sha256'] or
            any(value[name] is not False for name in ('installed', 'cold_environment_qualified', 'production_qualified'))):
        raise ValueError('environment recovery cannot claim installation or qualification')
    paths = _mirror_paths(original['files']); mirror = _private_directory(root/'rootfs')
    expected_members = {str(relative) for relative in paths.values()}
    expected_members.update(str(parent)+'/' for relative in paths.values() for parent in relative.parents if parent != Path('.'))
    if _mirror_members(mirror) != expected_members:
        raise ValueError('environment recovery has missing or extra files')
    for name, relative in paths.items():
        if _file_pin(mirror/relative, private=True, pace=pace) != original['files'][name]:
            raise ValueError('prepared dependency bytes differ from retained bundle')
    if _read(bundle, addressed=True, pace=pace) != original: raise ValueError('retained environment changed during recovery verification')
    return value


def prepare_environment_restore(bundle, destination, *, max_read_bytes_per_second=None):
    """Materialize retained bytes in a new private mirror, without live replacement."""
    pace = _pacer(max_read_bytes_per_second)
    original = _read(bundle, addressed=True, pace=pace); paths = _mirror_paths(original['files'])
    destination = Path(destination)
    if not destination.is_absolute() or destination.resolve() != destination:
        raise ValueError('absolute isolated recovery path required')
    parent = _private_directory(destination.parent)
    if destination.exists() or destination.is_symlink(): raise ValueError('environment recovery destination already exists')
    stage = parent/('.environment-restore-'+uuid4().hex); stage.mkdir(mode=0o700)
    try:
        mirror = stage/'rootfs'; mirror.mkdir(mode=0o700)
        for name, relative in paths.items():
            target = mirror/relative
            current = mirror
            for part in relative.parts[:-1]:
                current = current/part
                try: current.mkdir(mode=0o700)
                except FileExistsError: _private_directory(current)
            expected = original['files'][name]
            options = {} if pace is None else {'pace': pace}
            if _copy_file(Path(bundle)/'blobs'/expected['sha256'], target, **options) != expected:
                raise ValueError('retained dependency changed while preparing recovery')
        value = dict(schema=RESTORE_SCHEMA, bundle_sha256=original['bundle_sha256'], installed=False,
            cold_environment_qualified=False, production_qualified=False)
        _write_private(stage/'restore.json', _canonical(value))
        _verify_environment_restore(bundle, stage, pace=pace)
        for current, _, _ in os.walk(mirror, topdown=False): _sync_directory(Path(current))
        _sync_directory(stage); _rename_new(stage, destination); _sync_directory(parent)
        return value
    finally:
        if stage.exists(): shutil.rmtree(stage)
