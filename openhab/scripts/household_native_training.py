"""Production orchestration of the existing native capture, fit and handoff APIs."""
import contextlib
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import time
from uuid import uuid4

from household_cycle_pressure import PublicationHeadroom
from household_native_daily import capture_windows, retained_parts,long_part_prefix
from zoneinfo import ZoneInfo
from thermal_model.runtime_bundle import _owned_bytes


def read(path, maximum=131072):
    return json.loads(_owned_bytes(Path(path), maximum))


def save(path, value):
    """Atomic private checkpoint; never truncate a checkpoint on interruption."""
    path = Path(path)
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    temporary = path.with_name('.' + path.name + '-' + uuid4().hex)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def directory(path):
    from thermal_model.forcing_capture import _private_directory
    path = Path(path)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return _private_directory(path)


@contextlib.contextmanager
def daily_lock(path):
    """Create only this worker's private lock; retain its inode across runs."""
    from thermal_model.capture_guard import SharedScoreLock
    from thermal_model.forcing_capture import _private_directory
    path = Path(path)
    _private_directory(path.parent)
    try:
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        pass
    else:
        os.close(fd)
    with SharedScoreLock(path) as lock:
        yield lock


class RamGuard:
    def __init__(self, seconds=1800):
        self.pressure = PublicationHeadroom()
        self.deadline = time.monotonic() + seconds
        self.last = 0.
        self()

    def __call__(self):
        now = time.monotonic()
        if now >= self.deadline:
            raise TimeoutError('daily native refresh deadline exceeded')
        if now - self.last >= .25:
            self.pressure.check()
            self.last = now


def effective_selection():
    raw = subprocess.check_output(['systemctl', '--user', 'show',
        'thermal-provisional-forecast.service', '-p', 'ExecStart', '--value'], text=True, timeout=10)
    matches = re.findall(r'--stage ([^\s;]+) --deployment-sha256 ([0-9a-f]{64})(?=\s|;)', raw)
    if len(matches) != 1:
        raise ValueError('one effective native deployment selection required')
    stage, pin = matches[0]
    return dict(stage=stage, deployment_sha256=pin)


def build_deployment_candidate(*, originals, runtime, previous, created_at, guard):
    """Keep verified model identity when only its deployment changes."""
    from native_thermal_artifact import build_native_candidate, _references
    guard()
    same_model = (previous['runtime'] == runtime and
                  previous['originals'] == _references(originals))
    model_time = datetime.fromisoformat(previous['created_at']) if same_model else created_at
    candidate = build_native_candidate(originals=originals, runtime=runtime,
        created_at=model_time, guard=guard)
    if same_model and candidate != previous:
        raise ValueError('previous model differs from rederived original evidence')
    return candidate


def retained_model_admission(candidate, *, selections, guard):
    """Reuse the earliest externally pinned admission of this exact model."""
    from household_cycle_deploy import verify_stage
    from native_model_serving_receipt import load_serving_selection, read_serving_model
    # A complete retained dispatch has up to63 stages, plus the current one.
    if not isinstance(selections,(list,tuple)) or not 1<=len(selections)<=64:
        raise ValueError('bounded retained admission selections required')
    best=None;seen=set()
    for reference in selections:
        guard();stage=Path(reference['stage']);pin=reference['deployment_sha256']
        if str(stage) in seen:raise ValueError('unique retained admission stages required')
        seen.add(str(stage));record=verify_stage(stage,expected_deployment_sha256=pin)
        if record.get('artifact_sha256')!=candidate['artifact_sha256']:continue
        if record.get('runtime_sha256')!=candidate['runtime_sha256']:
            raise ValueError('retained admission runtime differs')
        now=datetime.now(timezone.utc)
        selection=load_serving_selection(stage,expected_deployment_sha256=pin,assessed_at=now,guard=guard)
        model=read_serving_model(selection,assessed_at=now,guard=guard)
        if model.candidate!=candidate:raise ValueError('retained admission candidate differs')
        receipt=json.loads(model._encoded)['receipt'];owned=json.loads(selection._encoded)
        key=(datetime.fromisoformat(receipt['verified_at']),str(stage))
        if best is None or key<best[0]:best=(key,model,owned,receipt)
    if best is None:return None
    _,model,owned,receipt=best
    model.verify_bindings(assessed_at=datetime.now(timezone.utc),guard=guard);guard()
    return dict(candidate_path=owned['candidate_path'],receipt_path=owned['receipt']['path'],
        receipt_sha256=owned['receipt']['sha256'],verified_at=receipt['verified_at'],
        source_stage=owned['stage'],source_deployment_sha256=owned['deployment_sha256'])


