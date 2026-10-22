"""Constructed conditional weather trajectories; never native members or risk odds."""
from copy import deepcopy
from dataclasses import dataclass
from datetime import timedelta
import json
from .contracts import canonical,identity,instant,finite

POLICY_SHA256='4d1f3bfb5e8b82d460e8d2848fa78c01aed7cad06d4b21f02670fb70320990f5'
SCHEMA='earthship-constructed-weather-scenario/v1'
FIELDS={'schema','source','origin','horizon_hours','issued_at','captured_at','site','rows','rows_sha256','snapshot_sha256','recipe','policy','original_forecast','release_authorized','automatic_actuation','probability_claim','forecast_sha256','block_original'}


def _policy(value):
    if (not isinstance(value,dict) or value.get('policy_sha256')!=POLICY_SHA256 or
            identity({k:v for k,v in value.items() if k!='policy_sha256'})!=POLICY_SHA256):
        raise ValueError('frozen scenario protocol required')
    return value


def _compile(original,recipe,policy,block=None):
    from .solar_experiment import validate_component_input
    policy=_policy(policy)
    if not isinstance(original,dict) or original.get('schema')==SCHEMA:raise ValueError('unchanged original native or retrospective forecast required')
    source,evidence=validate_component_input(original)
    if source['horizon_hours'] not in policy['horizons_hours']:raise ValueError('declared scenario horizon required')
    joint=block is not None
    if joint:
        block=ResidualBlock(canonical(block)).to_dict()
        if recipe!={'name':'residual_block','residual_block_sha256':block['block_sha256']}:raise ValueError('original whole-block recipe required')
        if _block_reason(source,block,block['cohort_sha256'],policy) is not None:raise ValueError('compatible issue-available residual block required')
    elif recipe not in policy['stress_cases']:raise ValueError('frozen stress recipe required')
    rows=deepcopy(source['rows']);recipe_pin=identity(dict(recipe=recipe,policy=policy['policy_sha256'],original=source['forecast_sha256']))
    for i,row in enumerate(rows):
        if joint:
            residual=block['residuals'][i];solar=row['solar'];direct,total=solar['direct_j_m2'],solar['total_j_m2']
            if direct is None or not 0<=direct<=total:raise ValueError('supported native direct fraction required for joint construction')
            fraction=0. if total==0 else direct/total
            row['tempF']+=residual['temperature_c']*1.8
            row['windMph']=max(0.,row['windMph']*.44704+residual['wind_m_s'])/.44704
            row['radiationWm2']=max(0.,row['radiationWm2']+residual['ghi_wm2'])
            solar['total_j_m2']=row['radiationWm2']*3600;solar['direct_j_m2']=solar['total_j_m2']*fraction
        else:
            row['tempF']+=recipe['temperature_delta_c']*1.8
            row['radiationWm2']*=recipe['solar_multiplier']
            row['solar']['total_j_m2']*=recipe['solar_multiplier']
            if row['solar']['direct_j_m2'] is not None:row['solar']['direct_j_m2']*=recipe['solar_multiplier']
        row['solar']['source_digest']=recipe_pin
        if not -40<=row['tempF']<=140 or not 0<=row['radiationWm2']<=1600:raise ValueError('constructed weather outside original physical domain')
    value=dict(schema=SCHEMA,source='constructed_from_weathernext3_not_native_members',origin=source['origin'],horizon_hours=source['horizon_hours'],issued_at=source['issued_at'],captured_at=source['captured_at'],site=source['site'],rows=rows,rows_sha256=identity(rows),snapshot_sha256=source['snapshot_sha256'],recipe=deepcopy(recipe),policy=deepcopy(policy),original_forecast=deepcopy(source),release_authorized=False,automatic_actuation=False,probability_claim=False,block_original=deepcopy(block))
    value['forecast_sha256']=identity(value);return value


