"""Bounded source/cohort-specific marginal kernels. No legacy dispatch changes.

Native statistics remain literal inputs. Local medians and zero atoms are model
outputs, not invented native members or joint/time-coherent ensemble forecasts.
Fitted values are immutable; scoring consumes predictions and never refits.
"""
from collections import Counter,defaultdict
from dataclasses import dataclass,field,fields,asdict
from datetime import datetime,timedelta,timezone
from hashlib import sha256
from math import exp,expm1,fsum,log,log1p,sqrt,pi,erf
from pathlib import Path
from importlib.metadata import version
import sys
from statistics import NormalDist
import json
from zoneinfo import ZoneInfo
from .contracts import canonical,digest,finite,identity,instant
from .evidence import utc

LEVELS=(.1,.25,.5,.75,.9)
KINDS=('temperature','solar_proxy','wind')
NORMAL=NormalDist()


def _arguments(value):return {f.name:getattr(value,f.name) for f in fields(value) if f.init}


def _lead(origin,end):
    hours=(instant(end)-instant(origin)).total_seconds()/3600
    for low,high in ((0,24),(24,72),(72,168),(168,336)):
        if low<hours<=high:return [low,high]
    raise ValueError('declared future lead scope required')


@dataclass(frozen=True)
class ForecastInput:
    kind:str
    origin:str
    initialized_at:str
    target_start:str
    target_end:str
    baseline:float
    incumbent:float|None
    incumbent_sha256:str|None
    p10:float|None
    p50:float|None
    p90:float|None
    source_ready_at:str
    actual_source_available_at:str
    availability_basis:str
    forecast_sha256:str
    grid_sha256:str
    cohort_sha256:str
    timezone:str
    input_sha256:str=field(init=False)

    def __post_init__(self):
        if self.kind not in KINDS:raise ValueError('declared marginal target kind required')
        origin,initialized,start,end,ready,actual=map(instant,(self.origin,self.initialized_at,self.target_start,self.target_end,self.source_ready_at,self.actual_source_available_at))
        if (not initialized<=ready<=origin<end<=initialized+timedelta(hours=360)
                or not initialized<=actual or origin-initialized>timedelta(hours=24)
                or (start!=end if self.kind=='temperature' else not origin<=start==end-timedelta(hours=1))):
            raise ValueError('original forecast point/window and readiness required')
        if self.availability_basis not in ('recorded_ingestion_availability','historical_assumed_availability'):
            raise ValueError('declared original source availability basis required')
        if self.availability_basis=='recorded_ingestion_availability' and (actual>origin or ready!=actual):
            raise ValueError('actual forecast availability cannot be backdated')
        for value in (self.forecast_sha256,self.grid_sha256,self.cohort_sha256):digest(value)
        if self.incumbent is None:
            if self.incumbent_sha256 is not None:raise ValueError('missing incumbent cannot claim an original artifact')
        else:digest(self.incumbent_sha256)
        if not finite(self.baseline) or self.incumbent is not None and not finite(self.incumbent):raise ValueError('finite original point forecast required')
        if self.kind!='temperature' and self.baseline<0:raise ValueError('nonnegative original proxy/wind input required')
        if any(v is not None and not finite(v) for v in (self.p10,self.p50,self.p90)):raise ValueError('finite native quantile or explicit absence required')
        ZoneInfo(self.timezone);_lead(self.origin,self.target_end)
        object.__setattr__(self,'input_sha256',identity(_arguments(self)))

    @property
    def width(self):
        values=[v for v in (self.p10,self.p50,self.p90) if v is not None]
        if self.p10 is None or self.p90 is None or values!=sorted(values):return None
        return self.p90-self.p10


@dataclass(frozen=True)
class CalibrationPair:
    forecast:ForecastInput
    value:float
    outcome_ready_at:str
    actual_outcome_available_at:str
    receipt_sha256:str
    pair_sha256:str=field(init=False)

    def __post_init__(self):
        if not isinstance(self.forecast,ForecastInput) or not finite(self.value):raise ValueError('original forecast and finite qualified local target required')
        at=instant(self.forecast.target_end);ready,actual=map(instant,(self.outcome_ready_at,self.actual_outcome_available_at))
        if not at<=ready or not at<=actual:raise ValueError('mature original observation availability required')
        if self.forecast.availability_basis=='recorded_ingestion_availability' and ready!=actual:
            raise ValueError('recorded observation availability cannot be backdated')
        if self.forecast.kind!='temperature' and self.value<0:raise ValueError('nonnegative qualified proxy/wind target required')
        digest(self.receipt_sha256)
        object.__setattr__(self,'pair_sha256',identity(dict(forecast=asdict(self.forecast),value=self.value,
            outcome_ready_at=self.outcome_ready_at,actual_outcome_available_at=self.actual_outcome_available_at,receipt_sha256=self.receipt_sha256)))


