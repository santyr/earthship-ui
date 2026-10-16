"""Outside-fitted, single-outcome queue with explicit retryable missing evidence.

The numerical scoring, original capture/delivery checks, completed pair handling
and report schema remain delegated to the pinned provisional monitor. Mature
active-candidate jobs precede older candidates; each group stays chronological.
Absent points retain the same verified native evidence and retry contract.
"""
from datetime import timedelta
from pathlib import Path
from hashlib import sha256
from thermal_model import provisional_monitor as pinned

GAP_SCHEMA='earthship-provisional-thermal-gap/v1'
GAP_FIELDS={'schema','job_id','delivery_sha256','capture_sha256','artifact_sha256',
    'horizon_hours','target_at','assessed_at','retry_after','native_source_paths',
    'original_fingerprints','queue_source_sha256','automatic_actuation','gap_sha256'}
# Reviewed b84d000 uses the identical gap schema and native absence replay.
# Accept its retained gaps across this scheduling-only upgrade; unknown
# implementations still refuse and every original source is revalidated.
PRIOR_GAP_SOURCES=('5537dd82d2565b1f307dc5dcb74d76cb84871bad669cf3e837b0c013e46ebbd0',)


def _source_digest():return sha256(Path(__file__).read_bytes()).hexdigest()


def _validate_gap_native(packets,capture,*,target,assessed,guard):
    from weather_temperature_sources import read_compressed_temperature_source,replay_temperature_source
    if not isinstance(packets,list) or len(packets)!=1:
        raise ValueError('one retained missing outcome native query required')
    guard();path=Path(packets[0]);packet=read_compressed_temperature_source(path.parent,path)
    if (packet['targets']!=[target.isoformat()] or pinned._utc(packet['assessed_at'])!=assessed or
        packet['stream']!='indoor' or packet['sensor_epoch']!=capture['candidate']['fit']['sensor_epochs']['air']):
        raise ValueError('missing outcome native query context differs')
    selected=replay_temperature_source(packet);guard()
    if len(selected)!=1 or pinned._utc(selected[0][0])!=target or selected[0][1] is not None:
        raise ValueError('missing outcome native query must select no measurement')


def _gap_index(root,now,guard):
    paths=[]
    for folder in pinned._folders(root,'scores',now):
        guard();paths.extend(folder.glob('*.provisional-gap-v1.json'))
    if len(paths)>4096:raise ValueError('bounded missing outcome inventory required')
    index={}
    for path in paths:
        job=path.name.split('-',1)[0]
        index.setdefault(job,[]).append(path)
    return index


def _gap_pending(paths,*,delivery,delivery_path,horizon,target,now,guard):
    if not paths:return False
    guard();path=max(paths,key=lambda p:p.stat().st_mtime_ns);value=pinned._load(path)
    job=pinned.digest({'delivery_sha256':delivery['delivery_sha256'],'horizon_hours':horizon},'unused')
    if (not isinstance(value,dict) or set(value)!=GAP_FIELDS or value['schema']!=GAP_SCHEMA or
        value['job_id']!=job or value['delivery_sha256']!=delivery['delivery_sha256'] or
        value['capture_sha256']!=delivery['capture_sha256'] or value['artifact_sha256']!=delivery['artifact_sha256'] or
        value['horizon_hours']!=horizon or value['target_at']!=target.isoformat() or
        value['automatic_actuation'] is not False or value['queue_source_sha256'] not in (_source_digest(),*PRIOR_GAP_SOURCES) or
        value['gap_sha256']!=pinned.digest(value,'gap_sha256') or
        path.name!=job+'-'+value['gap_sha256']+'.provisional-gap-v1.json'):
        raise ValueError('original missing outcome identity differs')
    assessed,retry=map(pinned._utc,(value['assessed_at'],value['retry_after']))
    if assessed>now or retry-assessed!=timedelta(minutes=15) or assessed<target+timedelta(minutes=5):
        raise ValueError('original missing outcome retry lifetime differs')
    packets=value['native_source_paths'];fingerprints=value['original_fingerprints']
    if (not isinstance(packets,list) or len(packets)>64 or
        any(not isinstance(p,str) or not 1<=len(p)<=1024 for p in packets) or
        not isinstance(fingerprints,dict) or not 1<=len(fingerprints)<=128):
        raise ValueError('bounded missing outcome originals required')
    for source,wanted in value['original_fingerprints'].items():
        guard()
        if pinned._fingerprint(source)!=wanted:raise ValueError('missing outcome original changed')
    capture=pinned._load(delivery['capture_path'],2097152)
    if (capture['capture_sha256']!=delivery['capture_sha256'] or
        pinned.digest(capture,'capture_sha256')!=delivery['capture_sha256']):
        raise ValueError('missing outcome capture identity differs')
    required=set(packets)|{delivery['capture_path'],capture['candidate']['snapshot_path'],str(delivery_path)}|set(capture['inputs']['native_source_paths'].values())
    if set(fingerprints)!=required:raise ValueError('complete missing outcome fingerprints required')
    _validate_gap_native(packets,capture,target=target,assessed=assessed,guard=guard)
    return now<retry


