"""Private source-backed preregistration; fixtures are not release evidence."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from hashlib import sha256
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'openhab/scripts'))
from test_thermal_origin_capture import capture_inputs,NOW,EPOCH
from test_thermal_graduation_policy import inputs,START
from thermal_model.origin_capture import build_origin_capture,write_origin_capture
from thermal_model.forcing_capture import _canonical
from thermal_model.graduation_policy import derive_policy
from test_thermal_graduation_evidence import receipt


def shift(value,delta):
    if isinstance(value,dict):return {key:shift(entry,delta) for key,entry in value.items()}
    if isinstance(value,list):return [shift(entry,delta) for entry in value]
    if isinstance(value,str) and value.startswith('2026-'):
        try:return (datetime.fromisoformat(value)+delta).isoformat()
        except ValueError:pass
    return value


@pytest.fixture(scope='module')
def development(tmp_path_factory):
    root=tmp_path_factory.mktemp('registration-source');root.chmod(0o700)
    original=build_origin_capture(**capture_inputs());sources=[]
    for day in range(35):
        issue=START+timedelta(days=day);record=shift(original,issue-NOW)
        point=record['output']['forecast']['trajectory'][1]
        record['output']['forecast']['trajectory']=[record['output']['forecast']['trajectory'][0]]+[
            {**point,'at':(issue+timedelta(hours=hours)).isoformat()} for hours in (1,6,12,24)]
        record['sha256']={name:sha256(_canonical(record[name])).hexdigest() for name in record['sha256']}
        origin=write_origin_capture(root,record)
        publication=dict(time=int((issue+timedelta(seconds=1)).timestamp()*1000),state=json.dumps(record['output']))
        for hours in (1,6,12,24):
            target=issue+timedelta(hours=hours);cycles=[]
            for lag in (range(2,9) if hours==24 else range(1,8)):
                start=issue-timedelta(days=lag);end=target-timedelta(days=lag)
                # For 24h, a cycle's end equals the next cycle's start.
                for at in (start,end):
                    if not any(row[0]==at.isoformat() for row in cycles):
                        cycles.append([at.isoformat(),receipt(at,70 if hours==24 else (70 if at==start else 71))])
            sources.append(dict(origin_path=str(origin),publication=publication,horizon_hours=hours,
                outcome=dict(target_at=target.isoformat(),receipt=receipt(target,72)),recent_cycle_grid=cycles))
    args=inputs()
    for row in args['development']:
        row['persistence_error_f']=2;row['recent_cycle_error_f']=2 if row['horizon_hours']==24 else 3
    return derive_policy(**args),sources


def module():
    import thermal_policy_registration
    return thermal_policy_registration


def freeze_clock(monkeypatch,registration):
    monkeypatch.setattr(registration,'_clock',lambda:datetime(2026,7,17,12,tzinfo=timezone.utc))


def test_registration_copies_raw_sources_and_replays_identical_policy(tmp_path,development,monkeypatch):
    registration=module();freeze_clock(monkeypatch,registration)
    policy,sources=development;tmp_path.chmod(0o700)
    path=registration.register_policy(tmp_path,policy,sources)
    result=registration.read_registered_policy(path)
    assert result['schema']=='earthship-thermal-policy-registration/v1'
    assert result['policy']==policy
    assert result['registered_at']=='2026-07-17T12:00:00+00:00'
    assert len(result['development_sources'])==140
    assert all(not Path(source['origin_path']).is_absolute() for source in result['development_sources'])
    assert path.stat().st_mode & 0o777==0o600
    assert result['release_authorized'] is False
    assert registration.register_policy(tmp_path,policy,sources)==path


@pytest.mark.parametrize('damage',['late_registration','future_declaration','modified_baseline','missing_sources','modified_publication','epoch'])
def test_bad_registration_never_creates_a_policy_receipt(tmp_path,development,monkeypatch,damage):
    registration=module();freeze_clock(monkeypatch,registration)
    policy,sources=deepcopy(development);tmp_path.chmod(0o700)
    if damage=='late_registration':monkeypatch.setattr(registration,'_clock',lambda:datetime(2026,7,19,tzinfo=timezone.utc))
    elif damage=='future_declaration':monkeypatch.setattr(registration,'_clock',lambda:datetime(2026,7,16,tzinfo=timezone.utc))
    elif damage=='modified_baseline':
        policy['development'][0]['persistence_error_f']=99
        policy=derive_policy(**{key:policy[key] for key in ('development','declared_at','intervals','candidate','regimes')})
    elif damage=='missing_sources':sources.pop()
    elif damage=='modified_publication':sources[0]['publication']['state']='{}'
    elif damage=='epoch':sources[0]['outcome']['receipt']['streamEpoch']='064142d5-99ee-4b7a-b5fc-e6a96e7274d8'
    with pytest.raises(ValueError):registration.register_policy(tmp_path,policy,sources)
    assert not list(tmp_path.glob('*.registration.json'))


def test_replay_requires_original_raw_sources_not_only_the_cached_policy(tmp_path,development,monkeypatch):
    registration=module();freeze_clock(monkeypatch,registration)
    policy,sources=development;tmp_path.chmod(0o700)
    path=registration.register_policy(tmp_path,policy,sources)
    cached=json.loads(path.read_text());source=tmp_path/cached['development_sources'][0]['origin_path']
    source.unlink()
    with pytest.raises(ValueError):registration.read_registered_policy(path)


def test_policy_receipt_cannot_be_overwritten_or_extended(tmp_path,development,monkeypatch):
    registration=module();freeze_clock(monkeypatch,registration)
    policy,sources=development;tmp_path.chmod(0o700)
    path=registration.register_policy(tmp_path,policy,sources)
    cached=json.loads(path.read_text());cached['active']=True;path.write_text(json.dumps(cached))
    with pytest.raises(ValueError):registration.read_registered_policy(path)
    with pytest.raises(ValueError):registration.register_policy(tmp_path,policy,sources)


def test_holdout_starting_during_receipt_write_prevents_registration(tmp_path,development,monkeypatch):
    registration=module();policy,sources=development;tmp_path.chmod(0o700)
    clocks=iter([datetime(2026,7,17,12,tzinfo=timezone.utc),
        datetime(2026,7,17,12,tzinfo=timezone.utc),datetime(2026,7,19,tzinfo=timezone.utc)])
    monkeypatch.setattr(registration,'_clock',lambda:next(clocks))
    with pytest.raises(ValueError,match='actual registration'):
        registration.register_policy(tmp_path,policy,sources)
    assert not list(tmp_path.glob('*.registration.json'))


@pytest.fixture(scope='module')
def registered(tmp_path_factory,development):
    registration=module();root=tmp_path_factory.mktemp('registered-policy');root.chmod(0o700)
    patch=pytest.MonkeyPatch();freeze_clock(patch,registration)
    try:path=registration.register_policy(root,*development)
    finally:patch.undo()
    return path


@pytest.mark.parametrize('damage',['path_escape','receipt_changed','file_mode','origin_mode'])
def test_rehashed_receipt_still_requires_qualified_original_sources(tmp_path,registered,damage):
    import shutil
    registration=module();root=tmp_path/'private'
    shutil.copytree(registered.parent,root);path=root/registered.name
    value=json.loads(path.read_text())
    if damage=='path_escape':value['development_sources'][0]['origin_path']='sources/../escaped.json.gz'
    elif damage=='receipt_changed':value['development_sources'][0]['outcome']['receipt']['temperatureF']=70
    elif damage=='file_mode':path.chmod(0o644)
    elif damage=='origin_mode':(root/value['development_sources'][0]['origin_path']).chmod(0o644)
    if damage in ('path_escape','receipt_changed'):
        body={key:entry for key,entry in value.items() if key!='registration_sha256'}
        value['registration_sha256']=sha256(_canonical(body)).hexdigest();path.write_text(json.dumps(value))
    with pytest.raises(ValueError):registration.read_registered_policy(path)


def test_invalid_source_path_is_a_validation_refusal(tmp_path,monkeypatch):
    registration=module();freeze_clock(monkeypatch,registration);tmp_path.chmod(0o700)
    policy=derive_policy(**inputs())
    source=dict(origin_path={'malformed':True},publication={},horizon_hours=1,outcome={},recent_cycle_grid=[])
    with pytest.raises(ValueError,match='archive path'):
        registration.register_policy(tmp_path,policy,[source])
    assert not list(tmp_path.glob('*.registration.json'))