class NativeTraining:
    def __init__(self, config):
        if config.get('training_cadence','daily') not in ('daily','six_hourly'):raise ValueError('supported native training cadence required')
        self.config = config
        self.repo = Path(__file__).resolve().parents[2]
        self.state = directory(config['state_directory'])
        self.guard = RamGuard()
        self.capture_config = read(config['capture_config'], 8192)
        self.inputs = read(config['staging_inputs'])

    def prepare_ac_load(self, cutoff):
        """Independent read-only AC-output model in the existing morning job."""
        from household_ac_load_store import refresh_profile, AC_LOAD_ROOT, ENERGY_READER_CONFIG
        from household_capture import _connection
        deadline = time.monotonic() + 120.
        def remaining():
            self.guard()
            value = deadline - time.monotonic()
            if value < 1: raise TimeoutError('daily load profile deadline elapsed')
            return min(15., value)
        result = dict(status='deferred', reason='load_profile_refresh_failed', automatic_actuation=False)
        try:
            connect = _connection(str(ENERGY_READER_CONFIG), 'energy_power_reader')
            result = refresh_profile(root=AC_LOAD_ROOT, connect=connect, cutoff=cutoff,
                clock=lambda: datetime.now(timezone.utc), remaining=remaining, guard=remaining)
            return result
        finally:
            save(self.state / 'last-ac-load-result.json', result)

    def current(self):
        from native_model_serving_receipt import load_serving_selection, read_serving_model
        selected = effective_selection()
        now = datetime.now(timezone.utc)
        selection = load_serving_selection(Path(selected['stage']),
            expected_deployment_sha256=selected['deployment_sha256'], assessed_at=now, guard=self.guard)
        model = read_serving_model(selection, assessed_at=datetime.now(timezone.utc), guard=self.guard)
        return dict(selected, trained_through=model.candidate['fit']['training_end'])

    def worker(self, command, seconds=90):
        from thermal_model.training_pressure_guard import run_training_worker
        env = dict(os.environ, EARTHSHIP_THERMAL_INPUT_CAPTURE='1',
            EARTHSHIP_GUARDED_CAPTURE_WORKER='1', EARTHSHIP_QUALIFICATION_FIT='0',
            EARTHSHIP_REMOTE_QUALIFICATION_FIT='0')
        scoped=['/usr/bin/python3',str(Path(__file__).with_name('household_job_run.py')),
            '--production','--collection','--minimum-mib','256','--preferred-mib','256',
            '--tasks','24','--seconds',str(seconds),'--',*command]
        status, output = run_training_worker(scoped, check=self.guard, seconds=seconds, env=env)
        if status:
            # The public CLI intentionally omits credential values from errors.
            raise RuntimeError('daily measurement worker failed: ' + output.decode(errors='replace')[-800:])

    def capture_index(self,cutoff):
        if getattr(self,'config',{}).get('training_cadence','daily')=='daily':return self.state/'raw-parts.json',None
        day=cutoff.astimezone(ZoneInfo(self.config['timezone'])).date()
        root=directory(self.state/'capture-days'/day.isoformat());index=root/'raw-parts.json'
        if index.exists():return index,None
        previous=self.state/'capture-days'/(day-timedelta(days=1)).isoformat()/'raw-parts.json'
        anchor=previous if previous.exists() else self.state/'raw-parts.json'
        return index,anchor if anchor.exists() else None

    def raw_parts(self, cutoff):
        from thermal_model.training_inputs import read_training_inputs_v2
        index,anchor=self.capture_index(cutoff)
        existing=index.exists()
        rows=read(index) if existing else read(anchor) if anchor is not None else []
        if not rows:
            for path in self.config['seed_parts']:
                record = read_training_inputs_v2(Path(path))
                rows.append(dict(path=path, start=record['start'], end=record['end'],
                                 sha256=sha256(Path(path).read_bytes()).hexdigest()))
        rows = retained_parts(rows, cutoff)
        if not existing and getattr(self,'config',{}).get('training_cadence','daily')=='six_hourly':rows=long_part_prefix(rows)
        for row in rows:
            if sha256(_owned_bytes(Path(row['path']),32000000)).hexdigest()!=row['sha256']:raise ValueError('retained raw measurement bytes changed')
        start = datetime.fromisoformat(rows[-1]['end']) if rows else max(
            cutoff - timedelta(days=7), datetime.fromisoformat(self.capture_config['native_cutover']))
        for left, right in capture_windows(start, cutoff):
            self.guard()
            attempt = directory(self.state / ('capture-' + uuid4().hex))
            config_path = attempt / 'config.json'
            save(config_path, dict(self.capture_config, start=left.isoformat(), end=right.isoformat()))
            output = directory(attempt / 'output')
            self.worker(['/usr/bin/python3', str(self.repo / 'scripts/capture-thermal-inputs.py'),
                '--config', str(config_path), '--destination', str(output), '--receipt-version', '2',
                '--worker', '--expected-config-digest', sha256(config_path.read_bytes()).hexdigest()])
            receipt = read(output / 'capture-receipt.json')
            path = output / (receipt['snapshot_sha256'] + '.training-inputs-v2.json')
            record = read_training_inputs_v2(path)
            if (datetime.fromisoformat(record['start']), datetime.fromisoformat(record['end'])) != (left, right):
                raise ValueError('captured history differs from requested interval')
            rows.append(dict(path=str(path), start=record['start'], end=record['end'],
                             sha256=sha256(path.read_bytes()).hexdigest()))
            rows = retained_parts(rows, cutoff)
            save(index, rows)
        for row in rows:
            if sha256(_owned_bytes(Path(row['path']), 32000000)).hexdigest() != row['sha256']:
                raise ValueError('retained raw measurement bytes changed')
        save(index, rows)
        return [Path(row['path']) for row in rows]

    def snapshot(self, run, cutoff):
        paths = self.raw_parts(cutoff)
        if len(paths) < 2:
            raise ValueError('at least two raw measurement intervals required')
        script = self.repo / 'scripts/assemble-thermal-inputs.py'
        spec = importlib.util.spec_from_file_location('native_daily_assembly', script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        destination = directory(run / 'assembly')
        dsn = Path(self.capture_config['journal_dsn_file'])
        _, _, digest = module._context(paths, dsn, destination)
        command = ['/usr/bin/python3', str(script), '--journal-dsn-file', str(dsn),
            '--destination', str(destination), '--receipt-version', '2', '--worker',
            '--expected-context-digest', digest]
        for path in paths:
            command.extend(['--part', str(path)])
        self.worker(command)
        receipt = read(destination / 'assembly-receipt.json')
        return destination / (receipt['snapshot_sha256'] + '.training-inputs-v2.json')

    def geometry(self, run, record, previous):
        from astro_geometry_series import build_series_request, split_series_request, build_series
        from astro_geometry import build_source
        from astro_geometry_worker import capture_batch, runtime_identity
        import openhab_sanity_check as oh
        settings = read(Path(previous['stage']).parent / 'geometry-libraries.json', 8192)
        libraries = {k: Path(v) for k, v in settings['library_paths'].items()}
        def metadata():
            thing = oh.get('/things/astro:sun:local', timeout=3)
            addon = oh.get('/addons/binding-astro', timeout=3)
            context = json.loads(oh.get('/items/Astro_Forecast_Context_JSON', timeout=3)['state'])
            return dict(binding_version=addon['version'], installed=addon['installed'],
                status=thing['statusInfo']['status'], geolocation=thing['configuration']['geolocation'],
                timezone=context['timezone'])
        source = metadata()
        if not (source['installed'] and source['status'] == 'ONLINE' and source['timezone'] == self.config['timezone']):
            raise ValueError('native Astro source unavailable or timezone differs')
        latitude, longitude = map(float, source['geolocation'].split(','))
        runtime = runtime_identity(libraries, binding_version=source['binding_version'], guard=self.guard)
        points = []
        at, end = datetime.fromisoformat(record['start']), datetime.fromisoformat(record['end'])
        while at < end:
            points.append(at)
            at += timedelta(minutes=5)
        request = build_series_request(points, requested_at=datetime.now(timezone.utc),
            latitude=latitude, longitude=longitude, timezone_name=source['timezone'])
        scratch = directory(run / 'geometry')
        caches = []
        chunks = split_series_request(request)
        for index, chunk in enumerate(chunks):
            self.guard()
            origin = build_source(chunk, observed_at=datetime.now(timezone.utc), native_runtime=runtime,
                source_status=source['status'], latitude=latitude, longitude=longitude,
                timezone_name=source['timezone'], altitude_m=None)
            from household_cycle_resources import publication_geometry_policy
            with publication_geometry_policy():
                cache = capture_batch(chunk, origin, library_paths=libraries, scratch=scratch, guard=self.guard)
            caches.append(cache)
            print(json.dumps(dict(status='training_geometry', completed=index + 1, total=len(chunks))), flush=True)
        if metadata() != source:
            raise ValueError('native Astro metadata changed during training acquisition')
        geometry = build_series(request, caches, expected_native_runtime=runtime)
        path = scratch / (geometry.sha256 + '.native-geometry-series-v1.json')
        save(path, geometry.to_dict())
        return geometry, path, settings

    def prepare(self, cutoff, previous):
        from thermal_model.training_inputs import read_training_inputs_v2
        from native_thermal_inputs import build_native_development
        from native_thermal_fit import fit_native_development
        from native_thermal_artifact import current_native_runtime
        run = directory(self.state / (cutoff.strftime('%Y%m%d') + '-' + uuid4().hex))
        save(self.state / 'current-run.json', dict(run=str(run), cutoff=cutoff.isoformat(), previous=previous))
        snapshot = self.snapshot(run, cutoff)
        record = read_training_inputs_v2(snapshot)
        if datetime.fromisoformat(record['end']) != cutoff:
            raise ValueError('assembled training history does not reach daily cutoff')
        geometry, geometry_path, libraries = self.geometry(run, record, previous)
        phases = {role: info['sensor_epoch'] for role, info in record['temperature_evidence']['roles'].items()}
        data = build_native_development(record, expected_snapshot_sha256=record['snapshot_sha256'],
            sensor_epochs=phases, geometry=geometry, expected_series_sha256=geometry.sha256,
            assessed_at=datetime.now(timezone.utc))
        dataset = run / (data.sha256 + '.native-development-data-v1.json')
        save(dataset, data.to_dict())
        runtime = current_native_runtime(guard=self.guard)
        os.environ['EARTHSHIP_QUALIFICATION_FIT'] = '1'
        os.environ['EARTHSHIP_REMOTE_QUALIFICATION_FIT'] = '0'
        fit = fit_native_development(data, expected_dataset_sha256=data.sha256,
            training_start=data.development.start, training_end=data.development.end,
            guard=self.guard, timeout_seconds=85, joint=True, irradiance=True)
        if current_native_runtime(guard=self.guard) != runtime:
            raise ValueError('native fitted runtime changed during training')
        commit = subprocess.check_output(['git', '-C', str(self.repo), 'rev-parse', 'HEAD'], text=True).strip()
        evidence = dict(schema='earthship-native-development-fit-evidence/v4',
            created_at=datetime.now(timezone.utc).isoformat(), code_revision=commit, fit_runtime=runtime,
            fit=fit, release_authorized=False, production_model_changed=False)
        evidence_path = run / 'fit-evidence.json'
        save(evidence_path, evidence)
        originals = dict(snapshot=snapshot, dataset=dataset, geometry=geometry_path, fit_evidence=evidence_path)
        return self.package(run, originals, runtime, previous, libraries, commit)

    def active_score_history(self,references,*,now):
        """Keep explicit stages used by the scorer's existing active folders.

        Unknown frozen archive policies remain retained. Binding discovery only
        filters already owned selections; it never authorizes another model.
        No forecast, completion, score, stage or original source is removed.
        """
        import household_cycle_deploy as deploy
        from native_thermal_artifact import _read as read_binding
        from thermal_model.native_operational_io import _folders
        from thermal_model.graduation_policy import _sha
        if type(references) is not tuple or len(references)>63:raise ValueError('bounded explicit score history required')
        policy='openhab/scripts/thermal_model/native_operational_io.py'
        current=sha256((Path(__file__).parent/'thermal_model/native_operational_io.py').read_bytes()).hexdigest()
        roots=set();unknown=set();seen=set()
        for ref in references:
            self.guard();stage=Path(ref['stage']);key=(str(stage),_sha(ref['deployment_sha256']))
            if key in seen:raise ValueError('unique owned score history required')
            seen.add(key)
            manifest=deploy._bytes(stage/'deployment.json',private=True,maximum=131072)
            if sha256(manifest).hexdigest()!=key[1]:raise ValueError('retained score stage pin differs')
            record=deploy.verify_stage(stage,expected_deployment_sha256=key[1])
            if record['source_manifest'].get(policy)!=current:
                unknown.add(key);continue
            cycle=read(stage/'cycle.json',8192);settings=read(cycle['forecast_config'],8192)
            roots.add(Path(settings['evidence_directory']))
        needed=set(unknown);fields={'schema','capture_sha256','artifact_sha256','runtime_sha256','issued_at','stage','deployment_sha256',
            'model_receipt_path','model_receipt_sha256','automatic_actuation','binding_sha256'}
        for root in roots:
            self.guard()
            if root.is_symlink():raise ValueError('original scoring archive cannot be a symlink')
            if not root.exists():continue
            paths=[p for folder in _folders(root,'origins',now) for p in folder.glob('*.native-serving-model-binding-v1.json')]
            if len(paths)>4096:raise ValueError('bounded original scoring binding inventory required')
            for path in paths:
                self.guard();_,value=read_binding(path,8192)
                if (set(value)!=fields or value['schema']!='earthship-native-serving-model-binding/v1' or value['automatic_actuation'] is not False or
                    value['binding_sha256']!=sha256(json.dumps({k:v for k,v in value.items() if k!='binding_sha256'},sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest() or
                    path.name!=_sha(value['capture_sha256'])+'.native-serving-model-binding-v1.json'):
                    raise ValueError('original scoring capture binding differs')
                needed.add((value['stage'],_sha(value['deployment_sha256'])))
        return tuple(ref for ref in references if (ref['stage'],ref['deployment_sha256']) in needed)

    def package(self, run, originals, runtime, previous, libraries, commit):
        from native_thermal_artifact import write_native_candidate
        from native_model_serving_receipt import admit_model
        import household_cycle_deploy as deploy
        from household_native_family import prepare_score_dispatch, prepare
        from household_forecast_score import read_score_dispatch
        cycle = read(Path(previous['stage']) / 'cycle.json')
        settings = read(cycle['forecast_config'], 8192)
        previous_candidate = read(settings['candidate_path'])
        if previous_candidate['artifact_sha256'] != settings['artifact_sha256']:
            raise ValueError('previous model selection differs')
        candidate = build_deployment_candidate(originals=originals, runtime=runtime,
            previous=previous_candidate, created_at=datetime.now(timezone.utc), guard=self.guard)
        old = read_score_dispatch(Path(previous['stage']),
            deployment_sha256=previous['deployment_sha256'], guard=self.guard)
        admission = retained_model_admission(candidate,
            selections=[{k:previous[k] for k in ('stage','deployment_sha256')},*old['historical']],guard=self.guard)
        if admission is None:
            path = write_native_candidate(directory(run / 'candidate'), candidate,
                assessed_at=datetime.now(timezone.utc), runtime=runtime,
                expected_artifact_sha256=candidate['artifact_sha256'], guard=self.guard)
            receipt = admit_model(path, runtime=runtime, expected_artifact_sha256=candidate['artifact_sha256'],
                directory=directory(run / 'receipts'), clock=lambda: datetime.now(timezone.utc), guard=self.guard)
            receipt_pin = sha256(receipt.read_bytes()).hexdigest()
        else:
            path=Path(admission['candidate_path']);receipt=Path(admission['receipt_path'])
            receipt_pin=admission['receipt_sha256']
        save(run / 'model-admission.json',dict(reused=admission is not None,original=admission))
        settings.update(candidate_path=str(path), artifact_sha256=candidate['artifact_sha256'],
            runtime_sha256=candidate['runtime_sha256'], model_receipt_path=str(receipt),
            model_receipt_sha256=receipt_pin, geometry_directory=str(directory(run / 'geometry-live')))
        config = run / 'final-config.json'
        save(config, settings)
        save(run / 'geometry-libraries.json', libraries)
        active=self.active_score_history(tuple(old['historical']),now=datetime.now(timezone.utc))
        save(run/'score-history-window.json',dict(schema='earthship-native-score-history-window/v1',checked_at=datetime.now(timezone.utc).isoformat(),
            scope='existing_three_UTC_date_scoring_window',retained=list(active),retired_from_active_queue=[v for v in old['historical'] if v not in active],archives_modified=False,automatic_actuation=False))
        historical = tuple([*active, {k: previous[k] for k in ('stage', 'deployment_sha256')}])
        dispatch = prepare_score_dispatch(historical_selections=historical,
            output=run / 'score-dispatch.json', guard=self.guard)
        stage = run / 'final'
        deploy.stage_deployment(repo_root=self.repo, stage=stage, forecast_config=config,
            parameters=Path(self.inputs['parameters']), parameters_sha256=self.inputs['parameters_sha256'],
            observation_cache=Path(self.inputs['observation_cache']), service_file=Path(self.inputs['service_file']),
            code_revision=commit, service_forecast_config=Path(self.inputs['service_base_config']),
            model_receipt_path=receipt, model_receipt_sha256=receipt_pin,
            score_dispatch_path=Path(dispatch['path']), score_dispatch_sha256=dispatch['sha256'])
        pin = sha256((stage / 'deployment.json').read_bytes()).hexdigest()
        prepare(stage, run / 'geometry-libraries.json', run / 'family', guard=self.guard, deployment_sha256=pin)
        selection = dict(stage=str(stage), deployment_sha256=pin, artifact_sha256=candidate['artifact_sha256'],
                         trained_through=candidate['fit']['training_end'])
        save(run / 'final-selection.json', selection)
        save(run / 'activation-input.json', dict(selection=selection, previous=previous))
        return selection

    def activate(self, selection, previous):
        # The transaction executes from the exact newly packaged source closure.
        run = Path(selection['stage']).parent
        environment = dict(os.environ, PYTHONPATH=str(Path(selection['stage']) / 'sources/openhab/scripts')
                           + ':/home/sat/Solar_PV/analytics/src')
        subprocess.run(['/usr/bin/python3', '-m', 'household_native_daily', '--activate', str(run)],
                       env=environment, check=True, timeout=600)
        return read(run / 'activation-result.json')


def wait_for_handoff_window(*,guard,read_pids,clock=lambda:datetime.now(timezone.utc),
                            monotonic=time.monotonic,sleep=time.sleep,seconds=240):
    """Wait before private preparation; never retry a begun handoff.

    The preparer reserves the last120s before the next original issue. Allow
    150s for its75s budget, the protected35s boundary and transaction overhead.
    Keep checking worker idleness and resource pressure through the wait.
    """
    from thermal_model.native_operational_io import _next_issue
    if type(seconds) not in (int,float) or not 0<seconds<=240:
        raise ValueError('bounded native handoff wait required')
    deadline=monotonic()+seconds
    while True:
        guard()
        if monotonic()>=deadline:raise TimeoutError('owned serving preparation window did not become idle')
        pids=read_pids();now=clock();issue=_next_issue(now)
        if not isinstance(pids,list) or len(pids)!=3 or any(not isinstance(p,str) or not p.isdecimal() for p in pids):
            raise ValueError('three original serving worker identities required')
        if pids==['0','0','0'] and issue-now>=timedelta(seconds=150):return issue
        sleep(1)


def activate(run):
    """Use the existing five-file handoff, restoring the owned timer states."""
    import household_native_handoff as handoff
    import household_native_install as install
    from thermal_model.capture_guard import SharedScoreLock
    run = Path(run)
    context = read(run / 'activation-input.json')
    selection, previous = context['selection'], context['previous']
    stage = Path(selection['stage'])
    if Path(handoff.__file__).resolve() != stage / 'sources/openhab/scripts/household_native_handoff.py':
        raise ValueError('exact selected transaction source required')
    guard = RamGuard(seconds=540)
    units = ('thermal-provisional-forecast.service', 'thermal-provisional-score.service',
             'thermal-native-geometry-prepare.service')
    wait_for_handoff_window(guard=guard,read_pids=lambda:[
        subprocess.check_output(['systemctl','--user','show',u,'-p','MainPID','--value'],
                                text=True,timeout=10).strip() for u in units])
    expected = {k: previous[k] for k in ('stage', 'deployment_sha256')}
    settings = read(run / 'final-config.json', 8192)
    from household_cycle_deploy import verify_stage
    record = verify_stage(stage, expected_deployment_sha256=selection['deployment_sha256'])
    unit_root = Path(record['service_file']).parent
    # The old preparer's last packet belongs to the old artifact. Warm this
    # exact staged model before replacing its source or pausing serving timers.
    from household_native_geometry_prepare import run as prepare_geometry
    from native_thermal_live import geometry_path, read_geometry, GEOMETRY_MAX
    from thermal_model.native_operational_io import _next_issue
    prepared = prepare_geometry(run / 'final-config.json', run / 'geometry-libraries.json',
        stage=stage, deployment_sha256=selection['deployment_sha256'])
    issue = _next_issue(datetime.now(timezone.utc))
    geometry = geometry_path(settings, issue)
    if prepared.get('status') != 'prepared' or prepared.get('path') != str(geometry):
        raise ValueError('next-issue model-bound geometry required before handoff')
    geometry_original = _owned_bytes(geometry, GEOMETRY_MAX)
    with SharedScoreLock(settings['shared_lock']) as lock:
        def check():
            lock.verify()
            guard()
            # Preserve the preparer's existing 35-second boundary, before the
            # forecast warm slot. A late transaction must restore the old files.
            if datetime.now(timezone.utc) >= issue - timedelta(seconds=35):
                raise ValueError('prepared geometry handoff window elapsed')
            if _owned_bytes(geometry, GEOMETRY_MAX) != geometry_original:
                raise ValueError('prepared handoff geometry changed')
        read_geometry(settings, issue=issue, guard=check)
        with install._quiesce_timers(unit_root, guard=check, include_preparer=True) as restoration:
            try:
                if effective_selection() != expected:
                    raise ValueError('active model changed while daily training was running')
                from native_model_serving_receipt import load_serving_selection, read_serving_model
                model = read_serving_model(load_serving_selection(stage,
                    expected_deployment_sha256=selection['deployment_sha256'],
                    assessed_at=datetime.now(timezone.utc), guard=check),
                    assessed_at=datetime.now(timezone.utc), guard=check)
                if datetime.fromisoformat(model.candidate['fit']['training_end']) <= datetime.fromisoformat(previous['trained_through']):
                    raise ValueError('daily training coverage must advance')
                handoff.prepare(run / 'family', previous_forecast_stage=Path(previous['stage']),
                    previous_score_stage=Path(previous['stage']), previous_family=Path(previous['stage']).parent / 'family',
                    previous_deployment_sha256=previous['deployment_sha256'], output=run / 'handoff', guard=check)
                result = install._activate_handoff(run / 'handoff', guard=check)
            except Exception as error:
                if isinstance(error, install.PreparerReconciliationRequired) or any(
                    'quiescent' in note or 'cleanup unproven' in note.lower() or 'Concurrent changes' in note
                    for note in getattr(error, '__notes__', [])):
                    restoration['safe'] = False
                raise
    save(run / 'activation-result.json', result)
    return result
