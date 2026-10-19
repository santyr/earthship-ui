"""Retired production profiles cannot reach local or external weather sources."""
import pytest
import native_thermal_live as live

RETIRED=('earthship-provisional-thermal-live-config/v1',
         'earthship-provisional-thermal-live-config/v2',
         'earthship-provisional-thermal-live-config/v3')


@pytest.mark.parametrize('schema',RETIRED)
def test_retired_native_configuration_has_no_selectable_field_contract(schema):
    with pytest.raises(ValueError):live.configuration_fields(schema)


@pytest.mark.parametrize('schema',RETIRED)
def test_retired_native_factory_refuses_before_any_source_lookup(monkeypatch,schema):
    selected=[]
    monkeypatch.setattr(live,'backend_settings',lambda value:selected.append('translation') or {},raising=False)
    monkeypatch.setattr(live,'CompressedSourceLiveBackend',lambda *a,**kw:selected.append('backend') or object(),raising=False)
    with pytest.raises(ValueError):
        live.make_forecast_backend({'schema':schema},evidence_directory='/unused',guard=lambda:None)
    assert selected==[]


@pytest.mark.parametrize('schema',[live.GOOGLE_LIVE_SCHEMA,live.GOOGLE_SERVING_SCHEMA])
def test_only_google_source_fields_are_required_for_native_production(schema):
    fields=live.configuration_fields(schema)
    assert 'weather_source' in fields and 'forecast_dsn_file' not in fields
    assert ('model_receipt_sha256' in fields)==(schema==live.GOOGLE_SERVING_SCHEMA)


@pytest.mark.parametrize('schema',RETIRED[1:])
def test_migration_can_pin_retired_baseline_metadata_without_selecting_it(tmp_path,schema):
    import json
    from test_native_household_deploy import native_fixture,api,write,encode
    args,_,candidate,settings=native_fixture(tmp_path)
    previous=json.loads(args['service_forecast_config'].read_bytes())
    previous.update(schema=schema,artifact_sha256='a'*64,runtime_sha256='b'*64,
        geometry_directory=settings['geometry_directory'])
    if schema==RETIRED[2]:
        previous.update(model_receipt_path=str(tmp_path/'old-receipt'),model_receipt_sha256='c'*64)
    write(args['service_forecast_config'],encode(previous))
    with pytest.raises(ValueError):live.load_settings(args['service_forecast_config'])
    assert api().stage_deployment(**args)['status']=='deployment_staged'
    record=api().verify_stage(args['stage'])
    assert record['runtime_sha256']==candidate['runtime_sha256']
    selected=json.loads((args['stage']/'cycle.json').read_bytes())
    assert selected['forecast_config']==str(args['forecast_config'])
    assert settings['schema']==live.GOOGLE_LIVE_SCHEMA