class _Frozen:
    __slots__=('_raw',)
    def __init__(self,*a,**kw):raise TypeError('construct from validated original calibration inputs')
    def __setattr__(self,name,value):raise AttributeError('calibration artifact is immutable')
    def to_dict(self):return json.loads(self._raw)


class CalibrationModel(_Frozen):pass
class MarginalPrediction(_Frozen):pass


def _freeze(cls,value,key):
    value=dict(value);value[key]=identity(value);obj=object.__new__(cls);object.__setattr__(obj,'_raw',canonical(value));return obj


def _policy(value):
    if (not isinstance(value,dict) or value.get('schema')!='earthship-marginal-calibration-protocol/v1'
            or value.get('policy_sha256')!=identity({k:v for k,v in value.items() if k!='policy_sha256'})):
        raise ValueError('unchanged predeclared marginal policy required')
    return value


def _source():
    root=Path(__file__).parent
    return identity(dict(files={n:sha256((root/n).read_bytes()).hexdigest() for n in ('probabilistic.py','contracts.py')},
        python=sys.version,numpy=version('numpy'),scipy=version('scipy')))


def _cohort(f):return f.kind,f.cohort_sha256,f.grid_sha256,f.timezone,tuple(_lead(f.origin,f.target_end)),f.availability_basis


def _validate(rows):
    if not isinstance(rows,list) or len(rows)>10000:raise ValueError('bounded original marginal training population required')
    seen=set();truth={}
    for row in rows:
        if not isinstance(row,CalibrationPair) or row.pair_sha256 in seen:raise ValueError('unique original marginal pairs required')
        seen.add(row.pair_sha256);f=row.forecast;key=(_cohort(f),f.target_start,f.target_end)
        observation=(row.value,row.receipt_sha256,row.outcome_ready_at,row.actual_outcome_available_at)
        if key in truth and truth[key]!=observation:raise ValueError('conflicting original measured target')
        truth[key]=observation
    return rows


def _eligible(rows,cutoff,retrospective,policy):
    rows=_validate(rows);earliest=cutoff-timedelta(days=policy['temporal']['maximum_training_days']);selected=[]
    for p in rows:
        f=p.forecast;assumed=retrospective and f.availability_basis=='historical_assumed_availability'
        source=f.source_ready_at if assumed else f.actual_source_available_at
        outcome=p.outcome_ready_at if assumed else p.actual_outcome_available_at
        if earliest<=instant(f.target_end)<cutoff and instant(source)<cutoff and instant(outcome)<cutoff:
            low,high=policy['domains'][f.kind]
            if any(not low<=v<=high for v in (f.baseline,p.value,*(() if f.incumbent is None else (f.incumbent,)))):
                raise ValueError('training values outside declared marginal domain')
            selected.append(p)
    if len({_cohort(r.forecast) for r in selected})>1:raise ValueError('different marginal source/quality/grid/lead cohorts cannot pool')
    return sorted(selected,key=lambda r:(r.forecast.origin,r.forecast.target_end,r.pair_sha256))


def _support(rows):
    zone=ZoneInfo(rows[0].forecast.timezone) if rows else ZoneInfo('America/Denver')
    return dict(pairs=len(rows),targets=len({(r.forecast.target_start,r.forecast.target_end) for r in rows}),
        local_dates=len({instant(r.forecast.target_end).astimezone(zone).date() for r in rows}))


