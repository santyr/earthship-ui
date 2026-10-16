"""Four shade regimes using native solar geometry; no release or actuation authority."""
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar
import json,math
import numpy as np
from astro_geometry_series import NativeGeometrySeries
from native_thermal_inputs import native_clear_sky_fraction
from thermal_model.installed_shade_dynamics import (InstalledShadeDynamics,InstalledShadeForcing,
    InstalledShadeRollout,STEP,MAX_ROLLOUT_STEPS,_number,_temperature,_utc)
from thermal_model.dynamics import MAX_VENT_FORCING,SOLAR_TERM_SCALE
from thermal_model.graduation_policy import _sha
from thermal_model.solar import SITE_LATITUDE,SITE_LONGITUDE

RULE='earthship-native-joint-shade-dynamics/v3'
PARAMETER_NAMES=('outside_exchange','mass_exchange','solar_unshaded','solar_indoor_closed',
    'solar_outdoor_only','solar_both_closed','vent_exchange','bias','mass_air_exchange',
    'mass_outside_exchange','mass_solar_unshaded','mass_solar_indoor_closed',
    'mass_solar_outdoor_only','mass_solar_both_closed')
LOWER=(0.,)*7+(-.2,)+(0.,)*6
UPPER=(.5,.5,.02,.01,.015,.01,.8,.2,.2,.2,.008,.004,.006,.004)
INSTALLED_INDICES=(0,1,5,4,6,7,8,9,13,12)
GAIN_PAIRS=((2,3),(2,4),(3,5),(4,5),(10,11),(10,12),(11,13),(12,13))
CONTEXT=Path(__file__).resolve().parents[1]/'thermal-shade-context.json'


def shade_contract():
    raw=CONTEXT.read_bytes()
    if len(raw)>8192:raise ValueError('bounded shade context required')
    value=json.loads(raw)
    if (not isinstance(value,dict) or set(value)!={'schema','nominal_shade_rejection_fraction','transmission_prior','interpretation',
            'outdoor_zones','expected_reinstallation','automatic_reinstallation'} or
            value['schema']!='earthship-thermal-shade-context/v1' or value['automatic_reinstallation'] is not False):
        raise ValueError('closed observational shade context required')
    rejection=_number(value['nominal_shade_rejection_fraction']);transmission=_number(value['transmission_prior'])
    if not 0<rejection<1 or not math.isclose(transmission,1-rejection,rel_tol=0,abs_tol=1e-12):
        raise ValueError('explicit complementary nominal shade prior required')
    zones=value['outdoor_zones']
    if (not isinstance(zones,list) or len(zones)!=3 or [z.get('id') if isinstance(z,dict) else None for z in zones]!=['kitchen','living_room','bedroom_bathroom'] or
            any(set(z)!={'id','name','rooms'} or not isinstance(z['name'],str) or not 1<=len(z['name'])<=64 or
                not isinstance(z['rooms'],list) or not 1<=len(z['rooms'])<=2 or
                any(not isinstance(r,str) or not 1<=len(r)<=64 for r in z['rooms']) for z in zones)):
        raise ValueError('three explicit exterior zones required; weights are not inferred')
    for key in ('interpretation','expected_reinstallation'):
        if not isinstance(value[key],str) or not 1<=len(value[key])<=240:raise ValueError('bounded context note required')
    return value


def validate_coefficients(values):
    if type(values) is not tuple or len(values)!=14:raise ValueError('four-regime fourteen-parameter vector required')
    for value,low,high in zip(values,LOWER,UPPER):
        if not low<=_number(value)<=high:raise ValueError('joint coefficient outside physical bounds')
    if any(values[high]<values[low] for high,low in GAIN_PAIRS):
        raise ValueError('adding a shade cannot increase fixed-forcing solar gain')
    # The installed projection has exactly the same heat-flow equations. This
    # retains its spectral-radius and 72-hour zero-solar stress checks verbatim.
    InstalledShadeDynamics(tuple(values[i] for i in INSTALLED_INDICES))
    return values


def expand_installed_prior(values):
    InstalledShadeDynamics(tuple(values));t=shade_contract()['transmission_prior'];p=values
    return validate_coefficients((p[0],p[1],p[3]/t,p[2]/t,p[3],p[2],p[4],p[5],
        p[6],p[7],p[9]/t,p[8]/t,p[9],p[8]))


def normalize_forcings(*,origin_at,forcings,geometry,guard=lambda:None):
    if type(geometry) is not NativeGeometrySeries:raise ValueError('original complete native geometry required')
    at=_utc(origin_at)
    if type(forcings) is not tuple or not 1<=len(forcings)<=MAX_ROLLOUT_STEPS:raise ValueError('bounded immutable forcing grid required')
    normalized=[]
    for row in forcings:
        guard()
        if not isinstance(row,InstalledShadeForcing):raise ValueError('explicit shade forcing required')
        next_at=_utc(row.at)
        if next_at!=at+STEP:raise ValueError('complete five-minute native grid required')
        outside=_temperature(row.outdoor_f);radiation,indoor,outdoor,vent=map(_number,
            (row.radiation_wm2,row.indoor_shade_closed,row.outdoor_shade_present,row.vent_open))
        if not 0<=indoor<=1 or not 0<=outdoor<=1 or not 0<=radiation<=1600 or not 0<=vent<=MAX_VENT_FORCING:
            raise ValueError('explicit shade forcing outside physical bounds')
        scale=SOLAR_TERM_SCALE*native_clear_sky_fraction(radiation,next_at,geometry=geometry)
        normalized.append((outside,scale*(1-indoor)*(1-outdoor),scale*indoor*(1-outdoor),
            scale*(1-indoor)*outdoor,scale*indoor*outdoor,vent));at=next_at
    return tuple(normalized)


