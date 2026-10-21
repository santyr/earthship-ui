"""The public atmosphere group must remain separate from original temperature scores."""
from copy import deepcopy
from datetime import timedelta
import importlib,json
import pytest
from capability_fixtures import reader
from learning_fixtures import T,SITE,native_snapshot
from weather_learning.archive import Archive
from weather_learning.worker import collect_once
from weather_learning.capability_publish import build_capability_report,validate_capability_report,retain_capability_report
from weather_learning.contracts import canonical,identity


def api():return importlib.import_module('weather_learning.atmospheric_publish')
def intake(tmp_path):
    r,clock=reader();archive=Archive(tmp_path/'archive')
    collected=collect_once(r,archive,probe=False,horizon=360,include_interim=True,clock=lambda:clock[0],free_bytes=10**9,optional_profiles=('atmosphere-v1',))
    return archive,clock[0],collected


def test_v2_atmosphere_keeps_the_v1_temperature_rows_and_originals(tmp_path):
    archive,decision,collected=intake(tmp_path);before={p.name:p.read_bytes() for p in archive.objects.glob('*.json')}
    base=build_capability_report(archive,decision=decision,site=SITE)
    value=api().build_atmospheric_report(archive,decision=decision,site=SITE)
    assert value['schema']=='earthship-weathernext-capabilities/v2'
    assert value['groups']['temperature']==base['groups']['temperature'] and value['sources']==base['sources']
    assert value['groups']['temperature']['hours'][0]['p50_c'] is None
    group=value['groups']['atmosphere'];assert len(group['hours'])==24
    row=group['hours'][0];fields=row['fields']
    assert fields['dewpoint']['value']==5 and fields['pressure']['value']==900
    assert fields['speed']['value']==2 and row['vector_magnitude_m_s']==pytest.approx(2**.5)
    assert row['wind_from_degrees']==pytest.approx(135) and fields['high']['value']==40
    proof={s['ref_sha256']:s for s in group['sources']}
    assert proof[fields['u']['source_ref']]['snapshot_sha256'] in {r['snapshot_sha256'] for r in collected['capabilities']}
    assert proof[fields['temperature']['source_ref']]['snapshot_sha256']!=proof[fields['u']['source_ref']]['snapshot_sha256']
    assert validate_capability_report(value)==value
    assert len(canonical(value))<=256*1024
    assert {p.name:p.read_bytes() for p in archive.objects.glob('*.json')}==before
    assert not any(text in json.dumps(value) for text in ['latitude','longitude','registry_raw','device_id','/home/'])


def test_core_only_archive_still_delivers_dewpoint_pressure_and_no_invented_layers(tmp_path):
    r,clock=reader();archive=Archive(tmp_path/'archive')
    collect_once(r,archive,probe=False,horizon=360,include_interim=True,clock=lambda:clock[0],free_bytes=10**9)
    value=api().build_atmospheric_report(archive,decision=clock[0],site=SITE)
    row=value['groups']['atmosphere']['hours'][0]
    assert row['fields']['dewpoint'] is not None and row['fields']['pressure'] is not None
    assert row['fields']['u'] is None and row['wind_from_degrees'] is None and row['fields']['high'] is None
    assert value['groups']['atmosphere']['moisture']['mode']=='outdoor_only'


@pytest.mark.parametrize('damage',['private','derived','clock','source','layer','authority'])
def test_v2_validator_refuses_unbound_private_derived_or_authority_claims(tmp_path,damage):
    archive,decision,_=intake(tmp_path);value=api().build_atmospheric_report(archive,decision=decision,site=SITE)
    g=value['groups']['atmosphere'];row=g['hours'][0]
    if damage=='private':g['private_path']='/operator-private'
    if damage=='derived':row['wind_from_degrees']=123
    if damage=='clock':g['sources'][0]['available_at']=(decision+timedelta(seconds=1)).isoformat()
    if damage=='source':row['fields']['u']['source_ref']='f'*64
    if damage=='layer':row['fields']['high']['value']=101
    if damage=='authority':g['temperature_model_uses_fields']=True
    value['report_sha256']=identity({k:v for k,v in value.items() if k!='report_sha256'})
    with pytest.raises(ValueError):validate_capability_report(value)


def test_v2_issued_original_is_retained_and_registers_the_same_temperature_values(tmp_path):
    archive,decision,_=intake(tmp_path);value=api().build_atmospheric_report(archive,decision=decision,site=SITE)
    root=tmp_path/'shadow';retain_capability_report(root,value)
    assert json.loads((root/'weather-capabilities.json').read_text())==value
    original=(root/'capability-issues'/(value['report_sha256']+'.json')).read_bytes()
    assert json.loads(original)['groups']['temperature']==value['groups']['temperature']
    from weather_learning.capability_scoring import CapabilityScores
    from weather_learning.shadow import ShadowStore
    queue=CapabilityScores(ShadowStore(root))
    with queue.connect() as db:assert db.execute('SELECT COUNT(*) FROM targets').fetchone()[0]>0


