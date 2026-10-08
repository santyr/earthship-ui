"""Passive bounded ELF64 dependency metadata; never loads or executes images.

Explicit library bindings describe a reviewed closure. Symbol compatibility,
search-order correctness, lazy dlopen and cold relocation remain separate gates.
"""
import os
from pathlib import Path
import stat
import struct

MAX_NATIVE_FILES = 2048
MAX_IMAGE_BYTES = 256000000
MAX_METADATA_BYTES = 1000000


def elf_dependencies(path):
    path = Path(path)
    if not path.is_absolute() or path.resolve() != path: raise ValueError('resolved native image required')
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid not in (0, os.getuid()) or
            info.st_mode & 0o022 or not 64 <= info.st_size <= MAX_IMAGE_BYTES):
        raise ValueError('bounded safe native image required')
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(descriptor)
        if (before.st_dev, before.st_ino) != (info.st_dev, info.st_ino): raise ValueError('native image changed')
        def read(offset, count):
            if not 0 <= offset <= info.st_size or not 0 <= count <= MAX_METADATA_BYTES or offset+count > info.st_size:
                raise ValueError('ELF metadata exceeds image or read bound')
            value = os.pread(descriptor, count, offset)
            if len(value) != count: raise ValueError('truncated ELF metadata')
            return value
        header = read(0, 64)
        if header[:4] != b'\x7fELF' or header[4] != 2 or header[5] not in (1, 2) or header[6] != 1:
            raise ValueError('supported ELF64 image required')
        endian = '<' if header[5] == 1 else '>'
        kind, machine, version, _, phoff, _, _, ehsize, phsize, phcount, _, _, _ = struct.unpack(endian+'HHIQQQIHHHHHH', header[16:])
        if kind not in (2, 3) or version != 1 or ehsize != 64 or phsize != 56 or not 1 <= phcount <= 256:
            raise ValueError('ELF program header contract invalid')
        table = read(phoff, phsize*phcount); loads = []; dynamic = None; interpreter = None
        for index in range(phcount):
            ptype, _, offset, address, _, length, _, _ = struct.unpack_from(endian+'IIQQQQQQ', table, index*56)
            if offset+length > info.st_size: raise ValueError('ELF segment outside image')
            if ptype == 1: loads.append((offset, address, length))
            elif ptype == 2:
                if dynamic is not None or not length or length % 16: raise ValueError('invalid ELF dynamic segment')
                dynamic = read(offset, length)
            elif ptype == 3:
                if interpreter is not None or not 1 <= length <= 1024: raise ValueError('invalid ELF interpreter segment')
                raw = read(offset, length)
                if not raw.endswith(b'\0') or b'\0' in raw[:-1]: raise ValueError('invalid interpreter name')
                interpreter = raw[:-1].decode('utf-8')
                if not interpreter.startswith('/'): raise ValueError('absolute ELF interpreter required')
        needed = []; strings = {}; names = []
        if dynamic is not None:
            ended = False
            for index in range(len(dynamic)//16):
                tag, value = struct.unpack_from(endian+'qQ', dynamic, index*16)
                if tag == 0: ended = True; break
                if tag == 1: needed.append(value)
                elif tag in (5, 10):
                    if tag in strings: raise ValueError('ambiguous ELF string table')
                    strings[tag] = value
            if not ended or len(needed) > 256: raise ValueError('unterminated or oversized ELF dependencies')
            if needed:
                if set(strings) != {5, 10} or not 1 <= strings[10] <= MAX_METADATA_BYTES:
                    raise ValueError('bounded dependency string table required')
                spans = [offset+strings[5]-address for offset, address, length in loads
                    if address <= strings[5] and strings[5]+strings[10] <= address+length]
                if len(spans) != 1: raise ValueError('unbound ELF dependency string table')
                data = read(spans[0], strings[10])
                for offset in needed:
                    if offset >= len(data): raise ValueError('dependency name offset invalid')
                    end = data.find(b'\0', offset)
                    if end < 0 or not 1 <= end-offset <= 512: raise ValueError('bounded terminated dependency name required')
                    name = data[offset:end].decode('utf-8')
                    if any(ord(character) < 32 for character in name): raise ValueError('invalid dependency name')
                    names.append(name)
        after = os.fstat(descriptor)
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError('native image changed during metadata read')
        return dict(elf_class=64, machine=machine, byte_order='little' if endian == '<' else 'big',
            needed=list(dict.fromkeys(names)), interpreter=interpreter)
    except (UnicodeDecodeError, struct.error) as error:
        raise ValueError('invalid ELF metadata encoding') from error
    finally: os.close(descriptor)


def native_dependency_closure(seeds, *, libraries):
    """Traverse explicit native library bindings without executing any image."""
    if not isinstance(seeds, (list, tuple)) or not 1 <= len(seeds) <= MAX_NATIVE_FILES:
        raise ValueError('explicit bounded native roots required')
    if not isinstance(libraries, dict) or len(libraries) > 20000:
        raise ValueError('explicit bounded library bindings required')
    for name in libraries:
        if not isinstance(name, str) or not 1 <= len(name) <= 1024: raise ValueError('library binding name invalid')
    files = {}; queue = [(Path(path), None) for path in seeds]; architecture = None
    while queue:
        path, expected = queue.pop()
        if len(files) >= MAX_NATIVE_FILES and str(path) not in files: raise ValueError('native closure exceeds file bound')
        metadata = files.get(str(path)) or elf_dependencies(path)
        abi = (metadata['elf_class'], metadata['machine'], metadata['byte_order'])
        if architecture is None: architecture = abi
        if abi != architecture or expected is not None and abi != expected: raise ValueError('native dependency architecture differs')
        if str(path) in files: continue
        files[str(path)] = metadata
        references = [*metadata['needed']]
        if metadata['interpreter'] is not None: references.append(metadata['interpreter'])
        for name in references:
            if name not in libraries: raise ValueError('native dependency lacks explicit library binding')
            queue.append((Path(libraries[name]), abi))
    return dict(schema='earthship-thermal-native-closure/v1', files=files,
        cold_environment_qualified=False, production_qualified=False)
