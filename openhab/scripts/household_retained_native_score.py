"""Current operational clocks around an archived native numerical runtime.

This module is outside the fitted runtime. It imports numerical, receipt,
source-query, gap and report helpers from the selected archive. It never edits
archived functions, source files, runtime hashes or clocks.
"""
from datetime import datetime,timedelta,timezone
from pathlib import Path
import time


# This is an operational reader integration; the fitted archived class stays
# untouched. Unknown archived source implementations retain their own reader.
NATIVE_READER_SOURCE_SHA256='61851a694333d3cd66c24e8e71aab016631844a34b09411c6816c74e0e5c11f8'
SEGMENTED_NATIVE_READER_SOURCE_SHA256='fa74fad2791de66c3e7884960ef6402f7b58c2bd03f05b41aae02edf02cf1833'
BOUNDED_SEGMENTED_NATIVE_READER_SOURCE_SHA256='28714d64f977cb9e7fd25eed7295336baa2870f2062a4ce17a86ad7a8f3c6cbc'
OPERATIONAL_READER_SOURCE_SHA256='5621fba1de64e317bfe5b4a7b0f7fa12d8e05ecc323961a6a96e170601f9f4a5'


def _reader_factory():
    import importlib.util
    from hashlib import sha256
    import native_thermal_live as native
    from thermal_model.origin_capture import _source_bytes
    if sha256(_source_bytes(Path(native.__file__).absolute(),maximum=262144)).hexdigest() not in (
            NATIVE_READER_SOURCE_SHA256,SEGMENTED_NATIVE_READER_SOURCE_SHA256,
            BOUNDED_SEGMENTED_NATIVE_READER_SOURCE_SHA256):
        return native.NativeScoreReader
    path=Path(__file__).absolute().with_name('household_native_score_queries.py')
    if sha256(_source_bytes(path,maximum=262144)).hexdigest()!=OPERATIONAL_READER_SOURCE_SHA256:
        raise ValueError('retained operational reader source differs')
    import sys
    queries=sys.modules.get('household_native_score_queries')
    if queries is None or Path(queries.__file__).absolute()!=path:
        spec=importlib.util.spec_from_file_location('_earthship_retained_score_queries',path)
        queries=importlib.util.module_from_spec(spec);spec.loader.exec_module(queries)
    return queries.RecentCycleWindowReader


CONFIGURATION_GUARD_SOURCES={
    'household_observation':'ae25be2471747d337031ed6f0ccd68118eb58253ac6b59f22ccf88e03baf11b7',
    'thermal_model.policy_registration':'9baf4b13fea46eb35d8ea1e1c19a6fdb5fe5270180da16a5193e19ce07b99bfb',
    'thermal_model.forcing_capture':'c492418769bfff01d0b42b1f2c982e3570a910eb2011ada4deb9bc5014dd9ec0',
    'thermal_model.replay_budget':'0962de5a39db509d0abe4cde4afce5c0a3366f8ce3c876e3c9a9a08f76a935b9',
}


def _configuration_reuse_supported(*functions):
    """Only the original pure parser/readers permit duplicate-work reuse."""
    import sys
    from hashlib import sha256
    from thermal_model.origin_capture import _source_bytes
    sources=[]
    for function in functions:
        expected=CONFIGURATION_GUARD_SOURCES.get(function.__module__)
        module=sys.modules.get(function.__module__)
        if expected is None or module is None:return None
        try:
            path=Path(module.__file__).absolute()
            raw=_source_bytes(path,maximum=262144)
            if Path(function.__code__.co_filename).absolute()!=path or sha256(raw).hexdigest()!=expected:return None
            sources.append((module,function.__name__,function,function.__code__,path,raw))
        except (OSError,ValueError,AttributeError):return None
    return tuple(sources)


