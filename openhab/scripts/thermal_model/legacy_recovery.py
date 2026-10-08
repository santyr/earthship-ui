"""Preserve v4 recovery bytes without decoding them as v5 or authorizing install.

Referenced environment archives remain required recovery inputs. This component
checks preservation and publication identity, not legacy numerical eligibility.
The pinned legacy reader, cold runtime and restored journal must qualify separately.
"""
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
from uuid import uuid4

from .environment_bundle import _read, _pacer, _copy_file, _name, _mirror_members
from .forcing_capture import _canonical, _private_directory
from .origin_capture import _object
from .runtime_bundle import _owned_bytes, _write_private, _sync_directory, _path
from .rollback import REASONS, _rename_new
from .graduation_policy import _utc, _sha
from .schema import validate_shadow_output

SCHEMA = 'earthship-thermal-legacy-recovery-generation/v1'
FLAGS = {'artifact_reader_qualified', 'cold_runtime_qualified', 'journal_qualified', 'installed', 'automatic_actuation'}
FIELDS = {'schema', 'artifact_sha256', 'output_sha256', 'source_root', 'source_bundle',
    'environment_bundles', 'revision_paths', 'runtime_revision', 'interpreter',
    'native_bindings', 'reason', 'created_at', 'generation_sha256'} | FLAGS
ARTIFACT_FIELDS = {'schema', 'code_revision', 'created_at', 'trained_from',
    'trained_through', 'behavior', 'dynamics', 'data_manifest', 'metrics'}


def _digest(value):
    return sha256(_canonical(value)).hexdigest()


def _document(raw):
    def refuse(_): raise ValueError('nonfinite legacy recovery document')
    return json.loads(raw, object_pairs_hook=_object, parse_constant=refuse)


def _pair(artifact_raw, output_raw):
    artifact = _document(artifact_raw); output = _document(output_raw)
    if (not isinstance(artifact, dict) or set(artifact) != ARTIFACT_FIELDS or
            artifact['schema'] != 'earthship-thermal-model/v4' or
            any(not isinstance(artifact[name], dict) for name in ('behavior', 'dynamics', 'data_manifest', 'metrics'))):
        raise ValueError('original v4 artifact shape required')
    validate_shadow_output(output)
    if output['confidence']['grade'] == 'unavailable': raise ValueError('available historical publication required')
    model = output['model']
    if (model['codeRevision'] != artifact['code_revision'] or
            _utc(model['createdAt']) != _utc(artifact['created_at']).replace(microsecond=0) or
            _utc(model['trainedThrough']) != _utc(artifact['trained_through']).replace(microsecond=0) or
            not _utc(artifact['trained_from']) <= _utc(artifact['trained_through']) <= _utc(artifact['created_at']) <= _utc(output['generatedAt'])):
        raise ValueError('original legacy artifact/publication identity differs')
    return output


def _paced_owned_bytes(path, maximum, pace):
    # Reserve the complete read bound before I/O. This remains conservative if
    # the file changes size between metadata inspection and the guarded read.
    if pace is not None: pace.reserve(maximum)
    return _owned_bytes(path, maximum)


def _environment_map(environments):
    if not isinstance(environments, dict) or not 1 <= len(environments) <= 8:
        raise ValueError('bounded retained environment references required')
    if any(not isinstance(label, str) or re.fullmatch('[a-z][a-z0-9_]{0,31}', label) is None for label in environments):
        raise ValueError('bounded environment labels required')


def _reference(path, pace):
    path = Path(path); _name(str(path))
    value = _read(path, addressed=True, pace=pace)
    return dict(path=str(path), sha256=value['bundle_sha256']), value


def _inputs(record, pace):
    if (record['reason'] not in REASONS or _utc(record['created_at']) > datetime.now(timezone.utc) or
            any(record[name] is not False for name in FLAGS)):
        raise ValueError('closed legacy preparation with explicit reason required')
    environments = record['environment_bundles']
    _environment_map(environments)
    refs = [record['source_bundle'], *environments.values()]; values = []; combined = {}
    for reference in refs:
        if not isinstance(reference, dict) or set(reference) != {'path', 'sha256'}:
            raise ValueError('exact archive reference required')
        actual, value = _reference(reference['path'], pace)
        if actual != reference: raise ValueError('retained archive identity differs')
        values.append(value)
        for logical, pin in value['files'].items():
            if logical in combined and combined[logical] != pin: raise ValueError('conflicting retained dependency versions')
            combined[logical] = pin
    interpreter = _name(record['interpreter'])
    if interpreter not in combined: raise ValueError('interpreter bytes not retained')
    bindings = record['native_bindings']
    if not isinstance(bindings, dict) or len(bindings) > 2048: raise ValueError('bounded native bindings required')
    for name, target in bindings.items():
        if (not isinstance(name, str) or not 1 <= len(name) <= 1024 or any(ord(char) < 32 for char in name) or
                not name.startswith('/') and Path(name).name != name):
            raise ValueError('native binding name invalid')
        if name.startswith('/'): _name(name)
        if _name(target) not in combined: raise ValueError('native binding bytes not retained')
    root = _name(record['source_root']); prefix = root.rstrip('/')+'/'
    sources = values[0]['files']
    if not 1 <= len(sources) <= 128: raise ValueError('bounded original source closure required')
    relative = {}
    for logical, pin in sources.items():
        if not logical.startswith(prefix): raise ValueError('source outside original runtime root')
        relative[_path(logical[len(prefix):])] = pin
    required = {'thermal_intel.py', 'thermal_model/artifacts.py', 'thermal_model/schema.py', 'thermal_model/pipeline.py', 'thermal_model/forcing_capture.py'}
    if not required <= set(relative): raise ValueError('original reader/publication source missing')
    paths = record['revision_paths']
    if (not isinstance(paths, list) or not 1 <= len(paths) <= 63 or
            any(not isinstance(name, str) for name in paths) or len(set(paths)) != len(paths) or
            'thermal_intel.py' not in paths or not set(paths) <= set(relative)):
        raise ValueError('original ordered revision closure required')
    digest = sha256(); archive = Path(record['source_bundle']['path'])/'blobs'
    for name in paths:
        _path(name)
        if pace is not None: pace.reserve(relative[name]['bytes'])
        raw = _owned_bytes(archive/relative[name]['sha256'], 2000000); encoded = name.encode()
        digest.update(len(encoded).to_bytes(4, 'big')); digest.update(encoded)
        digest.update(len(raw).to_bytes(8, 'big')); digest.update(raw)
    if record['runtime_revision'] is not None and record['runtime_revision'] != digest.hexdigest():
        raise ValueError('original runtime revision differs')
    return relative, digest.hexdigest()


