"""Scheduled captured-PV work must retain originals and leave earlier scores alone."""
import importlib,os
from pathlib import Path
from household.codec import canonical,loads,identity
from household.control_contracts import instant
from test_household_pv_outcomes import context,originals


def test_scoring_module_is_available_for_the_existing_optional_slot():
    api=importlib.import_module('household_pv_score')
    assert callable(api.run)


def setup(tmp_path,monkeypatch,originals):
    _,args=context(tmp_path,monkeypatch,originals);stage=tmp_path/'stage';evidence=stage/'evidence';evidence.mkdir(parents=True,mode=0o700)
    for value,suffix in ((args['energy_receipt'],'.household-energy-forecast-v1.json'),(args['plan_receipt'],'.household-model-plan-v6.json')):
        path=evidence/(identity(value)+suffix);path.write_bytes(canonical(value));path.chmod(0o600);stamp=instant(args['energy_receipt']['output']['array_pv']['origin']).timestamp();os.utime(path,(stamp,stamp))
    root=tmp_path/'state';root.mkdir(mode=0o700);solar=root/'energy-outcomes';solar.mkdir(mode=0o700)
    energy=args['energy_receipt'];issued=energy['output']['array_pv']['origin'];hour=issued[:13]+':00:00+00:00'
    from household_solar_outcomes import cohort_for
    source=dict(schema='earthship-household-solar-storage-samples/v1',samples={hour:dict(forecast_path=str(evidence/(identity(energy)+'.household-energy-forecast-v1.json')),forecast_sha256=identity(energy),forecast_receipt_sha256=energy['receipt_sha256'],issued_at=issued,cohort_id=identity(cohort_for(energy,args['plan_receipt'])),score_path=None,retry_after=None)})
    path=solar/'samples.json';path.write_bytes(canonical(source));path.chmod(0o600)
    return args,stage,root,path


def test_normal_opportunity_retains_full_source_and_replayable_score_without_changing_existing_state(tmp_path,monkeypatch,originals):
    args,stage,root,old=setup(tmp_path,monkeypatch,originals);before=old.read_bytes();api=importlib.import_module('household_pv_score')
    result=api.run(stage=stage,historical=[],guard=lambda:None,deadline=100.,clock=lambda:args['assessed_at'],monotonic=lambda:0.,state_root=root,
        hour_reader=lambda **kw:args['hour_sources']['1'])
    assert result['status']=='captured_pv_performance_refreshed' and result['count']==1
    report=loads((root/'captured-pv-performance.json').read_bytes());assert report['by_horizon']['1']['models']['constant_load_pv']['count']==1
    assert old.read_bytes()==before and report['automatic_actuation'] is False
    scores=list((root/'captured-pv-outcomes').glob('*.captured-pv-outcome-v1.json.gz'));assert len(scores)==1
    import gzip
    value=loads(gzip.decompress(scores[0].read_bytes()));assert value['inputs']['hour_sources']['1']['rows']==args['hour_sources']['1']['rows']
    original_files={p:p.read_bytes() for p in stage.joinpath('evidence').iterdir()}
    result=api.run(stage=stage,historical=[],guard=lambda:None,deadline=100.,clock=lambda:args['assessed_at'],monotonic=lambda:0.,state_root=root,
        hour_reader=lambda **kw:(_ for _ in ()).throw(AssertionError('resampled completed original')))
    assert result['count']==1 and all(p.read_bytes()==raw for p,raw in original_files.items())