@dataclass(frozen=True)
class NativeJointShadeDynamics:
    coefficients:tuple[float,...]
    geometry:NativeGeometrySeries
    expected_series_sha256:str
    rule:ClassVar[str]=RULE
    parameter_names:ClassVar[tuple[str,...]]=PARAMETER_NAMES
    release_authorized:ClassVar[bool]=False
    automatic_actuation:ClassVar[bool]=False
    def __post_init__(self):
        if type(self.geometry) is not NativeGeometrySeries or self.geometry.sha256!=_sha(self.expected_series_sha256):raise ValueError('original native geometry pin required')
        site=self.geometry.descriptor()
        if site['site']['latitude']!=SITE_LATITUDE or site['site']['longitude']!=SITE_LONGITUDE or site['timezone']!='America/Denver':raise ValueError('native thermal site differs')
        validate_coefficients(self.coefficients)
    def _transition(self,vent):
        p=self.coefficients
        return np.asarray(((1-p[0]-p[1]-vent*p[6],p[1]),(p[8],1-p[8]-p[9])))
    def rollout(self,*,origin_at,air_f,mass_f,forcings,guard=lambda:None):
        air,mass=_temperature(air_f),_temperature(mass_f);p=self.coefficients
        normalized=normalize_forcings(origin_at=origin_at,forcings=forcings,geometry=self.geometry,guard=guard)
        jac=np.zeros((2,14));states=[];sensitivities=[]
        for outside,*solar,vent in normalized:
            guard();direct=np.zeros((2,14));direct[0,:8]=(outside-air,mass-air,*solar,vent*(outside-air),1)
            direct[1,8:]=(air-mass,outside-mass,*solar);jac=self._transition(vent)@jac+direct
            air,mass=(air+p[0]*(outside-air)+p[1]*(mass-air)+sum(p[2+i]*s for i,s in enumerate(solar))+p[6]*vent*(outside-air)+p[7],
                mass+p[8]*(air-mass)+p[9]*(outside-mass)+sum(p[10+i]*s for i,s in enumerate(solar)))
            air,mass=_temperature(air),_temperature(mass)
            if not np.isfinite(jac).all():raise ValueError('nonfinite native joint sensitivity')
            states.append((air,mass));sensitivities.append(tuple(tuple(map(float,row)) for row in jac))
        return InstalledShadeRollout(tuple(states),tuple(sensitivities))


def objective(coefficients,batches,*,deadline=None):
    from thermal_model.installed_shade_fit import _check_deadline
    p=np.asarray(coefficients,dtype=float)
    if p.shape!=(14,) or not np.isfinite(p).all():raise ValueError('finite fourteen-parameter objective required')
    loss=0.;gradient=np.zeros(14);sensitivity=[]
    for origins,targets,vent,weather,*solar in batches:
        if len(solar)!=4:raise ValueError('four explicit regime features required')
        state=origins.copy();jac=np.zeros((len(state),2,14));matrix=np.zeros((len(state),2,2))
        matrix[:,0,0]=1-p[0]-p[1]-vent*p[6];matrix[:,0,1]=p[1]
        matrix[:,1,0]=p[8];matrix[:,1,1]=1-p[8]-p[9]
        for step in range(weather.shape[1]):
            if deadline is not None:_check_deadline(deadline)
            air,mass=state[:,0].copy(),state[:,1].copy();outside=weather[:,step]
            direct=np.zeros((len(state),2,14));direct[:,0,0]=outside-air;direct[:,0,1]=mass-air
            direct[:,0,6]=vent*(outside-air);direct[:,0,7]=1
            direct[:,1,8]=air-mass;direct[:,1,9]=outside-mass
            for i,feature in enumerate(solar):direct[:,0,2+i]=feature[:,step];direct[:,1,10+i]=feature[:,step]
            jac=matrix@jac+direct
            state[:,0]=air+p[0]*(outside-air)+p[1]*(mass-air)+sum(p[2+i]*s[:,step] for i,s in enumerate(solar))+p[6]*vent*(outside-air)+p[7]
            state[:,1]=mass+p[8]*(air-mass)+p[9]*(outside-mass)+sum(p[10+i]*s[:,step] for i,s in enumerate(solar))
            if not np.isfinite(state).all() or not np.isfinite(jac).all():raise ValueError('nonfinite joint solver trial')
        residual=state-targets;divisor=len(state)*len(batches)
        loss+=float(np.sum(residual**2))/divisor;gradient+=2*np.einsum('ni,nij->j',residual,jac)/divisor
        sensitivity.extend(jac.reshape(-1,14)/math.sqrt(divisor))
    if not math.isfinite(loss) or not np.isfinite(gradient).all():raise ValueError('nonfinite joint objective')
    return loss,gradient,np.asarray(sensitivity)