def _weights(rows):
    days=defaultdict(set);origins=defaultdict(set);versions=Counter()
    for row in rows:
        f=row.forecast;target=(f.target_start,f.target_end);day=instant(f.target_end).astimezone(ZoneInfo(f.timezone)).date()
        days[day].add(target);origins[target].add(f.origin);versions[(target,f.origin)]+=1
    return [1/len(days)/len(days[instant(r.forecast.target_end).astimezone(ZoneInfo(r.forecast.timezone)).date()])/
        len(origins[(r.forecast.target_start,r.forecast.target_end)])/versions[((r.forecast.target_start,r.forecast.target_end),r.forecast.origin)] for r in rows]


def _enough(rows,policy):
    support=_support(rows)
    return support['targets']>=policy['temporal']['minimum_training_targets'] and support['local_dates']>=policy['temporal']['minimum_training_local_dates']


def _body(rows,*,family,cutoff,completed_at,retrospective,policy,ridge,parameters):
    completed=datetime.now(timezone.utc) if completed_at is None else utc(completed_at)
    if completed<cutoff:raise ValueError('actual model completion cannot precede training cutoff')
    f=rows[0].forecast;ready=cutoff+timedelta(minutes=policy['temporal']['assumed_fit_latency_minutes']) if retrospective else completed
    return dict(schema='earthship-local-marginal-model/v1',family=family,kind=f.kind,cohort_sha256=f.cohort_sha256,grid_sha256=f.grid_sha256,
        timezone=f.timezone,lead_scope_hours=_lead(f.origin,f.target_end),availability_basis=f.availability_basis,
        cutoff=cutoff.isoformat(),actual_completed_at=completed.isoformat(),ready_at=ready.isoformat(),retrospective_only=retrospective,
        expires_at=(ready+timedelta(days=policy['temporal']['actual_model_lifetime_days'])).isoformat(),
        training_start=min(p.forecast.target_end for p in rows),training_end=max(p.forecast.target_end for p in rows),support=_support(rows),
        training_pair_sha256s=[r.pair_sha256 for r in rows],training_data_sha256=identity([r.pair_sha256 for r in rows]),
        original_forecast_sha256s=sorted({r.forecast.forecast_sha256 for r in rows}),policy_sha256=policy['policy_sha256'],
        numerical_producer_sha256=_source(),ridge=ridge,parameters=parameters,local_coverage_qualified=False,automatic_actuation=False)


def _quantile(values,weights,p):
    mass=0.
    for value,weight in sorted(zip(values,weights)):
        mass+=weight
        if mass>=p-1e-12:return value
    return max(values)


