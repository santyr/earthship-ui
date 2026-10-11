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
