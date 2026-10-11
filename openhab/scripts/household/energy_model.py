"""Pure legacy daily energy arithmetic; source qualification is caller-owned.

This preserves the production estimation policy, including its configured
capacity, overnight-drop fallback and rounded curtailment proxy. Numerical
output does not qualify a physical bank epoch, action effect or forecast.
"""


def daily_energy_projection(*,resource_kwh,direct_demand_kwh,soc_pct,bank_kwh,
                            eta_rt,overnight_drops_pct,tomorrow_cloud_pct):
    def clamp(value,low,high):return max(low,min(high,value))
    deficit_kwh=(100-soc_pct)/100*bank_kwh/eta_rt if soc_pct is not None else None
    demand=direct_demand_kwh+deficit_kwh if deficit_kwh is not None else None
    pv_pred=round(min(resource_kwh,demand),2) if demand is not None else None
    curtail=(round(clamp((resource_kwh-demand)/1.0,0,8)*2)/2
             if resource_kwh>demand else 0.0) if demand is not None else None
    drop_base_pct=(sum(overnight_drops_pct)/len(overnight_drops_pct)) if overnight_drops_pct else 12.0
    dusk_soc=(99 if resource_kwh>=demand-0.3 else
              clamp(soc_pct+(pv_pred-direct_demand_kwh)/bank_kwh*100*eta_rt,12,99)) if demand is not None else None
    cloud_drop_penalty_pct=2 if tomorrow_cloud_pct is not None and tomorrow_cloud_pct>70 else 0
    drop_pct=drop_base_pct+cloud_drop_penalty_pct
    trough_pred=round(clamp(dusk_soc-drop_pct,12,99)) if dusk_soc is not None else None
    return dict(deficit_kwh=deficit_kwh,demand=demand,pv_pred=pv_pred,curtail=curtail,
                drop_base_pct=drop_base_pct,dusk_soc=dusk_soc,cloud_drop_penalty_pct=cloud_drop_penalty_pct,
                drop_pct=drop_pct,trough_pred=trough_pred)


from dataclasses import dataclass
import math
from .codec import canonical,loads,identity

ENERGY_FIELDS={'resource_kwh','direct_demand_kwh','soc_pct','bank_kwh','eta_rt','overnight_drops_pct','tomorrow_cloud_pct'}


def _numeric_inputs(value):
    if not isinstance(value,dict) or set(value)!=ENERGY_FIELDS:raise ValueError('closed daily energy inputs required')
    for name,low,high,nullable in (
        ('resource_kwh',0,10000,False),('direct_demand_kwh',0,10000,False),
        ('soc_pct',0,100,True),('bank_kwh',0,10000,False),
        ('eta_rt',0,1,False),('tomorrow_cloud_pct',0,100,True)):
        number=value[name]
        if nullable and number is None:continue
        if type(number) not in (int,float) or not math.isfinite(number) or not low<=number<=high:
            raise ValueError('finite bounded daily energy input required')
        if name in ('bank_kwh','eta_rt') and number==0:raise ValueError('positive capacity and efficiency required')
    drops=value['overnight_drops_pct']
    if not isinstance(drops,list) or len(drops)>3 or any(type(number) not in (int,float) or not math.isfinite(number) or not 0<=number<=100 for number in drops):
        raise ValueError('bounded original overnight drop list required')


@dataclass(frozen=True)
class FrozenEnergyInputs:
    content:bytes

    def __post_init__(self):
        if not isinstance(self.content,bytes) or len(self.content)>4096:raise ValueError('bounded frozen energy inputs required')
        value=loads(self.content)
        if not isinstance(value,dict) or set(value)!={'schema','inputs'} or value['schema']!='earthship-household-energy-inputs/v1':
            raise ValueError('closed frozen energy input record required')
        _numeric_inputs(value['inputs'])

    def to_dict(self):return loads(self.content)


def freeze_energy_inputs(**inputs):
    return FrozenEnergyInputs(canonical(dict(schema='earthship-household-energy-inputs/v1',inputs=inputs)))


def project_energy(inputs):
    if not isinstance(inputs,FrozenEnergyInputs):raise ValueError('frozen daily energy inputs required')
    value=inputs.to_dict()
    result=dict(schema='earthship-household-energy-projection/v1',inputs_sha256=identity(value),
        output=daily_energy_projection(**value['inputs']),input_qualification='not_assessed',
        soc_basis='existing_qualified_soc_inputs_caller_contract',action_effects_qualified=False,automatic_actuation=False)
    result['projection_sha256']=identity(result)
    return result