def fit_marginal(rows,*,family,cutoff,policy,ridge=.1,completed_at=None,retrospective=False,guard=lambda:None):
    policy=_policy(policy);cutoff=utc(cutoff)
    if family not in ('temperature_normal','nonnegative','empirical') or ridge not in policy['optimization']['ridge_candidates'] or type(retrospective) is not bool:
        raise ValueError('one predeclared marginal family/ridge/context required')
    selected=_eligible(rows,cutoff,retrospective,policy)
    if selected and ((family=='temperature_normal' and selected[0].forecast.kind!='temperature') or
                     (family=='nonnegative' and selected[0].forecast.kind=='temperature')):raise ValueError('declared family differs from target kind')
    if family=='temperature_normal':selected=[r for r in selected if r.forecast.width is not None]
    if not _enough(selected,policy):return None
    weights=_weights(selected);kind=selected[0].forecast.kind
    if family=='empirical':
        residuals=[r.value-r.forecast.baseline for r in selected];values=[_quantile(residuals,weights,p) for p in LEVELS]
        floor=policy['empirical']['minimum_interval_half_width'][kind]
        values[0]=min(values[0],values[2]-floor);values[-1]=max(values[-1],values[2]+floor)
        parameters=values
    else:
        import numpy as np
        from scipy.optimize import minimize
        from scipy.special import ndtr,log_ndtr
        w=np.asarray(weights);y=np.asarray([r.value for r in selected]);x=np.asarray([r.forecast.baseline for r in selected])
        if family=='temperature_normal':
            width=np.asarray([r.forecast.width for r in selected]);floor=policy['empirical']['minimum_interval_half_width']['temperature']
            def objective(theta):
                guard();delta,a,b=theta;variance=floor*floor+a+b*width*width;sigma=np.sqrt(np.minimum(variance,400.));z=(y-x-delta)/sigma
                phi=np.exp(-.5*z*z)/sqrt(2*pi);cdf=ndtr(z);score=sigma*(z*(2*cdf-1)+2*phi-1/sqrt(pi))
                penalty=ridge*((delta/6)**2+(a/25)**2+b*b)
                ds=(2*phi-1/sqrt(pi))/(2*sigma)*(variance<400.)
                grad=np.asarray([-np.sum(w*(2*cdf-1))+2*ridge*delta/36,np.sum(w*ds)+2*ridge*a/625,np.sum(w*ds*width*width)+2*ridge*b])
                return float(np.sum(w*score)+penalty),grad
            delta=max(-6.,min(6.,float(np.sum(w*(y-x)))));variance=float(np.sum(w*(y-x-delta)**2))
            initial=[delta,max(0.,min(400.,variance-floor*floor)),.1];bounds=[(-6.,6.),(0.,400.),(0.,4.)]
        else:
            positive=[r for r in selected if r.value>0];support=_support(positive)
            if support['targets']<policy['nonnegative']['minimum_positive_training_targets'] or support['local_dates']<policy['nonnegative']['minimum_positive_training_local_dates']:return None
            xx=np.log1p(x);yy=np.log1p(y);zeros=y==0
            def objective(theta):
                guard();intercept,slope,ls=theta;sigma=np.exp(ls);mu=intercept+slope*xx;a=-mu/sigma
                rawp=ndtr(a);p=np.clip(rawp,.005,.995);z=(yy-mu)/sigma
                nll=np.where(zeros,-np.log(p),.5*z*z+ls+.5*log(2*pi)+yy+log_ndtr(-a)-np.log1p(-p))
                # Interior renormalization terms cancel. Tail clipping preserves
                # a declared non-degenerate zero/positive mixture consistently.
                dm=np.where(zeros,0.,-z/sigma);dl=np.where(zeros,0.,1-z*z)
                middle=(rawp>.005)&(rawp<.995);ratio=np.exp(-.5*a*a-.5*log(2*pi)-log_ndtr(a))
                dm=np.where(zeros&middle,ratio/sigma,dm);dl=np.where(zeros&middle,a*ratio,dl)
                tail=(~zeros)&(~middle);survival_ratio=np.exp(-.5*a*a-.5*log(2*pi)-log_ndtr(-a))
                dm=np.where(tail,dm+survival_ratio/sigma,dm);dl=np.where(tail,dl+a*survival_ratio,dl)
                penalty=ridge*(intercept*intercept+(slope-1)**2)
                return float(np.sum(w*nll)+penalty),np.asarray([np.sum(w*dm)+2*ridge*intercept,np.sum(w*dm*xx)+2*ridge*(slope-1),np.sum(w*dl)])
            initial=[0.,1.,log(max(.05,min(2.5,float(np.sqrt(np.sum(w*(yy-xx)**2))))))];bounds=[(-2.,2.),(0.,3.),(log(.05),log(2.5))]
        result=minimize(objective,initial,jac=True,method='L-BFGS-B',bounds=bounds,options=dict(maxiter=policy['optimization']['maximum_iterations'],maxfun=policy['optimization']['maximum_function_evaluations'],ftol=policy['optimization']['ftol']))
        if not result.success or not np.all(np.isfinite(result.x)):return None
        parameters=result.x.tolist()
    body=_body(selected,family=family,cutoff=cutoff,completed_at=completed_at,retrospective=retrospective,policy=policy,ridge=ridge,parameters=parameters)
    return _freeze(CalibrationModel,body,'model_sha256')


def _model(model,frame,policy,retrospective):
    policy=_policy(policy)
    if not isinstance(model,CalibrationModel) or not isinstance(frame,ForecastInput):raise ValueError('original immutable model and forecast-only input required')
    body=model.to_dict()
    if body['model_sha256']!=identity({k:v for k,v in body.items() if k!='model_sha256'}) or body['policy_sha256']!=policy['policy_sha256']:
        raise ValueError('unchanged original marginal model/policy required')
    if body['numerical_producer_sha256']!=_source():raise ValueError('original numerical producer differs from current marginal runtime')
    expected=(body['kind'],body['cohort_sha256'],body['grid_sha256'],body['timezone'],tuple(body['lead_scope_hours']),body['availability_basis'])
    if _cohort(frame)!=expected:raise ValueError('original marginal model cohort differs')
    origin=instant(frame.origin)
    if body['retrospective_only'] and not retrospective:return None
    if not instant(body['ready_at'])<=origin<instant(body['expires_at']):return None
    if not retrospective and instant(body['actual_completed_at'])>origin:return None
    return body


