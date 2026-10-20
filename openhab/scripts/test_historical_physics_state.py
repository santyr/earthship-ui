from datetime import timedelta
from test_household_pv_window import START
from household_native_training import directory,save


def test_intraday_capture_rolls_by_local_date_and_reuses_only_earlier_long_prefix(tmp_path):
    from historical_physics_train import cadence_capture_state
    directory(tmp_path/'state');rows=[]
    for i,hours in enumerate((48,48,6,6,6,6,6,6)):
        left=START+timedelta(hours=sum((48,48,6,6,6,6,6,6)[:i]));right=left+timedelta(hours=hours)
        rows.append(dict(start=left.isoformat(),end=right.isoformat(),path='/original/'+str(i)))
    save(tmp_path/'state/raw-parts.json',rows)
    first,seed=cadence_capture_state(tmp_path,START+timedelta(days=5))
    assert seed==['/original/0','/original/1']
    same,_=cadence_capture_state(tmp_path,START+timedelta(days=5,hours=1));assert same==first
    later,_=cadence_capture_state(tmp_path,START+timedelta(days=6));assert later!=first
    assert __import__('json').loads((tmp_path/'state/raw-parts.json').read_bytes())==rows
