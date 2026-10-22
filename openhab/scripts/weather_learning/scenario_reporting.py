"""Original-bound conditional scenario reports; explicit retention, no live readers."""
from dataclasses import dataclass
from datetime import datetime,timedelta,timezone
from hashlib import sha256
from pathlib import Path
import base64,gzip,io,json
from .contracts import canonical,identity,instant
from .scenarios import _policy,stress_cases,joint_scenarios,ResidualBlock,propagate
from .source_bundle import capture_sources
from .probabilistic_artifacts import numerical_environment
from .scenario_household import MAX_TARGET_BYTES

ROOT=Path(__file__).resolve().parents[3]
MAX_BYTES=16*1024**2
# Outcome collections retain up to 25 hourly originals.
MAX_ASSESSMENT_BYTES=MAX_TARGET_BYTES+MAX_BYTES
CACHE='scenario-advisory.json'
FIELDS={'schema','inputs','runtime','output','report_sha256'}
INPUTS={'forcing','policy','blocks','cohort_sha256','household_inputs','prepared_at','owned_sources'}
HOUSEHOLD={'positions','array','horizon_profile','initial_soc_pct','nominal_bank_kwh','load_ac_w','thermal_context'}


def _sources():
    import earthship_energy.power_evidence as companion
    sources=capture_sources(ROOT);directory=Path(companion.__file__).parent
    for name in ('power_evidence','power_intervals','bms_evidence','ac_evidence'):
        sources['companion/earthship_energy/'+name+'.py']=(directory/(name+'.py')).read_bytes()
    return sources


def _runtime():
    sources=_sources();manifest={n:sha256(raw).hexdigest() for n,raw in sources.items()}
    return dict(source_manifest=manifest,source_package={n:base64.b64encode(gzip.compress(raw,mtime=0)).decode() for n,raw in sources.items()},source_package_sha256=identity(manifest),environment=numerical_environment())


def _check_runtime(runtime):
    if (not isinstance(runtime,dict) or set(runtime)!={'source_manifest','source_package','source_package_sha256','environment'} or
            runtime['source_package_sha256']!=identity(runtime['source_manifest']) or set(runtime['source_manifest'])!=set(runtime['source_package']) or
            runtime['source_manifest']!={n:sha256(raw).hexdigest() for n,raw in _sources().items()} or runtime['environment']!=numerical_environment()):raise ValueError('original scenario producer runtime required; use retained original package for replay')
    total=0
    for name,encoded in runtime['source_package'].items():
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(base64.b64decode(encoded,validate=True))) as stream:raw=stream.read(1024**2+1)
        except (ValueError,OSError,EOFError) as error:raise ValueError('literal retained scenario source required') from error
        total+=len(raw)
        if len(raw)>1024**2 or total>16*1024**2 or sha256(raw).hexdigest()!=runtime['source_manifest'][name]:raise ValueError('bounded exact original scenario source package required')


def _build(inputs,runtime,guard):
    if not isinstance(inputs,dict) or set(inputs)!=INPUTS or not isinstance(inputs['household_inputs'],dict) or set(inputs['household_inputs'])!=HOUSEHOLD:raise ValueError('closed original scenario inputs required')
    if inputs['owned_sources'] is not None:
        original=inputs['owned_sources']
        if not isinstance(original,dict) or set(original) not in ({'energy','plan'},{'energy','plan','retained_producer'}):raise ValueError('closed owned energy/plan originals required')
        from .scenario_worker import prepare_owned_inputs
        expected=prepare_owned_inputs(**original,guard=guard)
        if canonical(expected)!=canonical({k:inputs[k] for k in ('forcing','household_inputs')}):raise ValueError('scenario forcing/household inputs differ from original owned sources')
    policy=_policy(inputs['policy']);forcing=inputs['forcing'];origin=instant(forcing['origin']);prepared=instant(inputs['prepared_at'])
    if prepared<max(origin,instant(forcing['captured_at'])):raise ValueError('scenario prepared before source/origin availability')
    guard();stress=stress_cases(forcing=forcing,policy=policy)
    blocks=[ResidualBlock(canonical(b)) for b in inputs['blocks']]
    joint=joint_scenarios(forcing=forcing,blocks=blocks,cohort_sha256=inputs['cohort_sha256'],policy=policy,guard=guard)
    household=dict(inputs['household_inputs'])
    if isinstance(household['thermal_context'],dict):
        from .native_scenarios import SCHEMA as NATIVE_SCHEMA,restore_native_context
        if household['thermal_context'].get('schema')==NATIVE_SCHEMA:household['thermal_context']=restore_native_context(household['thermal_context'],guard=guard)
    stress_projections=[propagate(s,**household,guard=guard) for s in stress]
    joint_projections=[propagate(s,**household,guard=guard) for s in joint['scenarios']]
    joint={k:v for k,v in joint.items() if k!='scenarios'};joint['projections']=joint_projections
    output=dict(stress=stress_projections,joint=joint,uncertainty_scope=policy['uncertainty_scope'],probability_claim=False,automatic_actuation=False)
    result=dict(schema='earthship-original-weather-scenario-report/v1',inputs=inputs,runtime=runtime,output=output)
    result['report_sha256']=identity(result)
    if len(canonical(result))>MAX_BYTES:raise ValueError('bounded full original scenario report exceeded')
    return result


