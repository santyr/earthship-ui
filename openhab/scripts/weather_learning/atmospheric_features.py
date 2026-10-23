"""Immutable forecast-only predictors for explicitly retrospective ablations.

Native instantaneous quantities are averaged in time; no observed future
weather, marginal probability, operational issue or control authority is added.
"""
from bisect import bisect_left
from dataclasses import dataclass
from datetime import timedelta
from math import fsum,hypot
from .atmospheric_context import VARIABLES,_field
from .config import Site
from .contracts import identity,instant
from .evidence import utc
from .historical import verify_history
from .pv_training_sources import forecast_origin
from .solar_experiment import BASES

GROUPS={'dewpoint':('dewpoint',),'pressure':('pressure',),'wind_direction':('u','v'),'cloud_layers':('high','medium','low')}


@dataclass(frozen=True)
class NativeInstant:
    at:object
    value:float
    snapshot_sha256:str
    grid_sha256:str
    native_asset_sha256:str
    source_digest:str


@dataclass(frozen=True)
class RetrospectiveAtmosphericFeatures:
    initialized_at:object
    ready_at:object
    actual_available_at:object
    assessed_at:object
    source_class:str
    source_sha256s:tuple
    series:tuple

    def _quantity(self,name,start,end):
        values=next((rows for key,rows in self.series if key==name),())
        if not values:return None
        times=tuple(p.at for p in values)
        def point(at):
            i=bisect_left(times,at)
            if i<len(times) and times[i]==at:return values[i].value,(values[i],)
            if not 0<i<len(times):return None
            left,right=values[i-1],values[i]
            if right.at-left.at>timedelta(hours=1) or left.grid_sha256!=right.grid_sha256:return None
            fraction=(at-left.at).total_seconds()/(right.at-left.at).total_seconds()
            return left.value+(right.value-left.value)*fraction,(left,right)
        if start==end:return point(end) if end in times else None
        knots=[start,*(at for at in times if start<at<end),end];parts=[];proof={}
        for a,b in zip(knots,knots[1:]):
            if b-a>timedelta(hours=1):return None
            left,right=point(a),point(b)
            if left is None or right is None:return None
            points=left[1]+right[1]
            if len({p.grid_sha256 for p in points})!=1:return None
            for p in points:proof[p.at]=p
            parts.append((b-a).total_seconds()*(left[0]+right[0])/2)
        return fsum(parts)/(end-start).total_seconds(),tuple(proof[k] for k in sorted(proof))

    def features(self,*,kind,origin,target):
        origin,target=map(utc,(origin,target))
        if kind not in ('temperature','wind','thermal') or not self.ready_at<=origin<target<=self.initialized_at+timedelta(hours=360):
            raise ValueError('declared forecast-only target after source readiness required')
        if origin>self.assessed_at or target>max(p.at for name,rows in self.series for p in rows):
            raise ValueError('original native forecast window unavailable')
        if kind!='wind' and target-origin>timedelta(hours=24):raise ValueError('bounded near-term atmospheric target required')
        start=target if kind=='temperature' else target-timedelta(hours=1) if kind=='wind' else origin
        if start<origin:raise ValueError('wind target must follow the prediction origin')
        values={name:self._quantity(name,start,target) for name in VARIABLES}
        def compatible(names):
            rows=[values[name] for name in names]
            return all(row is not None for row in rows) and all(
                [(p.at,p.grid_sha256,p.native_asset_sha256) for p in row[1]]==[(p.at,p.grid_sha256,p.native_asset_sha256) for p in rows[0][1]] for row in rows[1:])
        groups={};withheld={};proofs={}
        for group,names in GROUPS.items():
            required=('temperature','dewpoint') if group=='dewpoint' else names
            if not compatible(required):
                groups[group]=None;withheld[group]='missing_complete_native_quantity_support';continue
            vector=[values[name][0] for name in names]
            if group=='wind_direction':
                magnitude=hypot(*vector)
                if magnitude<=1e-6:
                    groups[group]=None;withheld[group]='calm_or_cancelling_mean_vector';continue
                vector=[v/magnitude for v in vector]
            elif group=='cloud_layers':vector=[v/100 for v in vector]
            groups[group]=vector
            proofs[group]=sorted({identity(dict(at=p.at.isoformat(),value=p.value,snapshot_sha256=p.snapshot_sha256,grid_sha256=p.grid_sha256,
                native_asset_sha256=p.native_asset_sha256,source_digest=p.source_digest)) for name in required for p in values[name][1]})
        result=dict(schema='earthship-atmospheric-experiment-features/v1',kind=kind,origin=origin.isoformat(),target_at=target.isoformat(),
            window_start=start.isoformat(),groups=groups,withheld=withheld,original_point_sha256s=proofs,
            source_class=self.source_class,source_sha256s=list(self.source_sha256s),source_ready_at=self.ready_at.isoformat(),
            actual_source_available_at=self.actual_available_at.isoformat(),assessed_at=self.assessed_at.isoformat(),
            as_issued_forecast=False,automatic_actuation=False,release_authorized=False)
        result['feature_sha256']=identity(result);return result


def prepare_atmospheric_features(*,snapshots,site,assessed_at,availability_basis,guard=lambda:None):
    assessed_at=utc(assessed_at)
    if not isinstance(site,Site) or not isinstance(snapshots,(list,tuple)) or not 1<=len(snapshots)<=8:
        raise ValueError('bounded original forecast profiles and authoritative site required')
    chosen={name:{} for name in VARIABLES};origins=set();initializations=set();historical_flags=set();available=[];pins=[]
    by_variable={spec[0]:name for name,spec in VARIABLES.items()}
    for snapshot in snapshots:
        guard();body=verify_history(snapshot);pin=identity(body)
        if snapshot.get('snapshot_sha256',pin)!=pin or body['site']!=site.__dict__:raise ValueError('original atmospheric source identity or site differs')
        historical=body['historical'];completed=instant(body['ingestion_completed_at'])
        if availability_basis!=BASES[historical] or assessed_at<completed:raise ValueError('actual source acquisition and explicit evidence class required')
        available.append(completed);pins.append(pin);historical_flags.add(historical);initializations.add(instant(body['initialized_at']))
        origins.add(forecast_origin(body,recorded=not historical));body=dict(body,snapshot_sha256=pin)
        for p in body['points']:
            if p['statistic']!='mean' or p['variable'] not in by_variable:continue
            name=by_variable[p['variable']];f=_field(body,p,name)
            if f is None:continue
            at=instant(f['valid_at']);candidate=NativeInstant(at,f['value'],pin,f['grid_sha256'],f['native_asset_sha256'],f['source_digest'])
            old=chosen[name].get(at)
            if old is None or (completed,pin)>old[0]:chosen[name][at]=((completed,pin),candidate)
    if len(initializations)!=1 or len(historical_flags)!=1:raise ValueError('one run and source class required; no later-run feature borrowing')
    ready=max(origins)
    if ready>assessed_at or not any(chosen.values()):raise ValueError('original forecast not ready at assessment')
    series=tuple((name,tuple(row[1] for at,row in sorted(values.items()))) for name,values in sorted(chosen.items()))
    return RetrospectiveAtmosphericFeatures(next(iter(initializations)),ready,max(available),assessed_at,
        'historical_assumed_availability' if next(iter(historical_flags)) else 'recorded_ingestion_availability',tuple(sorted(set(pins))),series)