def constraints(lower,spans):
    from scipy.optimize import LinearConstraint
    from thermal_model.dynamics import SOLVER_FEASIBILITY_MARGIN,STABILITY_TOLERANCE
    rows=[];bounds=[]
    for high,low in GAIN_PAIRS:
        row=np.zeros(14);row[high]=1;row[low]=-1
        rows.append(row*spans);bounds.append(SOLVER_FEASIBILITY_MARGIN-float(row@lower))
    for indices,values in (((0,1,6),(-1,-1,-2)),((8,9),(-1,-1))):
        row=np.zeros(14)
        for i,v in zip(indices,values):row[i]=v
        rows.append(row*spans);bounds.append(-1+STABILITY_TOLERANCE-float(row@lower))
    return [LinearConstraint(np.asarray(rows),np.asarray(bounds),np.full(len(rows),np.inf))]


REGIMES={(0,0):'unshaded',(1,0):'indoor_only',(0,1):'outdoor_only',(1,1):'both_closed'}
def regime_support(data,points,*,start=None,end=None):
    from thermal_model.graduation_policy import _utc as instant
    start=data.development.start if start is None else instant(start)
    end=data.development.end if end is None else instant(end)
    result={key:dict(endpoint_count=0,daylight_sample_count=0,status='prior_only') for key in REGIMES.values()}
    for point in points:
        key=REGIMES.get((point.origin.indoor_shade_closed,point.origin.outdoor_shade_present))
        if key:result[key]['endpoint_count']+=1
    for sample in data.development.samples:
        if not start<=sample.at<end:continue
        key=REGIMES.get((sample.indoor_shade_closed,sample.outdoor_shade_present))
        if key and sample.radiation_wm2>100 and not data.geometry.is_thermal_night(sample.at):result[key]['daylight_sample_count']+=1
    for row in result.values():
        if row['endpoint_count'] and row['daylight_sample_count']:row['status']='observed_unqualified'
    return result


def validate_fit_metadata(fit,*,created_at,assessed_at):
    """Same provisional support/authority guards, with fourteen explicit gains."""
    from uuid import UUID
    from thermal_model.graduation_policy import _utc as instant
    if (fit['mode']!='provisional' or fit['confidence']!='low' or fit['fit_executed'] is not True or
            any(fit[k] is not False for k in ('stability_assessed','graduated','automatic_actuation','release_authorized','as_issued_forecast')) or
            fit['prediction_intervals'] is not None):raise ValueError('joint priors cannot claim qualification or control')
    for key in ('coefficients','initial_coefficients'):
        if not isinstance(fit[key],list):raise ValueError('explicit coefficient vector required')
        validate_coefficients(tuple(fit[key]))
    for key in ('initial_objective','final_objective','regularization_strength'):
        if type(fit[key]) not in (int,float) or not math.isfinite(fit[key]) or fit[key]<0:raise ValueError('finite joint fit evidence required')
    if fit['regularization_strength']!=1 or fit['final_objective']>fit['initial_objective']+1e-6:raise ValueError('invalid regularized joint improvement')
    rank=fit['conditioning_rank'];condition=fit['normalized_condition_number']
    if type(rank) is not int or not 0<=rank<=14:raise ValueError('bounded joint rank required')
    if rank<14:
        if condition is not None:raise ValueError('unidentified joint condition must be unavailable')
    elif type(condition) not in (int,float) or not math.isfinite(condition) or condition<1:raise ValueError('finite full-rank condition required')
    for key,maximum in (('iterations',300),('endpoint_count',256),('independent_origin_dates',256)):
        if type(fit[key]) is not int or not 0<=fit[key]<=maximum:raise ValueError('bounded joint support required')
    if fit['endpoint_count']<1 or not 1<=fit['independent_origin_dates']<=fit['endpoint_count']:raise ValueError('real original endpoint support required')
    counts=fit['horizon_support']
    if (not isinstance(counts,dict) or set(counts)!={'1','6','12','24'} or
            any(type(x) is not int or not 0<=x<=64 for x in counts.values()) or sum(counts.values())!=fit['endpoint_count']):raise ValueError('closed joint horizon support required')
    phases=fit['sensor_epochs']
    if not isinstance(phases,dict) or set(phases)!={'air','mass','outdoor'}:raise ValueError('complete native phases required')
    for phase in phases.values():
        parsed=UUID(phase)
        if str(parsed)!=phase or parsed.int==0:raise ValueError('canonical nonzero phases required')
    start,end,created,assessed=map(instant,(fit['training_start'],fit['training_end'],created_at,assessed_at))
    if not start<end<=created<=assessed:raise ValueError('original frozen joint chronology required')
    _sha(fit['source_snapshot_sha256'])
