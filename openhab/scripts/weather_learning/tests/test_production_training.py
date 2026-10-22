"""Historical evidence may train a fresh production model without becoming as-issued history."""
from dataclasses import replace,asdict
from datetime import timedelta
import copy
import pytest
from learning_fixtures import T
from test_probabilistic import POLICY,pairs,frame
from test_production_model_admission import AUTH
from weather_learning.contracts import identity

CUTOFF=T+timedelta(days=22)
QUALITY=dict(provenance='synthetic_original_measurement',sensorEpoch='fixture-epoch',measurement_health_qualified=False)


def context(kind='temperature',basis='historical_assumed_availability'):
 return dict(kind=kind,measurement_quality=QUALITY,grid_sha256='a'*64,availability_basis=basis,lead_scope_hours=[0,24],timezone='America/Denver')


def cohort(value):return identity({k:v for k,v in value.items() if k!='timezone'})


def historical(kind='temperature'):
 ctx=context(kind);result=[]
 for p in pairs(kind):
  f=replace(p.forecast,availability_basis=ctx['availability_basis'],actual_source_available_at=(T+timedelta(days=21)).isoformat(),cohort_sha256=cohort(ctx))
  result.append(replace(p,forecast=f,actual_outcome_available_at=(T+timedelta(days=21)).isoformat()))
 return result


def fit(rows=None,kind='temperature',**kwargs):
 from weather_learning.production_training import fit_production
 args=dict(rows=historical(kind) if rows is None else rows,family='temperature_normal' if kind=='temperature' else 'nonnegative',training_context=context(kind),
  cutoff=CUTOFF,completed_at=CUTOFF+timedelta(minutes=1),policy=POLICY,population_sha256='a'*64,authorization=AUTH,authorization_sha256=identity(AUTH))
 args.update(kwargs);return fit_production(**args)


def test_actual_time_historical_fit_keeps_literal_original_availability_and_future_production_scope():
 prepared=fit();body=prepared.bundle.to_dict();training=prepared.training_dict();original=historical();snapshot=[asdict(r) for r in original]
 assert body['role']=='actual_time_production_fit'
 assert body['training_availability_basis']=='historical_assumed_availability'
 assert body['availability_basis']=='recorded_ingestion_availability'
 assert body['actual_completed_at']==body['ready_at']==(CUTOFF+timedelta(minutes=1)).isoformat()
 assert body['models']['temperature_normal']['availability_basis']=='historical_assumed_availability'
 assert body['models']['temperature_normal']['retrospective_only'] is False
 assert training['pairs']==snapshot
 assert training['pairs'][0]['forecast']['actual_source_available_at']>training['pairs'][0]['forecast']['origin']
 assert original==historical()


def test_historical_assumed_readiness_cannot_override_actual_training_input_arrival():
 assert fit(cutoff=T+timedelta(days=20),completed_at=T+timedelta(days=20,minutes=1)) is None
 values=historical();late=replace(values[0],value=60,actual_outcome_available_at=(T+timedelta(days=100)).isoformat())
 a=fit(values[1:]);b=fit([late,*values[1:]])
 assert a.bundle.to_dict()['models']==b.bundle.to_dict()['models']


def test_only_explicitly_matching_observation_grid_and_lead_context_can_transfer():
 for changed in [dict(context(),measurement_quality=dict(QUALITY,sensorEpoch='other')),dict(context(),grid_sha256='f'*64),dict(context(),lead_scope_hours=[24,72])]:
  with pytest.raises(ValueError,match='cohort|context'):fit(training_context=changed)
 mixed=historical();mixed[-1]=replace(mixed[-1],forecast=replace(mixed[-1].forecast,cohort_sha256='f'*64))
 with pytest.raises(ValueError,match='cohort|context'):fit(mixed)


def test_new_historical_model_predicts_production_with_its_own_admission_not_rewritten_shadow_flags():
 from weather_learning.production_model_admission import prepare_admission,predict_production
 p=fit();body=p.bundle.to_dict();live=context(basis='recorded_ingestion_availability');f=replace(frame(22),cohort_sha256=cohort(live))
 pin=body['models']['temperature_normal']['model_sha256'];original=p.bundle.to_dict()
 a=prepare_admission(p.bundle,family='temperature_normal',expected_model_sha256=pin,policy=POLICY,authorization=AUTH,authorization_sha256=identity(AUTH),admitted_at=CUTOFF+timedelta(minutes=2))
 value=predict_production(p.bundle,a,f,policy=POLICY,authorize=lambda r:True)
 assert value['point_estimate']==pytest.approx(12,abs=.5) and value['source_available_at']==f.actual_source_available_at
 assert value['issued'] is value['probability_claim'] is value['local_coverage_qualified'] is False
 assert p.bundle.to_dict()==original


