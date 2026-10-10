"""Actual archive/native-receipt boundary tests; no services or fitting."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'openhab/scripts'))
from test_thermal_origin_capture import capture_inputs,EPOCH,NOW
from thermal_model.origin_capture import build_origin_capture,write_origin_capture
import thermal_graduation_evidence as evidence


def receipt(at,value):
    return dict(temperatureF=value,receivedAt=(at-timedelta(seconds=30)).isoformat(),
        storedAt=(at-timedelta(seconds=20)).isoformat(),validUntil=(at+timedelta(seconds=90)).isoformat(),
        streamEpoch=EPOCH,snapshotSha256='a'*64)


def case(tmp_path):
    tmp_path.chmod(0o700)
    record=build_origin_capture(**capture_inputs());path=write_origin_capture(tmp_path,record)
    target=NOW+timedelta(hours=1)
    publication=dict(time=int((NOW+timedelta(seconds=1)).timestamp()*1000),state=json.dumps(record['output']))
    cycles=[]
    for lag in range(1,8):
        origin=NOW-timedelta(days=lag);end=target-timedelta(days=lag)
        cycles.extend([[origin.isoformat(),receipt(origin,70)],[end.isoformat(),receipt(end,71)]])
    return dict(origin_path=path,publication=publication,horizon_hours=1,
        outcome=dict(target_at=target.isoformat(),receipt=receipt(target,74)),
        recent_cycle_grid=cycles,assessed_at=target+timedelta(minutes=10))


def test_source_scorer_uses_original_output_and_native_outcome(tmp_path):
    data=case(tmp_path);result=evidence.score_qualified_origin(**data)
    row=result['scored_pair']
    assert row['model_error_f']==1
    assert row['persistence_error_f']==0
    assert row['recent_cycle_error_f']==1
    assert row['sensor_epochs']['air']==EPOCH
    assert result['release_authorized'] is False
    assert result['original_capture_sha256']
    assert result['outcome_receipt_sha256']
    assert result['recent_cycle_evidence_sha256']
    assert result['known_actions'] is None


@pytest.mark.parametrize('damage',['publication','future_store','changed_epoch','wrong_target','outcome_epoch',
    'late_outcome','missing_cycles','duplicate_cycles','future_cycle','cycle_epoch'])
def test_unqualified_source_pair_refuses_scoring(tmp_path,damage):
    data=case(tmp_path)
    if damage=='publication':data['publication']['state']='{}'
    elif damage=='future_store':data['publication']['time']=int((data['assessed_at']+timedelta(seconds=1)).timestamp()*1000)
    elif damage=='changed_epoch':data['recent_cycle_grid'][0][1]['streamEpoch']='064142d5-99ee-4b7a-b5fc-e6a96e7274d8'
    elif damage=='wrong_target':data['outcome']['target_at']=(NOW+timedelta(hours=2)).isoformat()
    elif damage=='outcome_epoch':data['outcome']['receipt']['streamEpoch']='064142d5-99ee-4b7a-b5fc-e6a96e7274d8'
    elif damage=='late_outcome':data['outcome']['receipt']['storedAt']=(NOW+timedelta(hours=1,seconds=1)).isoformat()
    elif damage=='missing_cycles':data['recent_cycle_grid']=data['recent_cycle_grid'][:-2]
    elif damage=='duplicate_cycles':data['recent_cycle_grid'].append(deepcopy(data['recent_cycle_grid'][0]))
    elif damage=='future_cycle':data['recent_cycle_grid'][0][0]=(NOW+timedelta(minutes=1)).isoformat()
    elif damage=='cycle_epoch':data['recent_cycle_grid'][0][1]['streamEpoch']='unbound'
    with pytest.raises(ValueError):evidence.score_qualified_origin(**data)


def test_missing_action_labels_do_not_remove_verified_forecast_pair(tmp_path):
    result=evidence.score_qualified_origin(**case(tmp_path))
    assert result['known_actions'] is None
    assert result['forecast_source_binding_verified'] is True
    assert result['action_response_qualification_claimed'] is False
