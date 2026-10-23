"""Both daily and household PV use one exact component artifact and owner."""
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
import json
import pytest
from test_production_pv import fit,CONTEXT,SYSTEM,TERRAIN,MEASUREMENT,forecast,ORIGIN,geometry
from weather_learning.contracts import canonical,identity
AUTH=json.loads(Path('docs/operations/weathernext3-capabilities/deployment-policy.json').read_bytes())

def api():
 from weather_learning import production_pv_runtime
 return production_pv_runtime

def write(path,value,mode=0o600):
 path.write_bytes(value if isinstance(value,bytes) else canonical(value));path.chmod(mode);return path

@pytest.fixture
def owner_files(tmp_path):
 policy=canonical(dict(synthetic_test_meter_policy=True));context=dict(CONTEXT,power_policy_sha256=sha256(policy).hexdigest())
 model,_=fit(context=context,authorization=AUTH,authorization_sha256=identity(AUTH));root=tmp_path.resolve()
 calibration=write(root/'model.json',model.to_dict());system=write(root/'system.json',SYSTEM,0o644);horizon=write(root/'horizon.json',TERRAIN,0o644);power=write(root/'power.json',policy,0o644)
 profile=dict(schema='earthship-component-pv-production-profile/v1',model_path=str(calibration),model_file_sha256=sha256(calibration.read_bytes()).hexdigest(),calibration_sha256=model.to_dict()['calibration_sha256'],
  measurement_cohort_sha256=MEASUREMENT,system_path=str(system),horizon_path=str(horizon),power_policy_path=str(power),runtime_sha256=identity(api().runtime_manifest()),authorization_policy_sha256=identity(AUTH),
  parallel_shadow_required=False,automatic_actuation=False)
 path=write(root/'profile.json',profile)
 owner=api().ComponentOwner(path,expected_sha256=sha256(path.read_bytes()).hexdigest(),clock=lambda:ORIGIN)
 return owner,path,profile,model

def test_actual_owner_compiles_the_same_native_point_kernel_and_daily_total(owner_files):
 owner,_,_,_=owner_files;f=forecast(hours=12);positions=geometry(count=144)
 point=owner.project(forecast=f,positions=positions,start=ORIGIN,end=ORIGIN+timedelta(hours=1))
 assert point['mode']=='selected_native_gain'
 days,originals=owner.project_days(dates=['2026-06-21'],forecast=f,positions=positions)
 assert days[0]['status']=='available' and days[0]['potentialKwh']==pytest.approx(days[0]['uncalibratedPotentialKwh']*.8)
 assert days[0]['calibrationScope']=='native_components_only' and len(originals)==1
 assert originals[0]['projection']['potential_pv_kwh']==days[0]['potentialKwh']

def test_profile_model_or_physical_configuration_changes_refuse_before_projection(owner_files):
 owner,path,profile,_=owner_files
 path.write_bytes(path.read_bytes()+b'\n')
 with pytest.raises(ValueError):owner.project(forecast=forecast(),positions=geometry(count=36),start=ORIGIN,end=ORIGIN+timedelta(hours=1))
 write(path,profile);calibration=Path(profile['model_path']);calibration.write_bytes(calibration.read_bytes()+b'\n')
 with pytest.raises(ValueError):owner.verify()

def test_expiry_before_publication_refuses_stale_compilation_without_clock_renewal(owner_files):
 owner,_,_,model=owner_files
 from weather_learning.production_pv import load_calibration
 # Model readiness/expiry is evaluated at the actual source origin. A later
 # wall clock cannot renew the old model or grant an old point a new issue.
 owner.clock=lambda:__import__('weather_learning.contracts',fromlist=['instant']).instant(model.to_dict()['expires_at'])
 with pytest.raises(ValueError):owner.project(forecast=forecast(),positions=geometry(count=36),start=ORIGIN,end=ORIGIN+timedelta(hours=1))

def test_missing_native_direct_never_gets_the_native_electrical_coefficients(owner_files):
 owner,_,_,_=owner_files
 value=owner.project(forecast=forecast(direct=None),positions=geometry(count=36),start=ORIGIN,end=ORIGIN+timedelta(hours=1))
 assert value['projection']['calibration_scope']=='raw_total_only_fallback'
 assert value['projection']['potential_pv_kwh']==value['raw_projection']['potential_pv_kwh']


def test_new_source_after_original_model_expiry_uses_explicit_raw_fallback(owner_files,monkeypatch):
 import native_solar_fixtures as fixtures
 from weather_learning.native_forecast import make_native_component_forecast
 owner,_,_,_=owner_files;init=fixtures.T+timedelta(days=15);origin=init+timedelta(hours=1,minutes=15)
 monkeypatch.setattr(fixtures,'T',init)
 f=make_native_component_forecast(fixtures.snapshot(hours=30),origin=origin,available_by=init+timedelta(hours=1),horizon_hours=1,site=fixtures.SITE)
 owner.clock=lambda:origin
 value=owner.project(forecast=f,positions=fixtures.geometry(start=init,count=36),start=origin,end=origin+timedelta(hours=1))
 assert value['mode']=='native_components_raw_fallback' and value['reason']=='registered_model_expired'
 assert value['projection']['potential_pv_kwh']==value['raw_projection']['potential_pv_kwh']

def test_daily_view_exposes_new_method_training_support_without_borrowed_skill_claims(owner_files):
 owner,_,_,model=owner_files;f=forecast(hours=12)
 days,_=owner.project_days(dates=['2026-06-21'],forecast=f,positions=geometry(count=144))
 view=owner.daily_view(days=days,forecast=f,geometry_sha256='f'*64)
 assert view['schema']=='earthship-daily-pv-potential/v4'
 assert view['calibration']['calibrationSha256']==model.to_dict()['calibration_sha256']
 assert view['calibration']['localTargetDates']==4 and view['calibration']['targets']==32
 assert 'baselineMaeW' not in view['calibration'] and 'candidateMaeW' not in view['calibration']
 assert view['calibration']['mode']=='experimental_production'
 assert view['physical_calibration_qualified'] is False
 assert str(owner.path).encode() not in canonical(view)


def test_old_and_new_daily_calibration_modes_cannot_be_combined(tmp_path):
 from daily_pv_worker import run
 with pytest.raises(ValueError,match='one'):
  run(archive_path=tmp_path/'unused-archive',state_path=tmp_path/'state',output_path=tmp_path/'view.json',libraries_path=tmp_path/'libraries',
   calibration_path=tmp_path/'old-model',component_profile_path=tmp_path/'new-model',component_profile_sha256='f'*64)
 assert not (tmp_path/'view.json').exists()