@dataclass(frozen=True)
class ScenarioReport:
    content:bytes
    def __post_init__(self):
        if not isinstance(self.content,bytes) or len(self.content)>MAX_BYTES:raise ValueError('bounded original scenario report required')
        value=json.loads(self.content)
        if (not isinstance(value,dict) or set(value)!=FIELDS or value.get('schema')!='earthship-original-weather-scenario-report/v1' or value['report_sha256']!=identity({k:v for k,v in value.items() if k!='report_sha256'})):raise ValueError('original scenario report identity required')
    def to_dict(self):return json.loads(self.content)


def prepare_report(*,forcing,policy,blocks,cohort_sha256,household_inputs,prepared_at,owned_sources=None,guard=lambda:None):
    if not isinstance(blocks,list) or len(blocks)>10000 or any(type(b) is not ResidualBlock for b in blocks):raise ValueError('bounded original residual templates required')
    inputs=dict(forcing=forcing,policy=policy,blocks=[b.to_dict() for b in blocks],cohort_sha256=cohort_sha256,household_inputs=household_inputs,prepared_at=prepared_at.isoformat(),owned_sources=owned_sources)
    runtime=_runtime();guard();record=_build(inputs,runtime,guard);_check_runtime(runtime);guard()
    return ScenarioReport(canonical(record))


def replay_report(raw,*,guard=lambda:None):
    record=ScenarioReport(raw);value=record.to_dict();_check_runtime(value['runtime']);guard()
    expected=_build(value['inputs'],value['runtime'],guard)
    if canonical(expected)!=canonical(value):raise ValueError('scenario report differs from frozen original inputs')
    _check_runtime(value['runtime']);guard();return record


def public_view(report,*,guard=lambda:None):
    if type(report) is not ScenarioReport:raise ValueError('original scenario report required')
    value=replay_report(report.content,guard=guard).to_dict();inputs=value['inputs'];forcing=inputs['forcing'];origin=instant(forcing['origin']);end=origin+timedelta(hours=forcing['horizon_hours'])
    expiry=min(origin+timedelta(hours=2),end,instant(forcing['issued_at'])+timedelta(hours=24))
    def row(projection):
        thermal=projection['thermal'];storage=projection['nominal_storage']
        return dict(name=projection['recipe']['name'],scenario_sha256=projection['scenario_sha256'],potential_pv_kwh=projection['pv']['potential_pv_kwh'],modeled_captured_pv_kwh=storage['modeled_captured_pv_kwh'],minimum_nominal_soc_pct=projection['minimum_nominal_soc_pct'],indoor_air_f=thermal['indoor_air_f'],north_wall_f=thermal['north_wall_f'],thermal_status=thermal['status'],thermal_reason=thermal['reason'],thermal_method=thermal.get('model_rule',thermal.get('features',{}).get('method')),thermal_input_scope=thermal.get('radiation_input_scope'),thermal_trajectory=[dict(at=p['at'],air_f=p['air_f'],north_wall_f=p['mass_f']) for p in thermal.get('trajectory',[])],pv_method=projection['pv']['model_rule'],solar_source_support=projection['pv']['source_support'],pv_benchmark=projection['pv']['benchmark'],storage_method=storage['model_rule'],trajectory=[dict(at=p['at'],nominal_soc_pct=p['nominal_soc_pct'],cumulative_potential_pv_kwh=p['cumulative_potential_pv_kwh']) for p in storage['trajectory']])
    joint=value['output']['joint'];public_joint={k:joint.get(k) for k in ('status','reason','method','seed','support','construction_refusals')};public_joint['scenario_count']=len(joint['projections'])
    public_joint['ranges']={name:None if not joint['projections'] else dict(min=min(p[name] for p in joint['projections']),max=max(p[name] for p in joint['projections'])) for name in ('minimum_nominal_soc_pct',)}
    view=dict(schema='earthship-weather-scenario-advisory/v1',generated_at=inputs['prepared_at'],origin=forcing['origin'],through=end.isoformat(),valid_until=expiry.isoformat(),source_forecast_sha256=forcing['forecast_sha256'],source_initialized_at=forcing['issued_at'],original_report_sha256=value['report_sha256'],policy_sha256=inputs['policy']['policy_sha256'],status='unqualified_conditional_sensitivity',product='constructed_weather_cases_not_native_members_or_current_serving_selection',stress=[row(p) for p in value['output']['stress']],joint=public_joint,uncertainty_scope=value['output']['uncertainty_scope'],issued_forecast_skill=False,physical_calibration_qualified=False,local_coverage_qualified=False,probability_claim=False,automatic_actuation=False)
    view['report_sha256']=identity(view)
    if len(canonical(view))>256*1024:raise ValueError('bounded public scenario view exceeded')
    return view


