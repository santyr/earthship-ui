from copy import deepcopy
from datetime import timedelta
from test_household_pv_window import START
from test_weather_directional_pv import rows
from weather_learning.contracts import identity


def test_identical_pv_training_evidence_preserves_original_model_clock():
    from weather_learning.pv_refresh import directional_if_changed, effective_if_changed
    data=rows();cutoff=START+timedelta(days=8);now=START+timedelta(days=20)
    for fit in (directional_if_changed,effective_if_changed):
        model,executed=fit(None,data,cutoff=cutoff,trained_at=now)
        assert executed is True
        again,executed=fit(model,data,cutoff=cutoff,trained_at=now+timedelta(days=1))
        assert executed is False and again==model
        changed=deepcopy(data);changed[0]['outcome_w']+=50
        changed[0]['pair_sha256']=identity({k:v for k,v in changed[0].items() if k!='pair_sha256'})
        fresh,executed=fit(model,changed,cutoff=cutoff,trained_at=now+timedelta(days=1))
        assert executed is True and fresh['model_sha256']!=model['model_sha256']


def test_pv_challenger_requires_later_comparisons_and_beats_incumbent():
    from weather_learning.pv_refresh import compare_incumbent
    from weather_learning.pv_directional_calibration import fit_directional
    data=rows();cutoff=START+timedelta(days=8)
    incumbent=fit_directional(data,cutoff=START+timedelta(days=3),trained_at=START+timedelta(days=3))
    candidate=fit_directional(data,cutoff=cutoff,trained_at=START+timedelta(days=14))
    for r in data:
        r['origin']=(__import__('datetime').datetime.fromisoformat(r['start'])-timedelta(hours=1)).isoformat()
        r['pair_sha256']=identity({k:v for k,v in r.items() if k!='pair_sha256'})
    result=compare_incumbent(candidate,incumbent,data,holdout_start=cutoff,holdout_end=START+timedelta(days=13))
    assert result['selected'] is True and result['candidate_mae_w']<result['incumbent_mae_w']
    # A fitted incumbent cannot be treated as available for earlier targets.
    late=deepcopy(incumbent);late['trained_at']=(START+timedelta(days=13)).isoformat()
    late['model_sha256']=identity({k:v for k,v in late.items() if k!='model_sha256'})
    result=compare_incumbent(candidate,late,data,holdout_start=cutoff,holdout_end=START+timedelta(days=13))
    assert result['selected'] is False and result['pairs']==0


def test_pv_candidate_does_not_replace_a_better_incumbent():
    from weather_learning.pv_refresh import compare_incumbent
    from weather_learning.pv_directional_calibration import fit_directional
    data=rows();cutoff=START+timedelta(days=8)
    incumbent=fit_directional(data,cutoff=cutoff,trained_at=cutoff)
    candidate=fit_directional(data,cutoff=START+timedelta(days=3),trained_at=START+timedelta(days=14))
    for r in data:
        r['origin']=(__import__('datetime').datetime.fromisoformat(r['start'])-timedelta(hours=1)).isoformat()
        r['pair_sha256']=identity({k:v for k,v in r.items() if k!='pair_sha256'})
    result=compare_incumbent(candidate,incumbent,data,holdout_start=cutoff,holdout_end=START+timedelta(days=13))
    assert result['selected'] is False and result['incumbent_mae_w']<result['candidate_mae_w']


def test_recorded_pv_origin_uses_actual_ingestion_and_sorting():
    from weather_learning.pv_training_sources import forecast_origin, ordered_runs
    snapshot={'initialized_at':START.isoformat(),'ingestion_completed_at':(START+timedelta(hours=3,minutes=13)).isoformat()}
    assert forecast_origin(snapshot,recorded=True)==START+timedelta(hours=4)
    assert forecast_origin(snapshot,recorded=False)==START+timedelta(hours=9)
    runs=[(START+timedelta(hours=9),'a',{},'historical'),(START+timedelta(hours=4),'b',{},'recorded')]
    assert [r[1] for r in ordered_runs(runs)]==['b','a']


def test_selection_retains_current_model_without_independent_evidence(tmp_path):
    from test_weather_pv_calibration_source import source
    from historical_pv_daily import select_candidate
    from weather_learning.contracts import canonical
    load,path,now=source(tmp_path)
    before=path.read_bytes();candidate=__import__('json').loads(before)
    from weather_learning.pv_directional_calibration import fit_directional
    training=fit_directional(rows(),cutoff=START+timedelta(days=8),trained_at=now)
    candidate['training_model_sha256']=training['model_sha256']
    candidate['report'].update(model_sha256=training['model_sha256'],holdout_start=(START+timedelta(days=8)).isoformat(),holdout_end=(START+timedelta(days=13)).isoformat())
    candidate['report']['report_sha256']=identity({k:v for k,v in candidate['report'].items() if k!='report_sha256'})
    candidate['receipt_sha256']=identity({k:v for k,v in candidate.items() if k!='receipt_sha256'})
    result=select_candidate(candidate,rows(),training_model=training,selected_path=path,now=now,system_raw=b'{}',horizon_raw=b'{}')
    assert result['status']=='incumbent_preserved' and path.read_bytes()==before
    assert result['comparison']['pairs']==0
    # Expiry is enforced by the serving loader, not renewed by an assessment.
    import pytest
    with pytest.raises(ValueError,match='expired'):
        load(path,origin=now+timedelta(days=15),system_raw=b'{}',horizon_raw=b'{}')


