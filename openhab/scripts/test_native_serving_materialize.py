"""The real native projection must survive the real observation cache writer."""
from test_native_serving_forecast import context,originals


def test_native_receipt_reaches_real_materializer(tmp_path,originals,monkeypatch):
    from household.weather_context import prepare_serving_native_cycle_contexts
    from household.model_snapshot import bind_model_snapshot
    from household.codec import canonical
    from household.control_contracts import instant
    from test_household_model_snapshot import source_at
    from test_household_model_pipeline import run
    import household_pipeline as pipeline,household_observation as observation
    forecasts,_,_,model,inputs,kwargs,_=context(tmp_path,originals,monkeypatch)
    capture=forecasts.build_serving_capture(model,inputs,**kwargs)
    thermal,_=prepare_serving_native_cycle_contexts(capture,model,code_revision='a'*40,expected_capture_sha256=capture['capture_sha256'],check_budget=lambda:None)
    source=source_at(instant(thermal.to_dict()['issue']))
    snap=bind_model_snapshot(source_receipt=source,source_runtime_manifest=source['runtime_manifest'],thermal_inputs=thermal,code_revision='a'*40)
    runtime={**pipeline.pipeline_runtime_manifest(expanded=True),**source['runtime_manifest']}
    monkeypatch.setattr(pipeline,'pipeline_runtime_manifest',lambda **kw:dict(runtime))
    # This fixture's power packet has an intentionally abbreviated runtime;
    # source closure is independently covered, while real replay stays intact.
    monkeypatch.setattr(pipeline,'verify_source_closure',lambda *a:None)
    record=run(snap,thermal,runtime_manifest=runtime)
    receipt=tmp_path/'native-receipt.json';receipt.write_bytes(canonical(record));receipt.chmod(0o600)
    target=tmp_path/'observation.json'
    result=observation.materialize(receipt,target,clock=lambda:instant(record['inputs']['now']))
    assert result['status']=='observation_written' and target.is_file()
