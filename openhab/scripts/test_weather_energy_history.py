from datetime import timedelta
import json
import pytest
from test_household_pv_window import START,END,raw,POLICY
from weather_learning.contracts import identity


def source(soc=70):
    def bms(at):
        t=int(at.timestamp()*1000)
        return json.dumps(dict(version=1,streamEpoch='00000000-0000-4000-8000-000000000001',recordedAt=t,status='valid',reason='ok',observedAt=t,scaleObservedAt=t,validUntil=t+120000,soc=soc))
    rows={kind:[] for kind in ('power','soc','ac')}
    for i,s in enumerate(range(0,3600,60)):
        at=START+timedelta(seconds=s)
        rows['power'].append([at.isoformat(),raw(at,i+1,1000)])
        rows['soc'].append([at.isoformat(),bms(at)])
    result=dict(schema='earthship-historical-energy-hour/v1',start=START.isoformat(),end=END.isoformat(),requested_at=(END+timedelta(minutes=5)).isoformat(),received_at=(END+timedelta(minutes=5,seconds=1)).isoformat(),
        policy_raw=POLICY,bank_start=(START-timedelta(days=1)).isoformat(),rows=rows,items=dict(power=612,soc=613,ac=614),automatic_actuation=False)
    result['source_sha256']=identity(result);return result


def test_input_potential_calibration_requires_qualified_low_soc_charging():
    from weather_learning.energy_history import summarize_hour
    bins=summarize_hour(source())
    assert len(bins)==12
    assert bins[0]['potential_proxy_eligible'] is True
    assert bins[0]['fields']['pv.input_power_w']['positive_kwh']==pytest.approx(1/12)
    assert bins[0]['fields']['inverter.ac_output_w']['covered_seconds']==0
    high=summarize_hour(source(99))
    assert not any(b['potential_proxy_eligible'] for b in high)
    missing=source();missing['rows']['soc']=[];missing.pop('source_sha256');missing['source_sha256']=identity(missing)
    assert not any(b['potential_proxy_eligible'] for b in summarize_hour(missing))


def test_energy_history_keeps_invalid_barriers_and_rejects_changed_originals():
    from weather_learning.energy_history import summarize_hour
    original=source();original['rows']['power'][1][1]='invalid'
    with pytest.raises(ValueError,match='identity'):summarize_hour(original)
    original.pop('source_sha256');original['source_sha256']=identity(original)
    bins=summarize_hour(original)
    assert bins[0]['fields']['pv.input_power_w']['covered_seconds']<300
    assert bins[0]['potential_proxy_eligible'] is False
