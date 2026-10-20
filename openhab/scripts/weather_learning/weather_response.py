"""Bounded site-response gains, with explicit retrospective and meter scope."""
from datetime import timedelta
from math import fsum
from .contracts import finite,identity,instant,digest
from .weights import weather_weights,metrics as weighted_metrics,validate_support,TIMEZONE

SCHEMA='earthship-site-weather-gain/v2'

PAIR_FIELDS={'kind','origin','target_start','target_end','baseline','outcome','source_sha256','measurement_sha256','measurement_quality','prospective_score','automatic_actuation','pair_sha256','availability_basis'}
KINDS={'wind_m_s','rain_24h_mm'}


def wind_hour(rows,*,start):
    if len(rows)>10000 or [at for at,_ in rows]!=sorted({at for at,_ in rows}):raise ValueError('bounded ordered wind states required')
    end=start+timedelta(hours=1);pieces=[]
    for i,(at,value) in enumerate(rows):
        stop=min(end,at+timedelta(seconds=120),rows[i+1][0] if i+1<len(rows) else end);left=max(start,at)
        if stop>left and finite(value) and 0<=value<=200:pieces.append(((stop-left).total_seconds(),value/2.2369362921))
    covered=fsum(s for s,_ in pieces)
    return dict(mean_m_s=None if covered<3420 else fsum(s*v for s,v in pieces)/covered,covered_seconds=covered,measurement_health_qualified=False,unit='m_s')


def _pair(row):
    if set(row)!=PAIR_FIELDS or row['kind'] not in KINDS or row['pair_sha256']!=identity({k:v for k,v in row.items() if k!='pair_sha256'}) or row['automatic_actuation'] is not False or row['prospective_score'] is not False:raise ValueError('unchanged observational weather pair required')
    digest(row['source_sha256']);digest(row['measurement_sha256'])
    origin,start,end=map(instant,(row['origin'],row['target_start'],row['target_end']))
    period=timedelta(hours=1 if row['kind']=='wind_m_s' else 24)
    if not origin<=start<end or end-start!=period or any(not finite(row[k]) or row[k]<0 for k in ('baseline','outcome')):raise ValueError('finite source-period-matched weather targets required')
    return row


def fit_gain(rows,*,kind,cutoff,trained_at,prior_pairs=24):
    if kind not in KINDS or not cutoff<=trained_at or not finite(prior_pairs) or not 0<prior_pairs<=365 or not 1<=len(rows)<=50000:raise ValueError('bounded earlier site-response context required')
    chosen=[_pair(r) for r in rows if r['kind']==kind and instant(r['target_end'])<cutoff];chosen.sort(key=lambda r:(r['origin'],r['target_end'],r['pair_sha256']))
    if not chosen or len({r['pair_sha256'] for r in chosen})!=len(chosen):raise ValueError('unique earlier weather pairs required')
    weights,support=weather_weights(chosen)
    xx=fsum(w*r['baseline']**2 for w,r in zip(weights,chosen));xy=fsum(w*r['baseline']*r['outcome'] for w,r in zip(weights,chosen));prior=xx*prior_pairs/support['target_weight_sum']
    gain=1. if xx==0 else max(.25,min(4.,(xy+prior)/(xx+prior)))
    result=dict(schema=SCHEMA,rule='target_weighted_gain_with_unchanged_physics_prior_v2',support=support,timezone=TIMEZONE,prior_targets=prior_pairs,kind=kind,gain=gain,prior_pairs=prior_pairs,cutoff=cutoff.isoformat(),trained_at=trained_at.isoformat(),
        training_start=min(r['target_start'] for r in chosen),training_end=max(r['target_end'] for r in chosen),training_pairs=len(chosen),training_target_days=support['local_target_dates'],
        training_pair_sha256s=[r['pair_sha256'] for r in chosen],training_data_sha256=identity(chosen),qualification='provisional_site_response_not_sensor_health_or_causal_qualification',automatic_actuation=False)
    result['model_sha256']=identity(result);return result


def validate_model(value):
    if value.get('schema') not in (SCHEMA,'earthship-site-weather-gain/v1') or value.get('model_sha256')!=identity({k:v for k,v in value.items() if k!='model_sha256'}) or value.get('kind') not in KINDS or value.get('automatic_actuation') is not False or not finite(value.get('gain')) or not .25<=value['gain']<=4 or not instant(value['training_end'])<instant(value['cutoff'])<=instant(value['trained_at']):raise ValueError('original site-weather gain required')
    if value['schema']==SCHEMA:
        support=validate_support(value.get('support'))
        if (support['forecast_pairs']!=value['training_pairs'] or support['local_target_dates']!=value['training_target_days'] or support['timezone']!=TIMEZONE or
            value.get('timezone')!=TIMEZONE or value.get('prior_targets')!=value['prior_pairs'] or value.get('rule')!='target_weighted_gain_with_unchanged_physics_prior_v2'):
            raise ValueError('weather target support differs from model')
    return value


def predict_gain(model,baseline,*,origin):
    model=validate_model(model)
    if instant(model['trained_at'])>origin:raise ValueError('site-weather model not available at origin')
    if not finite(baseline) or baseline<0:raise ValueError('finite nonnegative weather baseline required')
    return baseline*model['gain']


def evaluate_gain(model,rows,*,start,end):
    model=validate_model(model)
    if not instant(model['cutoff'])<=start<end:raise ValueError('later disjoint weather holdout required')
    chosen=[_pair(r) for r in rows if r['kind']==model['kind'] and start<=instant(r['origin'])<instant(r['target_end'])<end]
    def compare(values):
        weights,support=weather_weights(values)
        return dict(pairs=len(values),support=support,independent_target_days=support['local_target_dates'],
            baseline=weighted_metrics([r['baseline']-r['outcome'] for r in values],weights),
            candidate=weighted_metrics([r['baseline']*model['gain']-r['outcome'] for r in values],weights))
    result=dict(schema='earthship-site-weather-gain-comparison/v2',timezone=TIMEZONE,kind=model['kind'],model_sha256=model['model_sha256'],start=start.isoformat(),end=end.isoformat(),**compare(chosen),
        by_observed_rain={k:compare([r for r in chosen if (r['outcome']>0)==wet]) for k,wet in [('wet',True),('dry',False)]} if model['kind']=='rain_24h_mm' else {},
        prospective_score=False,automatic_actuation=False)
    result['selected']=result['support']['unique_measured_targets']>=3 and result['independent_target_days']>=2 and result['candidate']['mae']<result['baseline']['mae'];result['report_sha256']=identity(result);return result
