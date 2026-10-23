"""Explicit operator preferences only; no invented comfort bands or load ratings."""
from zoneinfo import ZoneInfo
from .contracts import closed,number,name
from ..codec import canonical,loads
from ..control_contracts import instant

FIELDS={'schema','version','timezone','valid_until','comfort_min_f','comfort_max_f','validity_seconds','review_seconds','minimum_temperature_delta_f','manual_hold_seconds','shades','ventilation','energy'}
EXCLUDED={'greywater','feeder','shureflo','goat-cam','SouthOutlet','EastOutlet','SET_NIGHT_LOAD_OVERRIDE','SouthOutlet_Outlet2_Switch','EastOutlet_Outlet2_Switch','EastOutlet_Outlet1_Switch','SouthOutlet_Outlet1_Switch','ShurefloPump_Power','Feeder_ManualRequest','GoatCam_Power'}


def validate_policy(value):
    closed(value,FIELDS)
    if value['schema']!='earthship-household-advice-policy/v1':raise ValueError('versioned policy required')
    name(value['version']);ZoneInfo(value['timezone']);instant(value['valid_until'])
    number(value['comfort_min_f'],-20,100);number(value['comfort_max_f'],40,120)
    if value['comfort_min_f']>=value['comfort_max_f']:raise ValueError('ordered comfort bounds required')
    number(value['validity_seconds'],15,1800);number(value['review_seconds'],1,value['validity_seconds']);number(value['minimum_temperature_delta_f'],0.1,20);number(value['manual_hold_seconds'],0,86400)
    p=value['shades']
    if p is not None:
        closed(p,{'target','shade_ids','privacy_required'});name(p['target'])
        if not isinstance(p['shade_ids'],list) or not 1<=len(p['shade_ids'])<=26 or len(set(p['shade_ids']))!=len(p['shade_ids']):raise ValueError('explicit shade members required')
        for shade in p['shade_ids']:name(shade)
        if type(p['privacy_required']) is not bool:raise ValueError('explicit privacy policy required')
    p=value['ventilation']
    if p is not None:
        closed(p,{'target','window_minutes','allowed','required_checks'});name(p['target']);number(p['window_minutes'],1,60)
        if type(p['allowed']) is not bool or not isinstance(p['required_checks'],list) or not set(p['required_checks'])<= {'rain','wind','security','smoke','occupancy'}:raise ValueError('explicit ventilation constraints required')
        # These conditions can never silently disappear from a policy.
        if not {'rain','wind','security','smoke'}<=set(p['required_checks']):raise ValueError('required user environmental checks missing')
    p=value['energy']
    if p is not None:
        closed(p,{'reserve_soc_pct','minimum_benefit_soc_pct','loads'});number(p['reserve_soc_pct'],10,100);number(p['minimum_benefit_soc_pct'],0.01,100)
        if not isinstance(p['loads'],list) or len(p['loads'])>8:raise ValueError('bounded approved flexible loads required')
        ids=set()
        for load in p['loads']:
            closed(load,{'id','devices','approved_discretionary','essential','power_w','duration_minutes','baseline_start','deadline','interruptible','profile_basis'})
            name(load['id']);name(load['profile_basis'])
            if load['id'] in ids:raise ValueError('duplicate flexible task refused')
            ids.add(load['id'])
            if type(load['approved_discretionary']) is not bool or type(load['essential']) is not bool or type(load['interruptible']) is not bool:raise ValueError('explicit load classification required')
            if not isinstance(load['devices'],list) or not 1<=len(load['devices'])<=8:raise ValueError('explicit affected-device set required')
            for device in load['devices']:name(device)
            for field in ('power_w','duration_minutes'):
                if load[field] is not None:number(load[field],1,20000 if field=='power_w' else 1440)
            instant(load['baseline_start']);instant(load['deadline'])
    return loads(canonical(value))
