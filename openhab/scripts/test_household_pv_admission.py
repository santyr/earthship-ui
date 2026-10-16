"""A legacy solar cohort is insufficient to admit a captured-PV comparison."""
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import json,os
import pytest
from household.codec import canonical,loads,identity
from household.control_contracts import instant
from test_household_pv_outcomes import context,originals
from test_household_pv_score import setup


@pytest.mark.parametrize('ineligible',['old_power_epoch','missing_current_PV'])
def test_old_ineligible_solar_origin_cannot_block_a_later_valid_comparison(tmp_path,monkeypatch,originals,ineligible):
    import test_household_model_snapshot as snapshots
    from test_household_power_snapshot import build as compile_source
    original_source_at=snapshots.source_at
    def changed_source(at):
        value=deepcopy(original_source_at(at)['inputs']['bundle'])
        for row in value['power_sources']:
            if row['kind']!='power':continue
            payload=loads(row['raw'])
            if ineligible=='old_power_epoch':
                payload['streamEpoch']='00000000-0000-0000-0000-000000000007';row['expected_epoch']=payload['streamEpoch']
            else:payload['fields']['pv.output_power_w']=dict(status='unavailable',reason='input_unavailable',observedAt=None,validUntil=None,watts=None)
            row['raw']=canonical(payload).decode();row['expected_sha256']=sha256(row['raw'].encode()).hexdigest()
        return compile_source(value)
    prior=tmp_path/'prior';prior.mkdir(mode=0o700)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(snapshots,'source_at',changed_source)
        _,bad=context(prior,patch,originals)
    # The later original is genuinely issued one hour later from the unchanged
    # physical configuration, rather than editing sealed forecast clocks/outputs.
    import test_native_thermal_score as native
    from test_native_thermal_forecast import ISSUE
    forecast_context=native.forecast_context
    monkeypatch.setattr(native,'forecast_context',lambda *a,**kw:forecast_context(*a,**kw,issue=ISSUE+timedelta(hours=1)))
    current=tmp_path/'current';current.mkdir(mode=0o700)
    args,stage,root,old_index=setup(current,monkeypatch,originals)
    from household_energy_forecast import seal_energy_forecast
    old=bad['energy_receipt'];old_inputs=old['inputs'];original_good=args['energy_receipt']
    good=seal_energy_forecast(plan_receipt=args['plan_receipt'],now=instant(original_good['inputs']['assessed_at']),runtime_manifest=args['energy_runtime_manifest'],
        **{name:old_inputs[name] for name in ('system_source','horizon_source','topology_source')})
    args['energy_receipt']=good
    from household_solar_outcomes import cohort_for
    solar_cohort=identity(cohort_for(old,bad['plan_receipt']))
    assert solar_cohort==identity(cohort_for(good,args['plan_receipt']))
    assert old['output']['nominal_storage']['status']=='conditional_nominal_simulation'
    evidence=stage/'evidence';(evidence/(identity(original_good)+'.household-energy-forecast-v1.json')).unlink()
    historical=prior/'stage';historical.joinpath('evidence').mkdir(parents=True,mode=0o700)
    def retain(directory,value,suffix):
        path=directory/(identity(value)+suffix);path.write_bytes(canonical(value));path.chmod(0o600)
        stamp=instant(value['output']['array_pv']['origin']).timestamp() if 'array_pv' in value['output'] else instant(value['inputs']['snapshot']['as_of']).timestamp()
        os.utime(path,(stamp,stamp));return path
    good_path=retain(evidence,good,'.household-energy-forecast-v1.json')
    bad_path=retain(historical/'evidence',old,'.household-energy-forecast-v1.json')
    retain(historical/'evidence',bad['plan_receipt'],'.household-model-plan-v6.json')
    refs={}
    for energy,path in ((old,bad_path),(good,good_path)):
        issue=instant(energy['output']['array_pv']['origin']);hour=issue.replace(minute=0,second=0,microsecond=0).isoformat()
        refs[hour]=dict(forecast_path=str(path),forecast_sha256=identity(energy),forecast_receipt_sha256=energy['receipt_sha256'],issued_at=issue.isoformat(),cohort_id=solar_cohort,score_path=None,retry_after=None)
    old_index.write_bytes(canonical(dict(schema='earthship-household-solar-storage-samples/v1',samples=refs)));before=old_index.read_bytes()
    def reader(**kw):
        assert kw['start']==instant(good['output']['array_pv']['origin'])
        return args['hour_sources']['1']
    import household_pv_score as scorer
    result=scorer.run(stage=stage,historical=[{'stage':str(historical)}],guard=lambda:None,deadline=100.,clock=lambda:args['assessed_at'],monotonic=lambda:0.,state_root=root,hour_reader=reader)
    assert result['count']==1 and old_index.read_bytes()==before
    admitted=loads((root/'captured-pv-outcomes/samples.json').read_bytes())['samples']
    assert set(admitted)=={instant(good['output']['array_pv']['origin']).replace(minute=0,second=0,microsecond=0).isoformat()}
