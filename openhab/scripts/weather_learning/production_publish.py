"""Google-only publication mechanics; no transport, schedule or release grant.

The cutover worker must supply its qualified release/ownership decision, hold
its shared writer lock, and inject bounded state-only REST functions. Missing
admission refuses before writes. This module cannot select a provider, fit a
model, import old learning, invoke a rule or command equipment.
"""
from datetime import datetime,timedelta,timezone
import json,math
from zoneinfo import ZoneInfo
from .contracts import canonical,identity
from .provider import publication_states

DETAIL='Forecast_10Day_JSON'
NUMERIC_ITEMS=('Forecast_Temp','Forecast_Cloudiness','Forecast_Radiation','Forecast_Daily_High',
    'Forecast_Daily_Low','Forecast_Daily_PrecipSum','Forecast_Tomorrow_High','Forecast_Tomorrow_Low')


def production_states(provider,*,now):
    states=publication_states(provider,now=now);value=provider.to_dict()
    states.update({item:'UNDEF' for item in NUMERIC_ITEMS})
    if value['status']!='AVAILABLE':return states
    def number(item,value,unit=''):
        if value is not None:states[item]=str(value)+((' '+unit) if unit else '')
    first=value['hours'][0]
    number('Forecast_Temp',first['temp_f'],'°F');number('Forecast_Cloudiness',first['cloud_pct'],'%')
    number('Forecast_Radiation',first['radiation_wm2'],'W/m²')
    today=now.astimezone(ZoneInfo(value['timezone'])).date();days={row['date']:row for row in value['days']}
    day=days.get(today.isoformat());tomorrow=days.get((today+timedelta(days=1)).isoformat())
    if day is not None:
        number('Forecast_Daily_High',day['high_f'],'°F');number('Forecast_Daily_Low',day['low_f'],'°F')
        number('Forecast_Daily_PrecipSum',None if day['precip_sum_in'] is None else day['precip_sum_in']*25.4,'mm')
    if tomorrow is not None:
        number('Forecast_Tomorrow_High',tomorrow['high_f']);number('Forecast_Tomorrow_Low',tomorrow['low_f'])
    return states


def _withdrawal(states,reason):
    result={item:('UNDEF' if item in NUMERIC_ITEMS else '[]') for item in states}
    detail=json.loads(states[DETAIL]);detail.update(providerStatus='UNAVAILABLE',providerReason=reason,source=None,issueSha256=None,days=[])
    result[DETAIL]=canonical(detail).decode()
    return result


def _same_state(item,expected,actual):
    if item not in NUMERIC_ITEMS or expected=='UNDEF':return actual==expected
    if not isinstance(actual,str):return False
    def parts(raw):
        fields=raw.strip().split(maxsplit=1)
        return float(fields[0]),fields[1] if len(fields)==2 else ''
    try:
        want,unit=parts(expected);got,observed=parts(actual)
        if not math.isfinite(want) or not math.isfinite(got):return False
        if unit=='°F' and observed in ('°C','K'):got=(got-(273.15 if observed=='K' else 0))*9/5+32;observed='°F'
        if unit=='W/m²' and observed=='W/m^2':observed=unit
        if unit=='mm' and observed in ('in','in_i'):got*=25.4;observed='mm'
        if unit=='%' and observed in ('one','1'):got*=100;observed='%'
        return unit==observed and math.isclose(want,got,rel_tol=1e-9,abs_tol=1e-9)
    except (ValueError,IndexError,OverflowError):return False


def publish_cycle(provider,*,now,put_state,read_state,authorize=None):
    """Commit detail last; every failure attempts all owned withdrawals.

    Authorization is an injected deployment decision, not a passing scientific
    assessment produced here. Unit/integration simulations use local stores.
    No live caller, permissive default or production activation is installed.
    """
    states=production_states(provider,now=now)
    if not callable(authorize) or authorize(provider) is not True:raise ValueError('qualified cutover writer authorization required')
    if not callable(put_state) or not callable(read_state):raise ValueError('bounded state writer and readback required')
    value=provider.to_dict();result=dict(schema='earthship-weathernext-publication-result/v1',status='FAILED',
        provider_snapshot_sha256=value['provider_snapshot_sha256'],states_sha256=identity(states),verified_items=[],
        failed_item=None,withdrawal_attempts=[],unconfirmed_withdrawals=[],release_authorized=False,automatic_actuation=False)
    active=DETAIL
    def write(item,raw):
        if put_state(item,raw) is False:raise ValueError('state write refused')
        if not _same_state(item,raw,read_state(item)):raise ValueError('state readback differs')
    try:
        pending=_withdrawal(states,'PUBLICATION_PENDING')
        write(DETAIL,pending[DETAIL])
        for item,raw in states.items():
            if item==DETAIL:continue
            active=item;write(item,raw);result['verified_items'].append(item)
        active=DETAIL;write(DETAIL,states[DETAIL]);result['verified_items'].append(DETAIL)
        result['status']='PUBLISHED' if value['status']=='AVAILABLE' else 'WITHDRAWN'
    except Exception:
        result['failed_item']=active
        withdrawal=_withdrawal(states,'PUBLICATION_FAILED')
        for item in (DETAIL,*(key for key in states if key!=DETAIL)):
            result['withdrawal_attempts'].append(item)
            try:write(item,withdrawal[item])
            except Exception:result['unconfirmed_withdrawals'].append(item)
    result['completed_at']=datetime.now(timezone.utc).isoformat()
    return result|{'result_sha256':identity(result)}