def _retain_gap(root,job,delivery,horizon,target,now,packets,source_paths,*,guard):
    guard()
    capture=pinned._load(delivery['capture_path'],2097152)
    _validate_gap_native(packets,capture,target=target,assessed=now,guard=guard)
    value=dict(schema=GAP_SCHEMA,job_id=job,delivery_sha256=delivery['delivery_sha256'],
        capture_sha256=delivery['capture_sha256'],artifact_sha256=delivery['artifact_sha256'],
        horizon_hours=horizon,target_at=target.isoformat(),assessed_at=now.isoformat(),
        retry_after=(now+timedelta(minutes=15)).isoformat(),native_source_paths=packets,
        original_fingerprints={source:pinned._fingerprint(source) for source in source_paths},
        queue_source_sha256=_source_digest(),automatic_actuation=False)
    value['gap_sha256']=pinned.digest(value,'gap_sha256')
    folder=pinned._phase_directory(root,'scores',now)
    path=folder/(job+'-'+value['gap_sha256']+'.provisional-gap-v1.json')
    pinned._write_private(path,pinned._canonical(value));pinned._sync_directory(folder)
    guard()


def score_jobs(settings, *, guard, reader=None, max_jobs=1):
    guard()
    pinned._resource_preflight()
    if type(max_jobs) is not int or max_jobs != 1:
        raise ValueError('one serial score job required')
    now = pinned._clock()
    deadline = pinned.monotonic() + 50

    def remaining():
        guard()
        value = deadline - pinned.monotonic()
        if value <= 0:
            raise ValueError('provisional scoring deadline exceeded')
        return value
    root = pinned._private_directory(pinned.Path(settings['evidence_directory']))
    runtime = pinned.current_runtime()
    candidate = pinned.read_candidate(pinned.Path(settings['candidate_path']), assessed_at=now, runtime=runtime)
    if reader is None:
        source_settings = {key: settings[key] for key in ('token_file', 'native_db_config', 'native_policy', 'openhab_base')}
        source_settings.update(schema=pinned.COMPRESSED_SOURCE_SCHEMA, output_directory=str(pinned._phase_directory(root, 'scores', now)))
        reader = pinned.ScoreReader(source_settings, shared_lock_guard=guard)
    paths = []
    for folder in pinned._folders(root, 'origins', now):
        paths.extend(folder.glob('*.provisional-delivery-v1.json'))
    if len(paths) > 1024:
        raise ValueError('bounded delivered forecast inventory required')
    deliveries = [(path, pinned._delivery(path, root)) for path in paths]
    deliveries.sort(key=lambda entry: (entry[1]['artifact_sha256']!=candidate['artifact_sha256'],
                                      pinned._utc(entry[1]['issued_at'])))
    scored = 0
    gaps = _gap_index(root, now, guard)
    missing = False
    report_path = root / 'latest-provisional-performance.json'
    if report_path.exists():
        report_path.unlink()
        pinned._sync_directory(root)
    with pinned.shared_replay_budget(remaining):
        for path, delivery in deliveries:
            remaining()
            issue = pinned._utc(delivery['issued_at'])
            for horizon in (1, 6, 12, 24):
                target = issue + pinned.timedelta(hours=horizon)
                if now < target + pinned.timedelta(minutes=5):
                    continue
                job_id = pinned.digest({'delivery_sha256': delivery['delivery_sha256'], 'horizon_hours': horizon}, 'unused')
                completion = None
                for folder in pinned._folders(root, 'scores', now):
                    marker = folder / (job_id + '.provisional-completion-v1.json')
                    if marker.exists():
                        completion = pinned._load(marker)
                        if completion.get('completion_sha256') != pinned.digest(completion, 'completion_sha256') or completion.get('job_id') != job_id:
                            raise ValueError('original completion identity differs')
                        break
                if completion is None and _gap_pending(gaps.get(job_id, []), delivery=delivery, delivery_path=path, horizon=horizon, target=target, now=now, guard=remaining):
                    continue
                if completion is not None:
                    pair_path = pinned.Path(completion['pair_path'])
                    if not pair_path.is_relative_to(root):
                        raise ValueError('score outside original archive')
                    try:
                        original = pinned.validate_pair(pinned._load(pair_path, 131072))
                        if original['pair_sha256'] != completion['pair_sha256'] or original['capture_sha256'] != delivery['capture_sha256'] or original['horizon_hours'] != horizon:
                            raise ValueError('completed score identity differs')
                        for source, identity in completion['original_fingerprints'].items():
                            if pinned._fingerprint(source) != identity:
                                raise ValueError('completed original source changed')
                    except (OSError, ValueError):
                        report_path = root / 'latest-provisional-performance.json'
                        if report_path.exists():
                            report_path.unlink()
                            pinned._sync_directory(root)
                        return dict(status='withheld', scored=scored, reason='completed_original_unavailable', automatic_actuation=False)
                    continue
                with pinned.capture_source_reads() as sources:
                    capture = pinned.read_capture(delivery['capture_path'], check_budget=remaining)
                    if capture['capture_sha256'] != delivery['capture_sha256'] or capture['candidate']['artifact_sha256'] != delivery['artifact_sha256'] or pinned._canonical(capture['candidate']['runtime']) != pinned._canonical(runtime):
                        raise ValueError('original scoring model/runtime identity differs')
                    pinned.validate_delivery(capture, delivery['receipts'])
                    for receipt in delivery['receipts'].values():
                        observed = reader.publication(receipt)
                        if pinned._canonical(observed) != pinned._canonical(receipt):
                            raise ValueError('actual original publication receipt missing')
                    phase = capture['candidate']['fit']['sensor_epochs']['air']
                    rows = reader.native([target], assessed_at=now, sensor_epoch=phase)
                    if len(rows) != 1 or pinned._utc(rows[0][0]) != target:
                        raise ValueError('original mature outcome shape differs')
                    if rows[0][1] is None:
                        reader.verify_unchanged(); sources.verify(); remaining()
                        packet_paths = list(reader.native_source_paths)
                        source_paths = set(packet_paths) | {delivery['capture_path'], capture['candidate']['snapshot_path'], str(path)} | set(capture['inputs']['native_source_paths'].values())
                        _retain_gap(root, job_id, delivery, horizon, target, now, packet_paths, source_paths, guard=remaining)
                        missing = True
                        break
                    cutoff = pinned._utc(settings['native_cutover'])

                    def grid(targets, assessed):
                        if any((at < cutoff for at in targets)):
                            return [(at, None) for at in targets]
                        return reader.native(targets, assessed_at=assessed, sensor_epoch=phase)
                    try:
                        recent = pinned.compare_v2(issue=issue, target=target, current_f=capture['output']['initial']['air_f'], grid_reader=grid, sensor_epoch=phase)
                    except (ValueError, RuntimeError) as error:
                        recent = dict(status='unavailable', prediction_f=None, reason=str(error))
                    pair = pinned.score(capture, delivery['receipts'], rows[0][1], horizon_hours=horizon, assessed_at=now, recent=recent, check_budget=remaining)
                    packet_paths = list(reader.native_source_paths)
                    pair['native_source_paths'] = packet_paths
                    pair['pair_sha256'] = pinned.digest(pair, 'pair_sha256')
                    reader.verify_unchanged()
                    sources.verify()
                    remaining()
                    folder = pinned._phase_directory(root, 'scores', now)
                    pair_path = pinned.persist(folder, pair, field='pair_sha256', suffix='.provisional-pair-v1.json', maximum=131072)
                    if pinned.validate_pair(pinned._load(pair_path, 131072)) != pinned.json.loads(pinned._canonical(pair)):
                        raise ValueError('original score readback differs')
                    original_paths = set(packet_paths) | {delivery['capture_path'], capture['candidate']['snapshot_path'], str(path)} | set(capture['inputs']['native_source_paths'].values())
                    completion = dict(schema='earthship-provisional-thermal-completion/v1', job_id=job_id, pair_path=str(pair_path), pair_sha256=pair['pair_sha256'], original_fingerprints={original: pinned._fingerprint(original) for original in original_paths})
                    completion['completion_sha256'] = pinned.digest(completion, 'completion_sha256')
                    reader.verify_unchanged()
                    sources.verify()
                    remaining()
                    marker = folder / (job_id + '.provisional-completion-v1.json')
                    pinned._write_private(marker, pinned._canonical(completion))
                    pinned._sync_directory(folder)
                scored += 1
                if missing or scored >= max_jobs:
                    break
            if missing or scored >= max_jobs:
                break
        report = pinned.refresh_report(settings, artifact_sha256=candidate['artifact_sha256'], now=now, guard=remaining)
    return dict(status='monitoring_refreshed' if missing else 'scored' if scored else 'waiting', scored=scored, current_revision_scored=sum((x['model']['count'] for x in report['by_horizon'].values())), pending_reason='mature_outcome_unavailable' if missing else None, automatic_actuation=False)
