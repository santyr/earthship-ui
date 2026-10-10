#!/usr/bin/env python3
"""Check private settings or replay raw calibration and freeze a development candidate."""
import argparse
from copy import deepcopy
from datetime import datetime,timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
from time import monotonic

SCHEMA='earthship-installed-shade-calibration-config/v1'
FIELDS={'schema','base_candidate_path','base_runtime_bundle_path','runtime_bundle_path',
    'base_runtime_sha256','runtime_sha256','raw_sources_path','raw_sources_sha256',
    'calibration_start','calibration_end','regimes','output_directory','shared_lock'}


def _clock():return datetime.now(timezone.utc)


def _resource_preflight():
    from thermal_installed_intel import _resource_preflight as verify
    verify()


def _private_bytes(path,maximum):
    """Stable owned-private read without importing numerical/runtime modules."""
    from thermal_model.installed_shade_training import _path
    path=_path(str(path));before=path.lstat()
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
    try:
        opened=os.fstat(fd)
        if (not stat.S_ISREG(opened.st_mode) or opened.st_uid!=os.getuid() or
                stat.S_IMODE(opened.st_mode)!=0o600 or opened.st_nlink!=1 or
                (opened.st_dev,opened.st_ino)!=(before.st_dev,before.st_ino)):
            raise ValueError('private source replaced before read')
        with os.fdopen(fd,'rb',closefd=False) as source:raw=source.read(maximum+1)
        after=os.fstat(fd);current=path.lstat()
        if (path.resolve()!=path or (current.st_dev,current.st_ino)!=(opened.st_dev,opened.st_ino) or
                (opened.st_size,opened.st_mtime_ns,opened.st_ctime_ns)!=(after.st_size,after.st_mtime_ns,after.st_ctime_ns)):
            raise ValueError('private source changed during read')
    finally:os.close(fd)
    if len(raw)>maximum:raise ValueError('bounded private source required')
    return raw


def _time(value):
    if not isinstance(value,str):raise ValueError('aware elapsed calibration clock required')
    at=datetime.fromisoformat(value)
    if at.utcoffset() is None:raise ValueError('aware elapsed calibration clock required')
    return at.astimezone(timezone.utc)


def _index(references):
    if not isinstance(references,list) or not 1<=len(references)<=10000:raise ValueError('bounded original source index required')
    for reference in references:
        if not isinstance(reference,dict) or set(reference)!={'raw_score_sources_path'}:raise ValueError('original raw source reference required')
        name=reference['raw_score_sources_path']
        if not isinstance(name,str) or not 1<=len(name)<=1024:raise ValueError('bounded original raw source path required')
        path=Path(name)
        if not path.is_absolute() or path.resolve()!=path:raise ValueError('resolved absolute original raw source required')


def load_settings(path):
    from thermal_model.installed_shade_training import _path,_object
    path=_path(str(path));raw=_private_bytes(path,16384)
    def reject(_):raise ValueError('nonfinite configuration refused')
    value=json.loads(raw,object_pairs_hook=_object,parse_constant=reject)
    if not isinstance(value,dict) or set(value)!=FIELDS or value['schema']!=SCHEMA:
        raise ValueError('closed raw calibration configuration required')
    for key in ('base_runtime_sha256','runtime_sha256','raw_sources_sha256'):
        if not isinstance(value[key],str) or re.fullmatch('[0-9a-f]{64}',value[key]) is None:raise ValueError('pinned original identity required')
    for key in ('base_candidate_path','raw_sources_path','shared_lock'):_path(value[key])
    for key in ('base_runtime_bundle_path','runtime_bundle_path','output_directory'):_path(value[key],directory=True)
    if not _time(value['calibration_start'])<_time(value['calibration_end'])<=_clock():
        raise ValueError('elapsed separate calibration interval required')
    if (not isinstance(value['regimes'],list) or not value['regimes'] or len(value['regimes'])>3 or
            any(type(item) is not str or item not in ('warm','shoulder','winter') for item in value['regimes']) or
            len(set(value['regimes']))!=len(value['regimes'])):raise ValueError('closed distinct regimes required')
    sources=_private_bytes(Path(value['raw_sources_path']),4000000)
    if sha256(sources).hexdigest()!=value['raw_sources_sha256']:raise ValueError('original calibration index changed')
    references=json.loads(sources,object_pairs_hook=_object,parse_constant=reject)
    _index(references)
    return deepcopy(value)