def _positive_parameters(mu,sigma):
    from scipy.special import ndtr,log_ndtr
    p=max(.005,min(.995,float(ndtr(-mu/sigma))))
    # Stable conditional expectation for exp(Z)-1 given Z>0.
    logmean=mu+.5*sigma*sigma+float(log_ndtr((mu+sigma*sigma)/sigma))-float(log_ndtr(mu/sigma))
    mean=(1-p)*max(0.,expm1(min(logmean,700.)))
    return p,mean


def predict_marginal(model,frame,*,policy,retrospective=False):
    if type(retrospective) is not bool:raise ValueError('explicit boolean retrospective context required')
    if model is None:return None
    body=_model(model,frame,policy,retrospective)
    if body is None:return None
    family=body['family'];parameters=body['parameters'];kind=frame.kind
    if family=='temperature_normal':
        if frame.width is None:return None
        delta,a,b=parameters;mu=frame.baseline+delta;floor=policy['empirical']['minimum_interval_half_width']['temperature']
        sigma=sqrt(min(400.,floor*floor+a+b*frame.width*frame.width));quantiles=[mu+sigma*NORMAL.inv_cdf(p) for p in LEVELS]
        distribution='normal';params=dict(mu=mu,sigma=sigma);mean=mu
    elif family=='empirical':
        quantiles=[frame.baseline+v for v in parameters]
        if kind!='temperature':quantiles=[max(0.,q) for q in quantiles]
        distribution='empirical_residual_quantiles';params={};mean=quantiles[2]
    elif family=='nonnegative':
        from scipy.special import log_ndtr,ndtri_exp
        a,b,ls=parameters;mu=a+b*log1p(frame.baseline);sigma=exp(ls);pzero,mean=_positive_parameters(mu,sigma);quantiles=[]
        for p in LEVELS:
            if p<=pzero:quantiles.append(0.);continue
            r=(p-pzero)/(1-pzero);z=-float(ndtri_exp(float(log_ndtr(mu/sigma))+log1p(-r)))
            quantiles.append(max(0.,expm1(min(700.,mu+sigma*z))))
        distribution='zero_atom_plus_positive_log1p_normal';params=dict(mu_log=mu,sigma_log=sigma,zero_probability=pzero)
    else:return None
    low,high=policy['domains'][kind]
    if any(not finite(q) or not low<=q<=high for q in (*quantiles,mean)) or quantiles!=sorted(quantiles):return None
    value=dict(schema='earthship-local-marginal-prediction/v1',kind=kind,origin=frame.origin,target_start=frame.target_start,target_end=frame.target_end,
        forecast_sha256=frame.forecast_sha256,input_sha256=frame.input_sha256,grid_sha256=frame.grid_sha256,cohort_sha256=frame.cohort_sha256,
        model_sha256=body['model_sha256'],policy_sha256=policy['policy_sha256'],model_ready_at=body['ready_at'],model_actual_completed_at=body['actual_completed_at'],
        retrospective=retrospective,distribution=distribution,parameters=params,mean=None if family=='empirical' else mean,
        point_estimate=mean,point_estimate_kind='model_median' if family=='empirical' else 'model_mean',quantile_levels=list(LEVELS),quantiles=quantiles,
        raw_native=dict(mean=frame.baseline,p10=frame.p10,p50=frame.p50,p90=frame.p90),median_source='local_model_generated',
        issued=False,local_coverage_qualified=False,probability_claim=False,automatic_actuation=False)
    return _freeze(MarginalPrediction,value,'prediction_sha256')


def prediction_cdf(value,x):
    if not isinstance(value,dict) or value.get('prediction_sha256')!=identity({k:v for k,v in value.items() if k!='prediction_sha256'}):raise ValueError('unchanged original marginal prediction required')
    p=value['parameters']
    if value['distribution']=='normal':return NORMAL.cdf((x-p['mu'])/p['sigma'])
    if value['distribution']=='zero_atom_plus_positive_log1p_normal':
        if x<0:return 0.
        if x==0:return p['zero_probability']
        from scipy.special import log_ndtr
        a=p['mu_log']/p['sigma_log'];z=(log1p(x)-p['mu_log'])/p['sigma_log']
        conditional=-expm1(min(0.,float(log_ndtr(-z))-float(log_ndtr(a))))
        return p['zero_probability']+(1-p['zero_probability'])*conditional
    raise ValueError('full empirical CDF not inferred from stored residual quantiles')