@pytest.mark.parametrize('kind',['wind','solar_proxy'])
def test_nonnegative_fit_preserves_hourly_wind_and_lux_proxy_scope(kind):
 from weather_learning.production_model_admission import prepare_admission,predict_production
 p=fit(kind=kind);b=p.bundle.to_dict();f=replace(frame(22,kind=kind),cohort_sha256=cohort(context(kind,basis='recorded_ingestion_availability')))
 a=prepare_admission(p.bundle,family='nonnegative',expected_model_sha256=b['models']['nonnegative']['model_sha256'],policy=POLICY,authorization=AUTH,authorization_sha256=identity(AUTH),admitted_at=CUTOFF+timedelta(minutes=2))
 value=predict_production(p.bundle,a,f,policy=POLICY,authorize=lambda r:True)
 assert value['point_estimate']>=0
 assert value['target_kind']==('local_station_hour_mean_wind_m_s' if kind=='wind' else 'qualified_lux_proxy_hour_mean_w_m2')


def test_production_retention_keeps_original_training_source_and_no_active_selector(tmp_path):
 from weather_learning.production_training import retain_production,read_production
 from weather_learning.shadow import ShadowStore
 state=ShadowStore(tmp_path/'production');prepared=fit();original=prepared.bundle.to_dict()
 ref=retain_production(state,prepared,policy=POLICY)
 assert ref['bundle_sha256']==original['bundle_sha256']
 loaded=read_production(state,ref['artifact_sha256'],policy=POLICY)
 assert loaded.to_dict()==original
 path=state.root/'production-models'/(ref['artifact_sha256']+'.json');raw=path.read_bytes()
 assert path.stat().st_mode&0o777==0o600
 assert retain_production(state,prepared,policy=POLICY)==ref and path.read_bytes()==raw
 assert not (state.root/'current-model.json').exists() and not (state.root/'production-current.json').exists()


def test_a_resealed_training_object_still_cannot_move_actual_input_arrival_after_cutoff(tmp_path):
 from weather_learning.production_training import FittedProduction,ProductionBundle,retain_production
 from weather_learning import probabilistic as kernel
 from weather_learning.contracts import canonical
 from weather_learning.shadow import ShadowStore
 prepared=fit();training=prepared.training_dict();f=dict(training['pairs'][0]['forecast']);f.pop('input_sha256')
 f['actual_source_available_at']=(CUTOFF+timedelta(days=1)).isoformat()
 p=dict(training['pairs'][0]);p.pop('pair_sha256');p['forecast']=kernel.ForecastInput(**f)
 training['pairs'][0]=asdict(kernel.CalibrationPair(**p));training['training_inputs_sha256']=identity({k:v for k,v in training.items() if k!='training_inputs_sha256'})
 body=prepared.bundle.to_dict();body.pop('bundle_sha256');body['training_inputs_sha256']=training['training_inputs_sha256']
 changed=FittedProduction(kernel._freeze(ProductionBundle,body,'bundle_sha256'),canonical(training));state=ShadowStore(tmp_path/'production')
 with pytest.raises(ValueError,match='past|available|cutoff'):retain_production(state,changed,policy=POLICY)
 assert not list((state.root/'production-models').glob('*.json'))


def test_production_artifacts_count_toward_the_existing_shared_storage_cap(tmp_path):
 from weather_learning.shadow import ShadowStore,_directory
 s=ShadowStore(tmp_path/'state');_directory(s.root/'production-models')
 with (s.root/'production-models/existing.json').open('wb') as output:output.truncate(2*1024**3-1)
 with pytest.raises(ValueError,match='capacity'):s._write(s.root/'issues/new.json',{'payload':'bounded new original'})


def test_partitioned_historical_cohort_maps_only_its_original_lead_range():
 from weather_learning.production_training import load_production_bundle,production_frame
 from weather_learning.production_model_admission import prepare_admission,predict_production
 descriptor=dict(method='contiguous_whole_native_leads_greedy_capacity/v1',parent_cohort_sha256=cohort(context()),lower_exclusive_hours=0.,upper_inclusive_hours=2.)
 values=[replace(p,forecast=replace(p.forecast,cohort_sha256=identity(descriptor))) for p in historical()]
 prepared=fit(values,partition=descriptor);body=prepared.bundle.to_dict()
 loaded=load_production_bundle(body,expected_sha256=body['bundle_sha256'],policy=POLICY)
 live=replace(frame(22),cohort_sha256=cohort(context(basis='recorded_ingestion_availability')))
 assert production_frame(loaded,live) is not None
 later=replace(live,target_start=(T+timedelta(days=22,hours=12)).isoformat(),target_end=(T+timedelta(days=22,hours=12)).isoformat())
 assert production_frame(loaded,later) is None
 pin=body['models']['temperature_normal']['model_sha256']
 a=prepare_admission(loaded,family='temperature_normal',expected_model_sha256=pin,policy=POLICY,authorization=AUTH,authorization_sha256=identity(AUTH),admitted_at=CUTOFF+timedelta(minutes=2))
 assert predict_production(loaded,a,live,policy=POLICY,authorize=lambda r:True)['point_estimate']==pytest.approx(12,abs=.5)


def test_rehashed_out_of_domain_parameters_are_not_a_valid_production_fit():
 from weather_learning.production_training import load_production_bundle
 b=fit().bundle.to_dict();model=b['models']['temperature_normal'];model['parameters'][0]=100
 model['model_sha256']=identity({k:v for k,v in model.items() if k!='model_sha256'});b['bundle_sha256']=identity({k:v for k,v in b.items() if k!='bundle_sha256'})
 with pytest.raises(ValueError,match='bounded'):load_production_bundle(b,expected_sha256=b['bundle_sha256'],policy=POLICY)