@dataclass(frozen=True)
class ScenarioForcing:
    content:bytes
    def __post_init__(self):
        if not isinstance(self.content,bytes) or len(self.content)>16*1024**2:raise ValueError('bounded constructed scenario required')
        value=json.loads(self.content)
        if (not isinstance(value,dict) or set(value)!=FIELDS or value['schema']!=SCHEMA or
                canonical(_compile(value['original_forecast'],value['recipe'],value['policy'],value['block_original']))!=canonical(value)):
            raise ValueError('constructed scenario differs from original recipe')
    def to_dict(self):return json.loads(self.content)
    def __getitem__(self,key):return self.to_dict()[key]


def validate_scenario(value):
    if type(value) is not ScenarioForcing:raise ValueError('typed original-bound constructed scenario required')
    return ScenarioForcing(value.content).to_dict()


def stress_cases(*,forcing,policy):
    policy=_policy(policy)
    return tuple(ScenarioForcing(canonical(_compile(forcing,recipe,policy))) for recipe in policy['stress_cases'])


def _thermal(scenario,context,*,positions,horizon_profile,guard=lambda:None):
    if context is None:return dict(status='unavailable',reason='compatible_component_response_model_not_supplied',indoor_air_f=None,north_wall_f=None)
    from .native_scenarios import NativeScenarioContext,restore_native_context,project_native_scenario,SCHEMA as NATIVE_SCHEMA
    if isinstance(context,dict) and context.get('schema')==NATIVE_SCHEMA:context=restore_native_context(context,guard=guard)
    if type(context) is NativeScenarioContext:return project_native_scenario(scenario,context,positions=positions,guard=guard)
    from .thermal_solar_experiment import component_features,predict_response,METHODS
    v=scenario.to_dict();fields={'schema','model','policy','origin_state','available_at'}
    if (not isinstance(context,dict) or set(context)!=fields or context['schema']!='earthship-component-thermal-scenario-context/v1' or
            instant(context['available_at'])>instant(v['origin']) or instant(context['model']['fitted_at'])>instant(context['available_at']) or
            context['model']['method']!=METHODS[False]):raise ValueError('issue-available separate component response model required')
    feature=component_features(forcing=scenario,positions=positions,origin_state=context['origin_state'],origin=instant(v['origin']),horizon_hours=v['horizon_hours'],horizon_profile=horizon_profile,policy=context['policy'])
    prediction=predict_response(context['model'],features=feature['features'],origin_air_f=context['origin_state']['air_f'],policy=context['policy'])
    return dict(status='unqualified_component_response' if prediction is not None else 'unavailable',reason=None if prediction is not None else 'response_outside_model_domain',indoor_air_f=prediction,north_wall_f=None,north_wall_reason='component_response_has_no_wall_target',model_sha256=context['model']['model_sha256'],features=feature,uses_legacy_proxy_coefficients=False)


def propagate(scenario,*,positions,array,horizon_profile,initial_soc_pct,nominal_bank_kwh,load_ac_w,thermal_context,guard=lambda:None):
    from household_pv_components import project_window_components
    from household_pv_model import simulate_storage
    v=validate_scenario(scenario);origin=instant(v['origin']);guard()
    pv=project_window_components(array=array,forecast=scenario,positions=positions,start=origin,end=origin+timedelta(hours=v['horizon_hours']),timezone_name=v['site']['timezone'],horizon_profile=horizon_profile)
    guard();storage=simulate_storage(steps=pv['steps'],initial_soc_pct=initial_soc_pct,nominal_bank_kwh=nominal_bank_kwh,load_ac_w=load_ac_w)
    thermal=_thermal(scenario,thermal_context,positions=positions,horizon_profile=horizon_profile,guard=guard);guard()
    from .native_scenarios import NativeScenarioContext
    original_context=thermal_context.to_dict() if type(thermal_context) is NativeScenarioContext else thermal_context
    output=dict(schema='earthship-conditional-weather-scenario-projection/v1',scenario_sha256=v['forecast_sha256'],recipe=v['recipe'],pv=pv,nominal_storage=storage,minimum_nominal_soc_pct=min(initial_soc_pct,*(r['nominal_soc_pct'] for r in storage['trajectory'])),thermal=thermal,uncertainty_scope=v['policy']['uncertainty_scope'],inputs_sha256=identity(dict(positions=positions,array=array,horizon_profile=horizon_profile,initial_soc_pct=initial_soc_pct,nominal_bank_kwh=nominal_bank_kwh,load_ac_w=load_ac_w,thermal_context=original_context)),reserve_breach_probability=None,overheating_probability=None,probability_claim=False,physical_calibration_qualified=False,automatic_actuation=False)
    output['projection_sha256']=identity(output);return output