def run(config,*,stage,deployment_sha256,deadline,resource_preflight,pressure_factory,
        source_guard,verify_archive,clock=lambda:datetime.now(timezone.utc),monotonic=time.monotonic):
    import os,math
    from native_thermal_live import load_settings,SERVING_SCHEMA
    import native_thermal_live as native
    from native_model_serving_receipt import load_serving_selection,read_serving_model
    from thermal_model.capture_guard import SharedScoreLock
    from thermal_model.native_operational_io import _next_issue
    from thermal_model.policy_registration import _read_private
    from thermal_model.forcing_capture import _private_directory
    from thermal_model.replay_budget import _source_reads,OriginalSourceInventory,observe_source_bytes
    from household_observation import _private_file
    if not math.isfinite(deadline) or monotonic()>=deadline:raise ValueError('score lifetime elapsed')
    source_guard();resource_preflight()
    os.environ['EARTHSHIP_QUALIFICATION_FIT']='0';os.environ['EARTHSHIP_REMOTE_QUALIFICATION_FIT']='0'
    config=Path(config).absolute();original=_private_file(config,8192);settings=load_settings(config)
    if settings.get('schema') not in getattr(native,'SERVING_SCHEMAS',(SERVING_SCHEMA,)):raise ValueError('retained native execution requires explicit serving profile')
    from household.codec import loads
    from household_cycle_deploy import _bytes
    cycle=loads(_bytes(Path(stage)/'cycle.json',private=True))
    if cycle.get('forecast_config')!=str(config):raise ValueError('retained native cycle configuration differs')
    # Parse the already validated original once. Every guard still freshly
    # checks the original full metadata/bytes, private parent and live settings.
    configuration_sources=_configuration_reuse_supported(_private_file,_read_private,_private_directory,observe_source_bytes)
    reuse_configuration=configuration_sources is not None
    sealed_settings=_read_private(config) if reuse_configuration else None
    observed_inventory=object()
    issue=_next_issue(clock())
    if issue-clock()<timedelta(seconds=90):raise BlockingIOError('forecast preparation window reserved')
    with SharedScoreLock(settings['shared_lock']) as lock:
        pressure=pressure_factory();pressure.check(force=True)
        def guard():
            nonlocal observed_inventory,reuse_configuration
            lock.verify();pressure.check();source_guard()
            if monotonic()>=deadline or clock()>=issue-timedelta(seconds=135):raise ValueError('score lifetime elapsed')
            if reuse_configuration and any(getattr(module,name,None) is not function or function.__code__ is not code
                    for module,name,function,code,_,_ in configuration_sources):reuse_configuration=False
            inventory=_source_reads.get()
            if not reuse_configuration or (inventory is not None and type(inventory) is not OriginalSourceInventory):
                if _private_file(config,8192)!=original or _read_private(config)!=settings:raise ValueError('score source or configuration changed')
                return
            if _private_file(config,8192)!=original or sealed_settings!=settings:raise ValueError('score source or configuration changed')
            _private_directory(config.parent)
            # Register genuine immutable bytes in EACH original inventory.
            # The strict metadata/byte check above runs even on repeated guards;
            # only duplicate JSON parsing/observation is omitted. Unknown
            # observers retain their original per-boundary observation calls.
            if inventory is not None and inventory is not observed_inventory:
                for _,_,_,_,path,raw in configuration_sources:observe_source_bytes(path,raw)
                observe_source_bytes(config,original[0]);observed_inventory=inventory
        guard()
        selected=load_serving_selection(stage,expected_deployment_sha256=deployment_sha256,assessed_at=clock(),guard=guard)
        model=read_serving_model(selected,assessed_at=clock(),guard=guard)
        guard();pressure.check(force=True)
        result=score_jobs(settings,guard=guard,deadline=deadline,clock=clock,monotonic=monotonic,serving_model=model)
        guard();verify_archive();pressure.check(force=True);guard()
        return result