def run_calibration(settings,*,guard):
    """One shared budget begins before numerical imports or original reads."""
    from thermal_model.replay_budget import shared_replay_budget
    guard();deadline=monotonic()+85
    def remaining():
        guard();return deadline-monotonic()
    with shared_replay_budget(remaining):return _run_calibration(settings,guard=guard)


def _run_calibration(settings,*,guard):
    """Read original archives only; incomplete support cannot freeze a candidate."""
    from thermal_model.forcing_capture import _canonical
    from thermal_model.replay_budget import check_shared_budget
    from thermal_model.runtime_bundle import _owned_bytes,read_runtime_bundle
    from thermal_model.origin_capture import build_runtime_binding,_source_bytes
    from thermal_model.installed_shade_publication import RAW_RUNTIME_PATHS
    from thermal_model.installed_shade_artifact import read_candidate_bundle,_digest
    from thermal_model.training_inputs import read_training_inputs_v2
    from thermal_model import installed_shade_calibration as calibration
    from thermal_model import installed_shade_calibrated_artifact as candidates
    guard();started=_clock();root=Path(__file__).resolve().parent
    original=_owned_bytes(Path(settings['raw_sources_path']),4000000)
    if sha256(original).hexdigest()!=settings['raw_sources_sha256']:raise ValueError('original source index changed')
    # Reuse the closed index reader rather than accepting caller scalar scores.
    from thermal_model.installed_shade_score_jobs import _decode
    references=_decode(original);calibration._raw_packet_digest(references)
    base_archive=read_runtime_bundle(Path(settings['base_runtime_bundle_path']))
    archive=read_runtime_bundle(Path(settings['runtime_bundle_path']))
    base_runtime=base_archive['runtime'];runtime=archive['runtime']
    if (_digest(base_runtime)!=settings['base_runtime_sha256'] or _digest(runtime)!=settings['runtime_sha256'] or
            set(archive['revision_paths'])!=set(RAW_RUNTIME_PATHS)):raise ValueError('original complete runtime binding differs')
    command=_source_bytes(Path(__file__),maximum=65536)
    def check():
        guard()
        check_shared_budget()
        if _owned_bytes(Path(settings['raw_sources_path']),4000000)!=original:raise ValueError('original source index changed')
        if _canonical(read_runtime_bundle(Path(settings['runtime_bundle_path'])))!=_canonical(archive):raise ValueError('runtime archive changed')
        if _canonical(read_runtime_bundle(Path(settings['base_runtime_bundle_path'])))!=_canonical(base_archive):raise ValueError('base runtime archive changed')
        if _canonical(build_runtime_binding(root,archive['revision_paths']))!=_canonical(runtime):raise ValueError('executing runtime differs')
        if _source_bytes(Path(__file__),maximum=65536)!=command:raise ValueError('calibration command changed')
    check();now=_clock()
    bundle=read_candidate_bundle(Path(settings['base_candidate_path']),expected_runtime_revision=settings['base_runtime_sha256'],assessed_at=now)
    inputs=read_training_inputs_v2(Path(settings['base_candidate_path']).parent/(bundle['artifact']['source_snapshot_sha256']+'.training-inputs-v2.json'))
    if bundle['fit_evidence']['fit_gates_passed'] is not True:raise ValueError('source-qualified base fit required')
    check()
    record=calibration.build_raw_calibration(bundle=bundle,inputs=inputs,expected_runtime_revision=settings['base_runtime_sha256'],
        original_pairs=references,calibration_start=settings['calibration_start'],calibration_end=settings['calibration_end'],
        regimes=settings['regimes'],created_at=_clock())
    check();out=Path(settings['output_directory'])
    path=calibration.write_raw_calibration(out,record,bundle=bundle,inputs=inputs,expected_runtime_revision=settings['base_runtime_sha256'],
        original_pairs=references,assessed_at=_clock())
    restored=calibration.read_raw_calibration(path,expected_runtime_revision=settings['base_runtime_sha256'],assessed_at=_clock())
    if _canonical(restored)!=_canonical(record):raise ValueError('original raw calibration readback differs')
    check();result=dict(status='calibration_incomplete',calibration_executed=True,calibration_path=str(path),
        calibration_sha256=record['calibration_sha256'],release_authorized=False,production_installed=False)
    if record['summary']['complete'] is True:
        artifact=candidates.build_raw_calibrated_candidate(base_bundle=bundle,inputs=inputs,calibration=record,original_pairs=references,
            base_runtime=base_runtime,runtime=runtime,created_at=_clock())
        check()
        candidate_path=candidates.write_raw_calibrated_candidate(out,artifact,base_bundle=bundle,inputs=inputs,calibration=record,
            original_pairs=references,expected_runtime_revision=settings['runtime_sha256'],assessed_at=_clock())
        loaded=candidates.read_raw_calibrated_candidate(candidate_path,expected_runtime_revision=settings['runtime_sha256'],assessed_at=_clock())
        if _canonical(loaded['artifact'])!=_canonical(artifact):raise ValueError('original raw candidate readback differs')
        check();result.update(status='calibrated_development_candidate',candidate_path=str(candidate_path),artifact_sha256=artifact['artifact_sha256'])
    receipt=dict(schema='earthship-installed-shade-calibration-build-receipt/v1',started_at=started.isoformat(),completed_at=_clock().isoformat(),
        raw_sources_sha256=settings['raw_sources_sha256'],base_runtime_sha256=settings['base_runtime_sha256'],runtime_sha256=settings['runtime_sha256'],
        command_source=dict(sha256=sha256(command).hexdigest(),utf8=command.decode()),**result)
    receipt['receipt_sha256']=_digest(receipt);check()
    receipt_path=calibration._persist(out,receipt,receipt['receipt_sha256'],'.installed-shade-calibration-build-v1.json')
    if _owned_bytes(receipt_path,65536)!=_canonical(receipt):raise ValueError('private execution receipt differs')
    check();return dict(result,receipt_path=str(receipt_path))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--calibrate',action='store_true');args=parser.parse_args(argv)
    saved={key:os.environ.get(key) for key in ('EARTHSHIP_QUALIFICATION_FIT','EARTHSHIP_REMOTE_QUALIFICATION_FIT')}
    try:
        if args.calibrate:_resource_preflight()
        settings=load_settings(args.config)
        if not args.calibrate:
            print(json.dumps(dict(status='configuration_verified',calibration_executed=False,release_authorized=False)));return 0
        os.environ['EARTHSHIP_QUALIFICATION_FIT']='0';os.environ['EARTHSHIP_REMOTE_QUALIFICATION_FIT']='0'
        from thermal_installed_score import SharedScoreLock
        with SharedScoreLock(settings['shared_lock']) as held:result=run_calibration(settings,guard=held.verify)
        print(json.dumps(result,sort_keys=True));return 0
    except BlockingIOError:
        print(json.dumps(dict(status='busy',calibration_executed=False,release_authorized=False)));return 75
    except Exception:
        print(json.dumps(dict(status='withheld',calibration_executed=None,release_authorized=False)));return 1
    finally:
        for key,value in saved.items():
            if value is None:os.environ.pop(key,None)
            else:os.environ[key]=value


if __name__=='__main__':raise SystemExit(main())