def score_marginal(prediction,value):
    if not isinstance(prediction,MarginalPrediction) or not finite(value):raise ValueError('original prediction and finite qualified outcome required')
    body=prediction.to_dict();q=body['quantiles'];low,median,high=q[0],q[2],q[4]
    def interval(lo,hi,alpha):return hi-lo+2/alpha*max(0,lo-value)+2/alpha*max(0,value-hi)
    def pinball(pred,p):return (p-(value<pred))*(value-pred)
    is80=interval(low,high,.2);is50=interval(q[1],q[3],.5);crps=None
    if body['distribution']=='normal':
        mu,sigma=body['parameters']['mu'],body['parameters']['sigma'];z=(value-mu)/sigma
        crps=sigma*(z*(2*NORMAL.cdf(z)-1)+2*exp(-.5*z*z)/sqrt(2*pi)-1/sqrt(pi))
    return dict(schema='earthship-local-marginal-score/v1',prediction_sha256=body['prediction_sha256'],model_sha256=body['model_sha256'],
        absolute_error=abs(body['point_estimate']-value),signed_error=body['point_estimate']-value,p10_pinball=pinball(low,.1),p90_pinball=pinball(high,.9),
        interval_score_80=is80,covered_80=low<=value<=high,width_80=high-low,
        wis=(.5*abs(value-median)+.1*is80+.25*is50)/2.5,crps=crps,
        local_coverage_qualified=False,automatic_actuation=False)


def fit_adaptive(rows,*,cutoff,completed_at=None,half_life_hours,policy,retrospective=False):
    if type(retrospective) is not bool:raise ValueError('explicit boolean retrospective context required')
    policy=_policy(policy);cutoff=utc(cutoff)
    if half_life_hours not in policy['adaptive']['half_life_candidates_hours']:raise ValueError('predeclared adaptive decay required')
    selected=_eligible(rows,cutoff,retrospective,policy)
    if selected and selected[0].forecast.kind!='temperature':raise ValueError('temperature adaptive residual state required')
    if not _enough(selected,policy):return None
    weights=_weights(selected);decay=[w*exp(-log(2)*(cutoff-instant(r.forecast.target_end)).total_seconds()/3600/half_life_hours) for r,w in zip(selected,weights)]
    errors=[r.value-(r.forecast.incumbent if r.forecast.incumbent is not None else r.forecast.baseline) for r in selected]
    mass=fsum(decay)
    if not mass:return None
    limit=policy['adaptive']['maximum_correction_c'];bias=max(-limit,min(limit,fsum(w*e for w,e in zip(decay,errors))/mass))
    body=_body(selected,family='adaptive',cutoff=cutoff,completed_at=completed_at,retrospective=retrospective,policy=policy,ridge=None,parameters=[bias,half_life_hours])
    return _freeze(CalibrationModel,body,'model_sha256')


def adaptive_point(model,frame,*,policy,retrospective=False):
    if type(retrospective) is not bool:raise ValueError('explicit boolean retrospective context required')
    baseline=frame.incumbent if frame.incumbent is not None else frame.baseline
    body=None if model is None else _model(model,frame,policy,retrospective)
    if body is None or body['family']!='adaptive' or instant(frame.origin)-instant(body['training_end'])>timedelta(hours=policy['adaptive']['maximum_latest_target_age_hours']):
        return dict(value=baseline,candidate_used=False,reason='cold_or_expired_state',fallback='incumbent' if frame.incumbent is not None else 'raw')
    lead=(instant(frame.target_end)-instant(frame.origin)).total_seconds()/3600
    correction=body['parameters'][0]*exp(-lead/policy['adaptive']['future_lead_decay_hours'])
    return dict(value=baseline+correction,candidate_used=True,reason=None,model_sha256=body['model_sha256'],local_coverage_qualified=False,automatic_actuation=False)