BLOCK_FIELDS={'schema','original_forecast','observations','cohort_sha256','grid_sha256','residuals','available_at','origin','through','physical_calibration_qualified','block_sha256'}
OBSERVATION_FIELDS={'at','temperature_c','wind_m_s','ghi_wm2','solar_quantity','available_at','measurement_cohort_sha256','original_sha256'}


def _grid(forcing):
    return identity(dict(site=forcing['site'],solar_grid=forcing['rows'][0]['solar']['grid_sha256'],solar_contract=forcing['solar_input_contract']))


def _block(forcing,observations,cohort):
    from .solar_experiment import validate_component_input
    from .contracts import digest
    digest(cohort)
    if not isinstance(forcing,dict):raise ValueError('original native block forecast required')
    forcing,evidence=validate_component_input(forcing)
    if (forcing['horizon_hours']>24 or not isinstance(observations,list) or len(observations)!=len(forcing['rows']) or len(observations)>26):raise ValueError('complete bounded matched residual block required')
    residuals=[];availability=[instant(forcing['captured_at'])]
    for row,observation in zip(forcing['rows'],observations):
        if (not isinstance(observation,dict) or set(observation)!=OBSERVATION_FIELDS or
                observation['at']!=row['at'] or observation['measurement_cohort_sha256']!=cohort or
                observation['solar_quantity']!='physical_global_horizontal_irradiance'):
            raise ValueError('complete matching physical GHI/temperature/wind observation originals required')
        digest(observation['original_sha256']);at,available=map(instant,(observation['at'],observation['available_at']))
        if available<at:raise ValueError('actual residual observation availability required')
        for name,low,high in [('temperature_c',-40,60),('wind_m_s',0,100),('ghi_wm2',0,2000)]:
            if not finite(observation[name]) or not low<=observation[name]<=high:raise ValueError('finite physical residual observation required')
        availability.append(available)
        residuals.append(dict(temperature_c=observation['temperature_c']-(row['tempF']-32)/1.8,wind_m_s=observation['wind_m_s']-row['windMph']*.44704,ghi_wm2=observation['ghi_wm2']-row['radiationWm2']))
    value=dict(schema='earthship-original-weather-residual-block/v1',original_forecast=deepcopy(forcing),observations=deepcopy(observations),cohort_sha256=cohort,grid_sha256=_grid(forcing),residuals=residuals,available_at=max(availability).isoformat(),origin=forcing['origin'],through=(instant(forcing['origin'])+timedelta(hours=forcing['horizon_hours'])).isoformat(),physical_calibration_qualified=False)
    value['block_sha256']=identity(value);return value


@dataclass(frozen=True)
class ResidualBlock:
    content:bytes
    def __post_init__(self):
        if not isinstance(self.content,bytes) or len(self.content)>16*1024**2:raise ValueError('bounded residual block original required')
        value=json.loads(self.content)
        if (not isinstance(value,dict) or set(value)!=BLOCK_FIELDS or
                canonical(_block(value['original_forecast'],value['observations'],value['cohort_sha256']))!=canonical(value)):
            raise ValueError('residual block differs from original observations')
    def to_dict(self):return json.loads(self.content)


def make_residual_block(*,forcing,observations,cohort_sha256):
    return ResidualBlock(canonical(_block(forcing,observations,cohort_sha256)))