def retain_report(root,report,*,clock=lambda:datetime.now(timezone.utc),guard=lambda:None):
    from .shadow import ShadowStore,_directory
    from .worker import collector_lock
    report=replay_report(report.content,guard=guard);value=report.to_dict();view=public_view(report,guard=guard);state=ShadowStore(Path(root));directory=state.root/'scenario-reports';_directory(directory)
    with collector_lock(state.root/'scenario-publish.lock'):
        state._write(directory/(value['report_sha256']+'.json'),value,immutable=True);guard()
        now=clock();fresh=(value['inputs']['forcing']['schema']=='earthship-weathernext-native-forecast/v2' and instant(view['generated_at'])<=now<instant(view['valid_until']))
        if fresh:
            state._write(state.root/CACHE,view)
            if (state.root/CACHE).read_bytes()!=canonical(view):raise ValueError('scenario cache exact readback differs')
            if not now<=clock()<instant(view['valid_until']):raise ValueError('scenario cache publication clock regressed or expired')
    return dict(retained=True,cached=fresh,report_sha256=value['report_sha256'],probability_claim=False,automatic_actuation=False)


def assess_report(report,*,household_targets=None,weather_observations=None,assessed_at,guard=lambda:None):
    from .scenario_household import HouseholdTargets,score_household
    from .scenarios import make_residual_block
    from .scenario_scores import assess_joint
    report=replay_report(report.content,guard=guard);value=report.to_dict();inputs=value['inputs'];assessed=instant(assessed_at.isoformat())
    if assessed<instant(inputs['prepared_at']):raise ValueError('scenario assessment precedes original preparation')
    household=dict(status='unavailable',reason='matching_original_household_targets_not_supplied')
    target=None
    if household_targets is not None:
        if type(household_targets) is not HouseholdTargets:raise ValueError('typed original household target required')
        target=HouseholdTargets(household_targets.content).to_dict()
        if instant(target['request']['assessed_at'])>assessed:raise ValueError('household outcome original not available by assessment')
        household=score_household(value['output']['stress']+value['output']['joint']['projections'],targets=household_targets)
    weather=dict(status='unavailable',reason='matching_physical_weather_outcomes_or_eligible_joint_templates_required')
    if weather_observations is not None:
        labels=make_residual_block(forcing=inputs['forcing'],observations=weather_observations,cohort_sha256=inputs['cohort_sha256']).to_dict()
        if instant(labels['available_at'])>assessed:raise ValueError('weather outcome original not available by assessment')
        blocks=[ResidualBlock(canonical(b)) for b in inputs['blocks']]
        joint=joint_scenarios(forcing=inputs['forcing'],blocks=blocks,cohort_sha256=inputs['cohort_sha256'],policy=inputs['policy'],guard=guard)
        if joint['scenarios']:weather=assess_joint(joint['scenarios'],observations=weather_observations,assessed_at=assessed,training_blocks=blocks,guard=guard)
    result=dict(schema='earthship-original-scenario-assessment/v1',original_report_sha256=value['report_sha256'],runtime_sha256=value['runtime']['source_package_sha256'],inputs=dict(household_targets=target,weather_observations=weather_observations,assessed_at=assessed.isoformat()),household=household,weather=weather,as_issued_score=False,physical_calibration_qualified=False,local_coverage_qualified=False,probability_claim=False,automatic_actuation=False)
    result['assessment_sha256']=identity(result)
    if len(canonical(result))>MAX_ASSESSMENT_BYTES:raise ValueError('bounded original scenario assessment exceeded')
    _check_runtime(value['runtime']);guard();return result


def replay_assessment(raw,*,report,guard=lambda:None):
    if not isinstance(raw,bytes) or len(raw)>MAX_ASSESSMENT_BYTES:raise ValueError('bounded original scenario assessment required')
    from .scenario_household import HouseholdTargets
    value=json.loads(raw)
    fields={'schema','original_report_sha256','runtime_sha256','inputs','household','weather','as_issued_score','physical_calibration_qualified','local_coverage_qualified','probability_claim','automatic_actuation','assessment_sha256'}
    if (not isinstance(value,dict) or set(value)!=fields or value['schema']!='earthship-original-scenario-assessment/v1' or value['assessment_sha256']!=identity({k:v for k,v in value.items() if k!='assessment_sha256'}) or set(value['inputs'])!={'household_targets','weather_observations','assessed_at'}):raise ValueError('original closed scenario assessment identity required')
    original=value['inputs']['household_targets'];target=None if original is None else HouseholdTargets(canonical(original))
    expected=assess_report(report,household_targets=target,weather_observations=value['inputs']['weather_observations'],assessed_at=instant(value['inputs']['assessed_at']),guard=guard)
    if canonical(expected)!=canonical(value):raise ValueError('scenario assessment differs from original predictions and observations')
    return value