def score_jobs(settings,*,guard,deadline,clock,monotonic,reader=None,max_jobs=1,serving_model=None,historical_selections=()):
    """One native outcome with raw query replay and source-backed reporting."""
    import json
    import native_thermal_live as archive
    from native_thermal_live import (deepcopy,_resource_preflight,SERVING_SCHEMA,LIVE_SCHEMA,
        _serving_settings,_owned_bytes,current_runtime,runtime_digest,SOURCE,read_native_candidate,
        COMPRESSED_SOURCE_SCHEMA,NativeScoreReader,_native_completion_index,_instant,
        serving_delivery_model,_native_gap_pending,_canonical,_retain_native_gap,refresh_report)
    import native_thermal_score as scores
    from native_thermal_artifact import _read
    from household_cycle import load_cycle_delivery
    from thermal_model.forcing_capture import _private_directory
    from thermal_model.native_operational_io import _folders
    from thermal_model.native_operational_io import _phase_directory
    from thermal_model.recent_cycles import compare_v2
    from thermal_model.replay_budget import shared_replay_budget,capture_source_reads
    if type(max_jobs) is not int or max_jobs!=1:raise ValueError('one serial native score job required')
    settings=deepcopy(settings);guard();_resource_preflight();now=clock()
    def remaining():
        guard();seconds=deadline-monotonic()
        if seconds<=0:raise ValueError('native scoring deadline exceeded')
        return seconds
    receipt_profile=settings.get('schema') in getattr(archive,'SERVING_SCHEMAS',(SERVING_SCHEMA,))
    if settings.get('schema') not in getattr(archive,'NATIVE_SCHEMAS',(LIVE_SCHEMA,SERVING_SCHEMA)):raise ValueError('explicit native scoring selection required')
    if receipt_profile:
        if type(historical_selections) is not tuple or len(historical_selections)>31:raise ValueError('bounded owned historical score selections required')
        _serving_settings(serving_model,settings,assessed_at=now,guard=remaining)
    elif serving_model is not None or historical_selections:raise ValueError('receipt context requires explicit serving profile')
    root=_private_directory(Path(settings['evidence_directory']))
    report_paths=[root/'latest-native-provisional-performance.json']
    if hasattr(archive,'_native_report_path'):
        report_paths.insert(0,archive._native_report_path(root,settings['artifact_sha256']))
    for report_path in report_paths:
        if report_path.exists() or report_path.is_symlink():
            from thermal_model.runtime_bundle import _sync_directory
            _owned_bytes(report_path,131072);remaining();report_path.unlink();_sync_directory(root)
    with shared_replay_budget(remaining),capture_source_reads() as originals:
        runtime=serving_model.runtime if receipt_profile else current_runtime(guard=remaining)
        if runtime_digest(runtime)!=settings['runtime_sha256'] or SOURCE not in runtime['native_source_manifest']:
            raise ValueError('externally pinned native scoring runtime differs')
        if receipt_profile:candidate=serving_model.candidate
        else:candidate=read_native_candidate(Path(settings['candidate_path']),assessed_at=now,runtime=runtime,
            expected_artifact_sha256=settings['artifact_sha256'],guard=remaining)
        folder=_phase_directory(root,'scores',now)
        if reader is None:
            config={key:settings[key] for key in ('token_file','native_db_config','native_policy','openhab_base')}
            config.update(schema=COMPRESSED_SOURCE_SCHEMA,output_directory=str(folder))
            reader=_reader_factory()(config,shared_lock_guard=remaining)
        paths=[]
        for directory in _folders(root,'origins',now):paths.extend(directory.glob('*.native-provisional-delivery-v2.json'))
        if len(paths)>1024:raise ValueError('bounded native delivered forecast inventory required')
        deliveries=[]
        fields={'schema','issued_at','capture_path','capture_sha256','artifact_sha256','runtime_sha256','geometry_series_sha256','receipts','delivery_sha256'}
        for path in paths:
            remaining();_,delivery=_read(path,65536)
            if (not isinstance(delivery,dict) or set(delivery)!=fields or delivery['schema']!='earthship-provisional-thermal-delivery/v2' or
                runtime_digest(delivery,'delivery_sha256')!=delivery['delivery_sha256'] or path.name!=delivery['delivery_sha256']+'.native-provisional-delivery-v2.json'):
                raise ValueError('closed original native delivered record required')
            origin=Path(delivery['capture_path'])
            if not origin.is_absolute() or origin.resolve()!=origin or origin.parent!=path.parent:
                raise ValueError('native origin outside original delivery archive')
            deliveries.append((path,delivery))
        deliveries.sort(key=lambda entry:(entry[1]['artifact_sha256']!=candidate['artifact_sha256'],_instant(entry[1]['issued_at'])))
        completed=_native_completion_index(root,now,remaining);scored=0;missing=False;historical_unavailable=False
        for path,delivery in deliveries:
            remaining();issue=_instant(delivery['issued_at'])
            for horizon in (1,6,12,24):
                target=issue+timedelta(hours=horizon)
                if now<target+timedelta(minutes=5):continue
                job=runtime_digest({'capture_sha256':delivery['capture_sha256'],'horizon_hours':horizon})
                if job in completed:
                    marker=completed[job][1]
                    if any(marker[key]!=delivery[key] for key in ('artifact_sha256','capture_sha256','runtime_sha256')) or marker['horizon_hours']!=horizon:
                        raise ValueError('native completed job binding differs')
                    continue
                selected_model=None
                if receipt_profile:
                    selected_model=serving_delivery_model(path,delivery,current_model=serving_model,
                        historical_selections=historical_selections,assessed_at=now,guard=remaining)
                    if selected_model is None:
                        historical_unavailable=True;break
                archive_pins=dict(runtime=runtime if selected_model is None else selected_model.runtime,
                    expected_artifact_sha256=delivery['artifact_sha256'],expected_capture_sha256=delivery['capture_sha256'])
                if receipt_profile:archive_pins['serving_model']=selected_model
                archive=load_cycle_delivery(dict(status='published' ,delivery_verified=True,origin_path=delivery['capture_path'],delivery_path=str(path)),
                    issue=issue,guard=remaining,**archive_pins)
                capture=archive['capture']
                if _native_gap_pending(root,now,job,delivery,path,capture,remaining):continue
                for receipt in archive['receipts'].values():
                    if _canonical(reader.publication(receipt))!=_canonical(receipt):raise ValueError('actual original native publication missing')
                phase=capture['candidate']['fit']['sensor_epochs']['air']
                outcome=reader.native([target],assessed_at=now,sensor_epoch=phase)
                if len(outcome)!=1 or _instant(outcome[0][0])!=target:raise ValueError('original native outcome shape differs')
                if outcome[0][1] is None:
                    reader.verify_unchanged();archive['verify_unchanged']();originals.verify();remaining()
                    _retain_native_gap(folder,job,delivery,path,capture,horizon=horizon,target=target,now=now,
                        paths=list(reader.native_source_paths),guard=remaining)
                    missing=True;break
                grid={}
                def historical(targets,assessed):
                    rows=reader.native(targets,assessed_at=assessed,sensor_epoch=phase)
                    for at,receipt in rows:
                        key=_instant(at).isoformat()
                        encoded=None if receipt is None else {name:value.isoformat() if isinstance(value,datetime) else value for name,value in receipt.items()}
                        if key in grid and grid[key]!=encoded:raise ValueError('original native comparator endpoint changed')
                        grid[key]=encoded
                    return rows
                compare_v2(issue=issue,target=target,current_f=capture['output']['initial']['air_f'],grid_reader=historical,sensor_epoch=phase)
                source_args=dict(capture_path=delivery['capture_path'],receipts=archive['receipts'],outcome=outcome[0][1],
                    recent_cycle_grid=[[at,value] for at,value in sorted(grid.items())],source_paths=list(reader.native_source_paths),
                    horizon_hours=horizon,assessed_at=now,expected_capture_sha256=delivery['capture_sha256'],check_budget=remaining)
                if receipt_profile:source=scores.build_serving_source_score(model=selected_model,**source_args)
                else:source=scores.build_source_score(runtime=runtime,expected_artifact_sha256=delivery['artifact_sha256'],**source_args)
                reader.verify_unchanged();archive['verify_unchanged']();originals.verify();remaining()
                if receipt_profile:selected_model.verify_bindings(assessed_at=clock(),guard=remaining)
                source_path=scores.persist_source_score(folder,source)
                completion_args=dict(expected_capture_sha256=delivery['capture_sha256'],expected_source_score_sha256=source['source_score_sha256'],
                    completed_at=clock(),check_budget=remaining)
                if receipt_profile:completion=scores.build_serving_source_completion(source_path,model=selected_model,**completion_args)
                else:completion=scores.build_source_completion(source_path,runtime=runtime,expected_artifact_sha256=delivery['artifact_sha256'],**completion_args)
                reader.verify_unchanged();archive['verify_unchanged']();originals.verify();remaining()
                if receipt_profile:selected_model.verify_bindings(assessed_at=clock(),guard=remaining)
                scores.persist_source_completion(folder,completion);scored=1;break
            if scored or missing:break
        report_args={} if not receipt_profile else dict(serving_model=serving_model)
        report=refresh_report(settings,runtime=runtime,artifact_sha256=candidate['artifact_sha256'],now=clock(),guard=remaining,**report_args)
        reader.verify_unchanged();originals.verify();remaining()
        result=dict(status='scored' if scored else 'monitoring_refreshed' if missing else 'waiting',scored=scored,
            current_revision_scored=sum(row['model']['count'] for row in report['by_horizon'].values()),automatic_actuation=False)
        if missing:result['pending_reason']='mature_outcome_unavailable'
        elif historical_unavailable:result['pending_reason']='historical_model_selection_unavailable'
        return result