def _block_reason(forcing,block,cohort,policy):
    from zoneinfo import ZoneInfo
    origin=instant(forcing['origin']);zone=ZoneInfo(forcing['site']['timezone']);old=block['original_forecast']
    if block['cohort_sha256']!=cohort:return 'observation_cohort_mismatch'
    if block['grid_sha256']!=_grid(forcing):return 'forecast_grid_mismatch'
    if instant(block['available_at'])>origin or instant(block['through'])>origin:return 'template_not_available_at_decision'
    if instant(block['origin'])<origin-timedelta(days=policy['training_window_days']):return 'template_outside_training_window'
    if old['horizon_hours']!=forcing['horizon_hours'] or len(old['rows'])!=len(forcing['rows']):return 'template_horizon_mismatch'
    def phase(row):
        at=instant(row['at']).astimezone(zone);return at.hour,at.minute,at.fold
    if [phase(r) for r in old['rows']]!=[phase(r) for r in forcing['rows']]:return 'template_local_phase_mismatch'
    return None


def template_population(*,forcing,blocks,cohort_sha256,policy,guard=lambda:None):
    from collections import Counter
    from .solar_experiment import validate_component_input
    from .contracts import digest
    policy=_policy(policy);digest(cohort_sha256);forcing,evidence=validate_component_input(forcing)
    if (not isinstance(blocks,list) or len(blocks)>10000 or any(type(b) is not ResidualBlock for b in blocks) or
            sum(len(b.content) for b in blocks)>policy['maximum_original_bytes']):raise ValueError('bounded original residual block population required')
    eligible={};withheld=Counter();rows=0
    for original in blocks:
        guard();block=ResidualBlock(original.content).to_dict();rows+=len(block['residuals'])
        if rows>policy['maximum_template_rows']:raise ValueError('residual population row budget exceeded')
        reason=_block_reason(forcing,block,cohort_sha256,policy)
        if reason:withheld[reason]+=1
        else:eligible[block['block_sha256']]=block
    return eligible,dict(withheld)


def joint_scenarios(*,forcing,blocks,cohort_sha256,policy,guard=lambda:None):
    from random import Random
    from collections import Counter
    from zoneinfo import ZoneInfo
    policy=_policy(policy)
    eligible,withheld=template_population(forcing=forcing,blocks=blocks,cohort_sha256=cohort_sha256,policy=policy,guard=guard)
    zone=ZoneInfo(forcing['site']['timezone']);dates={instant(b['through']).astimezone(zone).date() for b in eligible.values()}
    support=dict(blocks=len(eligible),local_dates=len(dates),template_rows=sum(len(b['residuals']) for b in eligible.values()),withheld=withheld)
    result=dict(status='insufficient_evidence',reason='fewer_than_frozen_template_dates',method=policy['joint_method'],seed=policy['seed'],support=support,scenarios=[],probability_claim=False,automatic_actuation=False)
    if len(dates)<policy['minimum_template_dates']:return result
    # One original trajectory per local target date; repeated issues do not buy extra sampling mass.
    by_date={}
    for pin in sorted(eligible):
        date=instant(eligible[pin]['through']).astimezone(zone).date();by_date.setdefault(date,pin)
    pins=Random(policy['seed']).sample(sorted(by_date.values()),min(policy['maximum_scenarios'],len(by_date)))
    rejected=Counter();scenarios=[]
    for pin in pins:
        guard();recipe=dict(name='residual_block',residual_block_sha256=pin)
        try:scenarios.append(ScenarioForcing(canonical(_compile(forcing,recipe,policy,eligible[pin]))))
        except ValueError:rejected['constructed_trajectory_outside_supported_domain']+=1
    result.update(status='unqualified_joint_scenarios' if scenarios else 'insufficient_evidence',reason=None if scenarios else 'all_constructed_trajectories_refused',scenarios=scenarios,construction_refusals=dict(rejected),template_sha256s=pins)
    return result
