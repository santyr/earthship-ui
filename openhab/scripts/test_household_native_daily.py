"""Daily training advances the local-day boundary without redundant fitting."""
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import pytest


def daily():
    path=Path(__file__).with_name('household_native_daily.py')
    assert path.exists(), 'daily native scheduler has not been implemented'
    spec=importlib.util.spec_from_file_location('daily_test_subject',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('now,expected', [
    ('2026-10-15T12:50:00+00:00','2026-10-15T06:00:00+00:00'),
    ('2026-11-02T13:50:00+00:00','2026-11-02T07:00:00+00:00'),
    ('2026-10-15T05:59:00+00:00','2026-10-14T06:00:00+00:00'),
])
def test_cutoff_is_last_local_midnight_including_dst(now,expected):
    assert daily().training_cutoff(datetime.fromisoformat(now),'America/Denver').isoformat()==expected


def test_capture_chunks_cover_only_missing_days_without_gaps():
    m=daily();start=datetime(2026,10,12,6,tzinfo=timezone.utc);end=datetime(2026,10,17,6,tzinfo=timezone.utc)
    chunks=m.capture_windows(start,end)
    assert chunks==[(start,datetime(2026,10,14,6,tzinfo=timezone.utc)),(datetime(2026,10,14,6,tzinfo=timezone.utc),datetime(2026,10,16,6,tzinfo=timezone.utc)),(datetime(2026,10,16,6,tzinfo=timezone.utc),end)]


class Backend:
    def __init__(self,trained,fail=None):self.trained=trained;self.calls=[];self.fail=fail
    def current(self):return {'trained_through':self.trained,'stage':'old','deployment_sha256':'old-pin'}
    def prepare(self,cutoff,previous):
        self.calls.append(('prepare',cutoff,previous));return {'stage':'new'}
    def activate(self,selection,previous):
        self.calls.append(('activate',selection,previous))
        if self.fail:raise ValueError(self.fail)
        return {'status':'native_family_activated'}


def test_current_model_skips_capture_fit_and_handoff():
    b=Backend('2026-10-14T06:00:00+00:00')
    result=daily().run_daily(b,now=datetime(2026,10,14,18,tzinfo=timezone.utc),timezone_name='America/Denver')
    assert result['status']=='already_current';assert b.calls==[]


def test_next_day_prepares_then_activates_with_original_selection():
    b=Backend('2026-10-14T06:00:00+00:00')
    result=daily().run_daily(b,now=datetime(2026,10,15,13,tzinfo=timezone.utc),timezone_name='America/Denver')
    assert result['status']=='native_family_activated'
    assert b.calls[0][1]==datetime(2026,10,15,6,tzinfo=timezone.utc)
    assert b.calls[1][2]['deployment_sha256']=='old-pin'


def test_failed_preparation_never_changes_live_selection():
    b=Backend('2026-10-14T06:00:00+00:00')
    def refuse(*args):raise ValueError('insufficient usable data')
    b.prepare=refuse
    with pytest.raises(ValueError,match='insufficient usable data'):
        daily().run_daily(b,now=datetime(2026,10,15,13,tzinfo=timezone.utc),timezone_name='America/Denver')
    assert b.calls==[]


def test_rolling_parts_keep_crossing_interval_but_drop_expired_parts():
    m=daily();target=datetime(2026,10,20,6,tzinfo=timezone.utc)
    rows=[{'path':'a','start':'2026-10-11T06:00:00+00:00','end':'2026-10-13T06:00:00+00:00'}, {'path':'b','start':'2026-10-13T06:00:00+00:00','end':'2026-10-15T06:00:00+00:00'}, {'path':'c','start':'2026-10-15T06:00:00+00:00','end':'2026-10-17T06:00:00+00:00'}]
    assert m.retained_parts(rows,target)==rows[1:]
    rows[2]['start']='2026-10-16T06:00:00+00:00'
    with pytest.raises(ValueError,match='adjacent'):m.retained_parts(rows,target)


def test_training_builds_real_new_fit_evidence_before_packaging(tmp_path,monkeypatch):
    import json
    import household_native_training as training
    import native_thermal_artifact as artifacts
    from test_installed_shade_inputs import snapshot, END
    from test_native_thermal_inputs import geometry
    from thermal_model.training_inputs import write_training_inputs_v2
    tmp_path.chmod(0o700)
    record=snapshot();source=tmp_path/'source';source.mkdir(mode=0o700)
    write_training_inputs_v2(source,record)
    snapshot_path=source/(record['snapshot_sha256']+'.training-inputs-v2.json')
    geom=geometry(record)
    geom_path=tmp_path/'geometry.json';training.save(geom_path,geom.to_dict())
    backend=training.NativeTraining.__new__(training.NativeTraining)
    backend.state=tmp_path;backend.repo=Path(__file__).resolve().parents[2];backend.guard=lambda:None
    backend.snapshot=lambda run,cutoff:snapshot_path
    backend.geometry=lambda run,rec,previous:(geom,geom_path,{})
    monkeypatch.setattr(artifacts,'current_native_runtime',lambda **kwargs:{'test_binding':'unchanged'})
    packaged=[]
    def package(run,originals,runtime,previous,libraries,commit):
        evidence=json.loads(originals['fit_evidence'].read_bytes())
        assert evidence['fit']['fit_executed'] is True
        assert datetime.fromisoformat(evidence['fit']['training_end'])==END
        assert evidence['fit']['endpoint_count']>0
        assert evidence['fit_runtime']==runtime
        assert evidence['production_model_changed'] is False
        packaged.append(originals)
        return {'trained_through':evidence['fit']['training_end']}
    backend.package=package
    result=backend.prepare(END,{'stage':'unused'})
    assert datetime.fromisoformat(result['trained_through'])==END
    assert len(packaged)==1


def test_raw_part_fingerprint_drift_is_rejected_without_recapture(tmp_path):
    import household_native_training as training
    tmp_path.chmod(0o700)
    path=tmp_path/'raw.json';training.save(path,{'changed':True})
    training.save(tmp_path/'raw-parts.json',[dict(path=str(path),start='2026-10-14T06:00:00+00:00',
        end='2026-10-15T06:00:00+00:00',sha256='0'*64)])
    backend=training.NativeTraining.__new__(training.NativeTraining)
    backend.state=tmp_path;backend.capture_config={};backend.guard=lambda:None
    with pytest.raises(ValueError,match='bytes changed'):
        backend.raw_parts(datetime(2026,10,15,6,tzinfo=timezone.utc))


def test_first_run_creates_owned_lock_and_concurrent_run_refuses(tmp_path):
    import household_native_training as training
    tmp_path.chmod(0o700)
    lock=tmp_path/'daily.lock'
    assert hasattr(training,'daily_lock'), 'first-run daily lock initialization is missing'
    with training.daily_lock(lock):
        inode=lock.stat().st_ino
        with pytest.raises(BlockingIOError):
            with training.daily_lock(lock):pass
    with training.daily_lock(lock):assert lock.stat().st_ino==inode
    assert lock.stat().st_mode & 0o777 == 0o600


def test_load_domain_refresh_runs_even_when_thermal_is_already_current():
    b=Backend('2026-10-15T06:00:00+00:00');calls=[]
    b.prepare_ac_load=lambda cutoff:calls.append(cutoff) or dict(status='load_profile_prepared')
    result=daily().run_daily(b,now=datetime(2026,10,15,13,tzinfo=timezone.utc),timezone_name='America/Denver')
    assert result['status']=='already_current' and result['ac_load']['status']=='load_profile_prepared'
    assert calls==[datetime(2026,10,15,6,tzinfo=timezone.utc)] and b.calls==[]


def test_load_failure_is_sanitized_and_does_not_prevent_thermal_refresh():
    b=Backend('2026-10-14T06:00:00+00:00');calls=[]
    def failed(cutoff):calls.append(cutoff);raise ValueError('private source detail must not be published')
    b.prepare_ac_load=failed
    result=daily().run_daily(b,now=datetime(2026,10,15,13,tzinfo=timezone.utc),timezone_name='America/Denver')
    assert result['status']=='native_family_activated' and len(calls)==1
    assert result['ac_load']==dict(status='deferred',reason='load_profile_refresh_failed',automatic_actuation=False)
    assert 'private source' not in str(result)


def test_load_refresh_precedes_thermal_selection_and_retains_its_own_status():
    b=Backend('2026-10-14T06:00:00+00:00');calls=[]
    b.prepare_ac_load=lambda cutoff:calls.append('load') or dict(status='load_profile_prepared')
    def failed_current():calls.append('thermal');raise ValueError('thermal selection unavailable')
    b.current=failed_current
    with pytest.raises(ValueError,match='thermal selection unavailable'):
        daily().run_daily(b,now=datetime(2026,10,15,13,tzinfo=timezone.utc),timezone_name='America/Denver')
    assert calls==['load','thermal']
