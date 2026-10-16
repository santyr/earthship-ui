"""Daily orchestration delegates strict acquisition to an admitted child."""
from pathlib import Path
import os


def test_daily_worker_uses_counted_collection_scope(monkeypatch,tmp_path):
    from household_native_training import NativeTraining
    import thermal_model.training_pressure_guard as runner
    backend=object.__new__(NativeTraining);backend.repo=tmp_path;backend.guard=lambda:None
    calls=[]
    monkeypatch.setattr(runner,'run_training_worker',lambda argv,**kw:(calls.append((argv,kw)) or (0,b'')))
    original=['/usr/bin/python3','/fixture/capture.py','--config','/fixture/private.json']
    backend.worker(original,seconds=90)
    argv,kwargs=calls[0]
    assert argv[:2]==['/usr/bin/python3',str(Path(__import__('household_native_training').__file__).with_name('household_job_run.py'))]
    assert '--collection' in argv and argv[argv.index('--')+1:]==original
    assert argv[argv.index('--preferred-mib')+1]=='256'
    assert kwargs['seconds']==90 and kwargs['check'] is backend.guard
    assert kwargs['env']['EARTHSHIP_GUARDED_CAPTURE_WORKER']=='1'
