"""Bounded delivered-job discovery and provisional performance reporting."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
from time import monotonic
from uuid import uuid4
import json,os,stat
from .forcing_capture import _canonical,_private_directory
from .runtime_bundle import _owned_bytes,_write_private,_sync_directory
from .graduation_policy import _utc
from .replay_budget import shared_replay_budget,capture_source_reads
from .provisional_live import current_runtime,_phase_directory
from .provisional_artifact import read_candidate
from .provisional_forecast import read_capture,digest,persist
from .provisional_score import score,validate_pair,validate_delivery,summarize
from .installed_shade_score_inputs import ScoreReader,COMPRESSED_SOURCE_SCHEMA
from .recent_cycles import compare_v2
from thermal_installed_intel import _resource_preflight


def _clock():return datetime.now(timezone.utc)


def _load(path,maximum=65536):
    from .origin_capture import _object
    return json.loads(_owned_bytes(Path(path),maximum),object_pairs_hook=_object)


def _folders(root,prefix,now):
    root=_private_directory(Path(root));result=[]
    for offset in range(3):
        path=root/(prefix+'-'+(_utc(now)-timedelta(days=offset)).strftime('%Y%m%d'))
        if path.exists():result.append(_private_directory(path))
    return result


def _delivery(path,root):
    value=_load(path)
    if (not isinstance(value,dict) or set(value)!={'schema','issued_at','capture_path','capture_sha256','artifact_sha256','receipts','delivery_sha256'} or
            value['schema']!='earthship-provisional-thermal-delivery/v1' or value['delivery_sha256']!=digest(value,'delivery_sha256')):
        raise ValueError('original delivered forecast record required')
    original=Path(value['capture_path'])
    if not original.is_absolute() or original.resolve()!=original or not original.is_relative_to(root):raise ValueError('original capture outside archive')
    return value


def _fingerprint(path):
    path=Path(path);info=path.lstat()
    if (not path.is_absolute() or path.resolve()!=path or not stat.S_ISREG(info.st_mode) or
            info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1):
        raise ValueError('owned original monitoring source required')
    return [info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns]


def _write_report(root,report):
    root=_private_directory(Path(root));temporary=root/('.performance-'+uuid4().hex)
    try:
        _write_private(temporary,_canonical(report));os.replace(temporary,root/'latest-provisional-performance.json');_sync_directory(root)
    finally:
        if temporary.exists():temporary.unlink()


def refresh_report(settings,*,artifact_sha256,now,guard):
    markers=[]
    for folder in _folders(settings['evidence_directory'],'scores',now):markers.extend(folder.glob('*.provisional-completion-v1.json'))
    if len(markers)>4096:raise ValueError('bounded recent performance inventory required')
    markers=sorted(markers,key=lambda p:p.stat().st_mtime_ns,reverse=True)[:256]
    pairs=[]
    for marker in markers:
        guard();completion=_load(marker)
        if completion.get('completion_sha256')!=digest(completion,'completion_sha256'):raise ValueError('original completion identity differs')
        path=Path(completion['pair_path'])
        if not path.is_absolute() or path.resolve()!=path or not path.is_relative_to(Path(settings['evidence_directory'])):raise ValueError('score outside original archive')
        pair=validate_pair(_load(path,131072))
        if pair['pair_sha256']!=completion['pair_sha256']:raise ValueError('completed score identity differs')
        for source,identity in completion['original_fingerprints'].items():
            if _fingerprint(source)!=identity:raise ValueError('completed original source changed')
        pairs.append(pair)
    report=summarize(pairs,artifact_sha256=artifact_sha256);report['assessed_at']=_utc(now).isoformat()
    _write_report(settings['evidence_directory'],report);return report


def score_jobs(settings,*,guard,reader=None,max_jobs=1):
    guard();_resource_preflight()
    if type(max_jobs) is not int or max_jobs!=1:raise ValueError('one serial score job required')
    now=_clock();deadline=monotonic()+50
    def remaining():
        guard();value=deadline-monotonic()
        if value<=0:raise ValueError('provisional scoring deadline exceeded')
        return value
    root=_private_directory(Path(settings['evidence_directory']));runtime=current_runtime()
    candidate=read_candidate(Path(settings['candidate_path']),assessed_at=now,runtime=runtime)
    if reader is None:
        source_settings={key:settings[key] for key in ('token_file','native_db_config','native_policy','openhab_base')}
        source_settings.update(schema=COMPRESSED_SOURCE_SCHEMA,output_directory=str(_phase_directory(root,'scores',now)))
        reader=ScoreReader(source_settings,shared_lock_guard=guard)
    paths=[]
    for folder in _folders(root,'origins',now):paths.extend(folder.glob('*.provisional-delivery-v1.json'))
    if len(paths)>1024:raise ValueError('bounded delivered forecast inventory required')
    deliveries=[(path,_delivery(path,root)) for path in paths]
    deliveries.sort(key=lambda entry:_utc(entry[1]['issued_at']))
    scored=0
    report_path=root/'latest-provisional-performance.json'
    if report_path.exists():report_path.unlink();_sync_directory(root)
    with shared_replay_budget(remaining):
        for path,delivery in deliveries:
            remaining();issue=_utc(delivery['issued_at'])
            for horizon in (1,6,12,24):
                target=issue+timedelta(hours=horizon)
                if now<target+timedelta(minutes=5):continue
                job_id=digest({'delivery_sha256':delivery['delivery_sha256'],'horizon_hours':horizon},'unused')
                completion=None
                for folder in _folders(root,'scores',now):
                    marker=folder/(job_id+'.provisional-completion-v1.json')
                    if marker.exists():
                        completion=_load(marker)
                        if completion.get('completion_sha256')!=digest(completion,'completion_sha256') or completion.get('job_id')!=job_id:
                            raise ValueError('original completion identity differs')
                        break
                if completion is not None:
                    pair_path=Path(completion['pair_path'])
                    if not pair_path.is_relative_to(root):raise ValueError('score outside original archive')
                    try:
                        original=validate_pair(_load(pair_path,131072))
                        if original['pair_sha256']!=completion['pair_sha256'] or original['capture_sha256']!=delivery['capture_sha256'] or original['horizon_hours']!=horizon:raise ValueError('completed score identity differs')
                        for source,identity in completion['original_fingerprints'].items():
                            if _fingerprint(source)!=identity:raise ValueError('completed original source changed')
                    except (OSError,ValueError):
                        report_path=root/'latest-provisional-performance.json'
                        if report_path.exists():report_path.unlink();_sync_directory(root)
                        return dict(status='withheld',scored=scored,reason='completed_original_unavailable',automatic_actuation=False)
                    continue
                with capture_source_reads() as sources:
                    capture=read_capture(delivery['capture_path'],check_budget=remaining)
                    if capture['capture_sha256']!=delivery['capture_sha256'] or capture['candidate']['artifact_sha256']!=delivery['artifact_sha256'] or _canonical(capture['candidate']['runtime'])!=_canonical(runtime):
                        raise ValueError('original scoring model/runtime identity differs')
                    validate_delivery(capture,delivery['receipts'])
                    for receipt in delivery['receipts'].values():
                        observed=reader.publication(receipt)
                        if _canonical(observed)!=_canonical(receipt):raise ValueError('actual original publication receipt missing')
                    phase=capture['candidate']['fit']['sensor_epochs']['air']
                    rows=reader.native([target],assessed_at=now,sensor_epoch=phase)
                    if len(rows)!=1 or _utc(rows[0][0])!=target or rows[0][1] is None:raise ValueError('original mature outcome unavailable')
                    cutoff=_utc(settings['native_cutover'])
                    def grid(targets,assessed):
                        if any(at<cutoff for at in targets):return [(at,None) for at in targets]
                        return reader.native(targets,assessed_at=assessed,sensor_epoch=phase)
                    try:recent=compare_v2(issue=issue,target=target,current_f=capture['output']['initial']['air_f'],grid_reader=grid,sensor_epoch=phase)
                    except (ValueError,RuntimeError) as error:recent=dict(status='unavailable',prediction_f=None,reason=str(error))
                    pair=score(capture,delivery['receipts'],rows[0][1],horizon_hours=horizon,assessed_at=now,recent=recent,check_budget=remaining)
                    packet_paths=list(reader.native_source_paths)
                    pair['native_source_paths']=packet_paths;pair['pair_sha256']=digest(pair,'pair_sha256')
                    reader.verify_unchanged();sources.verify();remaining()
                    folder=_phase_directory(root,'scores',now)
                    pair_path=persist(folder,pair,field='pair_sha256',suffix='.provisional-pair-v1.json',maximum=131072)
                    if validate_pair(_load(pair_path,131072))!=json.loads(_canonical(pair)):raise ValueError('original score readback differs')
                    original_paths=set(packet_paths)|{delivery['capture_path'],capture['candidate']['snapshot_path'],str(path)}|set(capture['inputs']['native_source_paths'].values())
                    completion=dict(schema='earthship-provisional-thermal-completion/v1',job_id=job_id,pair_path=str(pair_path),pair_sha256=pair['pair_sha256'],
                        original_fingerprints={original:_fingerprint(original) for original in original_paths})
                    completion['completion_sha256']=digest(completion,'completion_sha256')
                    reader.verify_unchanged();sources.verify();remaining()
                    marker=folder/(job_id+'.provisional-completion-v1.json');_write_private(marker,_canonical(completion));_sync_directory(folder)
                scored+=1
                if scored>=max_jobs:break
            if scored>=max_jobs:break
        report=refresh_report(settings,artifact_sha256=candidate['artifact_sha256'],now=now,guard=remaining)
    return dict(status='scored' if scored else 'waiting',scored=scored,current_revision_scored=sum(x['model']['count'] for x in report['by_horizon'].values()),automatic_actuation=False)