def test_available_atmosphere_does_not_require_temperature_and_skips_empty_initial_target(tmp_path):
    from test_atmospheric_context import source,DECISION,SITE as AT_SITE,T as AT_T
    from weather_learning.weathernext_ee import parse_collection_response,make_snapshot
    original=source(station=False,u=1.,v=0.)['source_originals'][0];raw=deepcopy(original['payload'])
    raw['metadata'].append(dict(raw['metadata'][0],**{'system:index':'a2','end_time':(AT_T+timedelta(hours=2)).isoformat(),'forecast_hour':2}))
    raw['region'].append(['a2',-105.,40.,(AT_T+timedelta(hours=2)).timestamp()*1000,*raw['region'][1][4:]])
    raw['region'][1][4:]=[None]*len(raw['region'][1][4:])
    parsed=parse_collection_response(raw,collection=original['collection'],bands=raw['region'][0][4:],site=AT_SITE,initialized_at=AT_T,horizon=2)
    snapshot=make_snapshot([parsed],site=AT_SITE,initialized_at=AT_T,first_seen_at=AT_T+timedelta(minutes=20),completed_at=AT_T+timedelta(minutes=21))
    archive=Archive(tmp_path/'archive');archive.store_snapshot(snapshot)
    value=api().build_atmospheric_report(archive,decision=DECISION,site=AT_SITE)
    assert value['status']=='available' and value['groups']['temperature']['hours']==[]
    assert len(value['groups']['atmosphere']['hours'])==1
    assert value['groups']['atmosphere']['moisture']['outdoor_target_at']==(AT_T+timedelta(hours=2)).isoformat()


def test_invalid_newest_optional_quantity_does_not_mask_an_older_valid_field(tmp_path):
    from weather_learning.weathernext_ee import parse_collection_response,make_snapshot
    archive,decision,_=intake(tmp_path)
    core=next(archive.read(p.stem) for p in archive.objects.glob('*.json') if any(q['variable']=='mean_sea_level_pressure' for q in archive.read(p.stem)['points']) and archive.read(p.stem)['initialized_at']==(T+timedelta(hours=1)).isoformat())
    parsed=[]
    for original in core['source_originals']:
        raw=deepcopy(original['payload']);header=raw['region'][0]
        if 'mean_sea_level_pressure_mean' in header:
            position=header.index('mean_sea_level_pressure_mean')
            for row in raw['region'][1:]:row[position]=200000.
        parsed.append(parse_collection_response(raw,collection=original['collection'],bands=header[4:],site=SITE,initialized_at=T+timedelta(hours=1),horizon=len(raw['metadata'])))
    bad=make_snapshot(parsed,site=SITE,initialized_at=T+timedelta(hours=1),first_seen_at=decision,completed_at=decision+timedelta(seconds=1));archive.store_snapshot(bad)
    value=api().build_atmospheric_report(archive,decision=decision+timedelta(minutes=1),site=SITE)
    assert value['groups']['atmosphere']['hours'][0]['fields']['pressure']['value']==900


def test_qualified_moisture_original_must_be_retained_before_its_public_claim(tmp_path,monkeypatch):
    import test_moisture_context as fixtures
    archive,decision,_=intake(tmp_path);monkeypatch.setattr(fixtures,'DECISION',decision);prepared=fixtures.indoor()
    value=api().build_atmospheric_report(archive,decision=decision,site=SITE,indoor=prepared,zone='room')
    m=value['groups']['atmosphere']['moisture'];assert m['mode']=='qualified_comparison'
    root=tmp_path/'shadow'
    with pytest.raises(ValueError):retain_capability_report(root,value)
    assert not (root/'weather-capabilities.json').exists()
    retain_capability_report(root,value,indoor=prepared)
    private=root/'capability-issues'/(m['indoor_context_sha256']+'.indoor.json')
    assert identity(json.loads(private.read_text()))==m['indoor_context_sha256']
    assert 'registry_raw' not in (root/'weather-capabilities.json').read_text()
    assert private.stat().st_mode&0o077==0


def test_explicit_atmosphere_worker_keeps_prepare_read_only_and_retains_its_qualified_input_on_apply(tmp_path,monkeypatch):
    import test_moisture_context as fixtures
    from weather_learning.capability_worker import publish_capabilities
    archive,decision,_=intake(tmp_path);monkeypatch.setattr(fixtures,'DECISION',decision);prepared=fixtures.indoor();root=tmp_path/'shadow'
    result=publish_capabilities(archive.root,root,decision=decision,site=SITE,include_atmosphere=True,indoor=prepared,indoor_zone='room',apply=False)
    assert result['atmospheric_hours']==24 and not root.exists()
    publish_capabilities(archive.root,root,decision=decision,site=SITE,include_atmosphere=True,indoor=prepared,indoor_zone='room',apply=True)
    assert json.loads((root/'weather-capabilities.json').read_text())['schema']=='earthship-weathernext-capabilities/v2'
    assert len(list((root/'capability-issues').glob('*.indoor.json')))==1


def test_retention_replays_claimed_indoor_values_against_the_actual_qualified_original(tmp_path,monkeypatch):
    import test_moisture_context as fixtures
    from weather_learning.atmospheric_context import vapor_pressure_hpa
    archive,decision,_=intake(tmp_path);monkeypatch.setattr(fixtures,'DECISION',decision);prepared=fixtures.indoor()
    value=api().build_atmospheric_report(archive,decision=decision,site=SITE,indoor=prepared,zone='room')
    m=value['groups']['atmosphere']['moisture'];m['indoor_temperature_c']=23.
    m['indoor_vapor_pressure_hpa']=vapor_pressure_hpa(23.)*m['indoor_relative_humidity_pct']/100
    m['context_sha256']=identity({k:v for k,v in m.items() if k!='context_sha256'})
    value['report_sha256']=identity({k:v for k,v in value.items() if k!='report_sha256'})
    # A self-consistent public arithmetic claim still cannot borrow another
    # original sensor context's proof hash while changing the measured input.
    assert validate_capability_report(value)==value
    root=tmp_path/'shadow'
    with pytest.raises(ValueError):retain_capability_report(root,value,indoor=prepared)
    assert not (root/'weather-capabilities.json').exists()