def _verify(directory, pace):
    root = _private_directory(Path(directory))
    if {entry.name for entry in root.iterdir()} != {'manifest.json', 'models', 'runtime', 'last-shadow.json'}:
        raise ValueError('exact legacy generation required')
    record = _document(_paced_owned_bytes(root/'manifest.json', 128000, pace))
    if not isinstance(record, dict) or set(record) != FIELDS or record['schema'] != SCHEMA:
        raise ValueError('closed legacy generation schema required')
    if _digest({key: value for key, value in record.items() if key != 'generation_sha256'}) != record['generation_sha256']:
        raise ValueError('legacy generation manifest changed')
    _sha(record['runtime_revision'])
    sources, _ = _inputs(record, pace)
    models = _private_directory(root/'models')
    if {entry.name for entry in models.iterdir()} != {'accepted.json'}: raise ValueError('exact legacy model membership required')
    artifact = _paced_owned_bytes(models/'accepted.json', 4000000, pace); output = _paced_owned_bytes(root/'last-shadow.json', 16384, pace)
    if sha256(artifact).hexdigest() != record['artifact_sha256'] or sha256(output).hexdigest() != record['output_sha256']:
        raise ValueError('original legacy pair bytes changed')
    if _utc(_pair(artifact, output)['generatedAt']) > _utc(record['created_at']):
        raise ValueError('historical publication was unavailable at preparation')
    expected = set(sources)
    expected.update(str(parent)+'/' for name in sources for parent in Path(name).parents if parent != Path('.'))
    if _mirror_members(root/'runtime') != expected: raise ValueError('legacy runtime membership differs')
    for name, pin in sources.items():
        if pace is not None: pace.reserve(pin['bytes'])
        raw = _owned_bytes(root/'runtime'/name, 2000000)
        if sha256(raw).hexdigest() != pin['sha256'] or len(raw) != pin['bytes']: raise ValueError('legacy runtime bytes changed')
    return record


def verify_legacy_generation(directory, *, max_read_bytes_per_second=None):
    return _verify(directory, _pacer(max_read_bytes_per_second))


def prepare_legacy_generation(destination, *, artifact_path, output_path, source_bundle,
        source_root, revision_paths, environment_bundles, interpreter, native_bindings,
        reason, max_read_bytes_per_second=None):
    """Prepare original v4 bytes in a new generation; never execute or install."""
    pace = _pacer(max_read_bytes_per_second)
    destination = Path(destination); _name(str(destination))
    if destination.resolve() != destination: raise ValueError('resolved private generation path required')
    parent = _private_directory(destination.parent)
    if destination.exists() or destination.is_symlink(): raise ValueError('legacy destination already exists')
    _environment_map(environment_bundles)
    artifact = _paced_owned_bytes(Path(artifact_path), 4000000, pace); output = _paced_owned_bytes(Path(output_path), 16384, pace)
    _pair(artifact, output)
    source_ref, _ = _reference(source_bundle, pace)
    refs = {name: _reference(path, pace)[0] for name, path in environment_bundles.items()}
    record = dict(schema=SCHEMA, artifact_sha256=sha256(artifact).hexdigest(), output_sha256=sha256(output).hexdigest(),
        source_root=source_root, source_bundle=source_ref, environment_bundles=refs,
        revision_paths=list(revision_paths), runtime_revision=None, interpreter=interpreter,
        native_bindings=dict(native_bindings), reason=reason, created_at=datetime.now(timezone.utc).isoformat(),
        **{name: False for name in FLAGS})
    sources, record['runtime_revision'] = _inputs(record, pace)
    record['generation_sha256'] = _digest(record)
    stage = parent/('.legacy-recovery-'+uuid4().hex); stage.mkdir(mode=0o700)
    try:
        (stage/'models').mkdir(mode=0o700); (stage/'runtime').mkdir(mode=0o700)
        _write_private(stage/'models/accepted.json', artifact); _write_private(stage/'last-shadow.json', output)
        for name, pin in sources.items():
            target = stage/'runtime'/name
            current = stage/'runtime'
            for part in Path(name).parts[:-1]:
                current = current/part; current.mkdir(mode=0o700, exist_ok=True); _private_directory(current)
            if _copy_file(Path(source_bundle)/'blobs'/pin['sha256'], target, pace=pace) != pin:
                raise ValueError('source bytes changed while preparing legacy generation')
        _write_private(stage/'manifest.json', _canonical(record)); _verify(stage, pace)
        for current, _, _ in os.walk(stage, topdown=False): _sync_directory(Path(current))
        _rename_new(stage, destination); _sync_directory(parent)
        return record
    finally:
        if stage.exists(): shutil.rmtree(stage)