def test_previous_pv_model_reuse_rejects_modified_model_bytes(tmp_path):
    import json,pytest
    from hashlib import sha256
    from test_weather_pv_calibration_source import source
    from weather_learning.pv_refresh import previous_models
    from weather_learning.contracts import canonical
    load,path,now=source(tmp_path);receipt=json.loads(path.read_bytes())
    run=tmp_path/'run';run.mkdir(mode=0o700)
    receipt['training_model_sha256']=receipt['final_model']['model_sha256']
    receipt['receipt_sha256']=identity({k:v for k,v in receipt.items() if k!='receipt_sha256'})
    for filename,value in [('experiment.json',receipt),('training-model.json',receipt['final_model']),('final-model.json',receipt['final_model'])]:
        p=run/filename;p.write_bytes(canonical(value));p.chmod(0o600)
    pointer=tmp_path/'last-experiment.json';pointer.write_bytes(canonical(dict(path=str(run),receipt_sha256=receipt['receipt_sha256'])));pointer.chmod(0o600)
    from pathlib import Path
    scripts=Path(__file__).parent
    sources={'openhab/scripts/weather_learning/'+n:(scripts/'weather_learning'/n).read_bytes() for n in ['pv_calibration.py','pv_directional_calibration.py','contracts.py']}
    assert previous_models(tmp_path,sources)['final_model']==receipt['final_model']
    p=run/'final-model.json';value=json.loads(p.read_bytes());value['model_sha256']='f'*64;p.write_bytes(canonical(value))
    with pytest.raises(ValueError,match='model differs'):previous_models(tmp_path,sources)


def test_selection_publishes_improved_candidate_atomically(tmp_path):
    import json
    from test_weather_pv_calibration_source import source
    from historical_pv_daily import select_candidate
    from weather_learning.pv_directional_calibration import fit_directional,assess_directional
    from weather_learning.contracts import canonical
    load,path,now=source(tmp_path);old=json.loads(path.read_bytes());data=rows()
    for r in data:
        r['origin']=(__import__('datetime').datetime.fromisoformat(r['start'])-timedelta(hours=1)).isoformat()
        r['pair_sha256']=identity({k:v for k,v in r.items() if k!='pair_sha256'})
    old_time=START+timedelta(days=3)
    old['created_at']=old_time.isoformat();old['final_model']=fit_directional(data,cutoff=old_time,trained_at=old_time)
    old['receipt_sha256']=identity({k:v for k,v in old.items() if k!='receipt_sha256'});path.write_bytes(canonical(old))
    cutoff=START+timedelta(days=8);end=START+timedelta(days=13)
    training=fit_directional(data,cutoff=cutoff,trained_at=now)
    candidate=deepcopy(old);candidate.update(created_at=now.isoformat(),training_model_sha256=training['model_sha256'],final_model=fit_directional(data,cutoff=end,trained_at=now),report=assess_directional(training,data,holdout_start=cutoff,holdout_end=end))
    candidate['receipt_sha256']=identity({k:v for k,v in candidate.items() if k!='receipt_sha256'})
    result=select_candidate(candidate,data,training_model=training,selected_path=path,now=now,system_raw=b'{}',horizon_raw=b'{}')
    assert result['status']=='candidate_selected' and json.loads(path.read_bytes())==candidate
    assert load(path,origin=now,system_raw=b'{}',horizon_raw=b'{}')['model']==candidate['final_model']


def test_energy_rolling_index_retains_original_files_and_limits_active_range():
    from historical_energy_capture import rolling_rows
    existing={str(i):dict(start=(START+timedelta(hours=i)).isoformat()) for i in range(72)}
    # Index keys are canonical times; files do not participate in this filter.
    existing={v['start']:v for v in existing.values()}
    active=rolling_rows(existing,start=START+timedelta(days=1),end=START+timedelta(days=3))
    assert len(active)==48 and min(active)==(START+timedelta(days=1)).isoformat()
    assert len(existing)==72


def test_expired_unchanged_candidate_is_explicitly_unavailable_without_renewal(tmp_path):
    import json
    from test_weather_pv_calibration_source import source
    from historical_pv_daily import select_candidate
    load,path,now=source(tmp_path);before=path.read_bytes();candidate=json.loads(before)
    result=select_candidate(candidate,rows(),training_model=candidate['final_model'],selected_path=path,
        now=now+timedelta(days=15),system_raw=b'{}',horizon_raw=b'{}')
    assert result['status']=='candidate_unavailable_incumbent_preserved'
    assert result['reason']=='model_unavailable_or_expired'
    assert path.read_bytes()==before


def test_daily_geometry_reads_readonly_repository_sources_without_weakening_private_reads(tmp_path):
    import pytest
    from historical_pv_daily import geometry_declarations
    from weather_source_files import _read
    directory=tmp_path/'openhab';directory.mkdir()
    system=directory/'household-pv-system.json';horizon=directory/'household-solar-horizon.json'
    system.write_bytes(b'{"array":{}}');horizon.write_bytes(b'{"profile":[]}')
    system.chmod(0o400);horizon.chmod(0o400)
    assert geometry_declarations(tmp_path)==(system.read_bytes(),horizon.read_bytes())
    with pytest.raises(ValueError,match='owned bounded'):_read(system,16384)
    system.unlink();system.symlink_to(horizon)
    with pytest.raises(ValueError,match='owned bounded'):geometry_declarations(tmp_path)
