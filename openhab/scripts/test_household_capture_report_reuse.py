"""Full captured inputs reuse only inside the original report inventory."""
from copy import deepcopy
from contextvars import Context
import pytest
from test_native_serving_score import originals
from test_household_score_report_reuse import report_fixture


def test_capture_reuse_keeps_original_reads_copies_chronology_and_complete_keys(tmp_path,originals,monkeypatch):
    import household_score_report_reuse as reuse,native_thermal_forecast as forecasts
    import native_model_serving_receipt as serving
    from thermal_model.replay_budget import capture_source_reads
    from pathlib import Path
    scores,entries,kwargs,expected,calls,args,path=report_fixture(tmp_path,originals,monkeypatch)
    selection=kwargs['selections'][0];at=kwargs['assessed_at']
    model=serving.read_serving_model(selection,assessed_at=at,guard=lambda:None)
    numeric=forecasts._numeric;rollouts=[]
    def counted(*a,**kw):rollouts.append(1);return numeric(*a,**kw)
    monkeypatch.setattr(forecasts,'_numeric',counted)
    capture_path=Path(args['capture_path']);pin=args['expected_capture_sha256'];original=forecasts.validate_serving_capture
    with reuse._model_reads(scores,at),reuse._capture_reads(lambda:None):
        with capture_source_reads() as inventory:
            first=forecasts.read_serving_capture(capture_path,model,expected_capture_sha256=pin)
            first['output']['trajectory'][0]['air_f']=0
            value=forecasts.read_serving_capture(capture_path,model,expected_capture_sha256=pin)
            assert value['output']['trajectory'][0]['air_f']!=0
            assert len(rollouts)==1,'one report repeated identical captured numerical/source validation'
            with pytest.raises(ValueError):forecasts.validate_serving_capture(value,model,expected_capture_sha256='0'*64)
            changed=deepcopy(value);changed['output']['trajectory'][0]['air_f']+=1
            changed['capture_sha256']=forecasts.digest(changed,'capture_sha256')
            with pytest.raises(ValueError):forecasts.validate_serving_capture(changed,model,expected_capture_sha256=changed['capture_sha256'])
            before=len(rollouts);Context().run(forecasts.validate_serving_capture,value,model,expected_capture_sha256=pin)
            assert len(rollouts)>before
            inventory.verify()
    assert forecasts.validate_serving_capture is original


def test_capture_reuse_is_bounded_unknown_fallback_and_restores_on_refusal(tmp_path,originals,monkeypatch):
    import household_score_report_reuse as reuse,native_thermal_forecast as forecasts
    import native_model_serving_receipt as serving
    from thermal_model.replay_budget import capture_source_reads
    from pathlib import Path
    scores,entries,kwargs,expected,calls,args,path=report_fixture(tmp_path,originals,monkeypatch)
    model=serving.read_serving_model(kwargs['selections'][0],assessed_at=kwargs['assessed_at'],guard=lambda:None)
    original=forecasts.validate_serving_capture;capture_path=Path(args['capture_path']);pin=args['expected_capture_sha256']
    numeric=forecasts._numeric;rollouts=[]
    def counted(*a,**kw):rollouts.append(1);return numeric(*a,**kw)
    monkeypatch.setattr(forecasts,'_numeric',counted)
    monkeypatch.setattr(reuse,'MAX_CAPTURE_CACHE_BYTES',1)
    with reuse._model_reads(scores,kwargs['assessed_at']),reuse._capture_reads(lambda:None),capture_source_reads():
        forecasts.read_serving_capture(capture_path,model,expected_capture_sha256=pin)
        forecasts.read_serving_capture(capture_path,model,expected_capture_sha256=pin)
        assert len(rollouts)==2
    for failure in (TimeoutError,KeyboardInterrupt):
        with pytest.raises(failure):
            with reuse._capture_reads(lambda:None),capture_source_reads():
                with reuse._capture_reads(lambda:None):
                    forecasts.read_serving_capture(capture_path,model,expected_capture_sha256=pin)
                raise failure()
        assert forecasts.validate_serving_capture is original
    monkeypatch.setattr(reuse,'CAPTURE_SOURCE_SHA256','0'*64)
    with reuse._capture_reads(lambda:None):assert forecasts.validate_serving_capture is original


def test_validated_large_capture_reuses_under_small_private_metadata_budget(tmp_path,originals,monkeypatch):
    import household_score_report_reuse as reuse,native_thermal_forecast as forecasts
    import native_model_serving_receipt as serving
    from thermal_model.replay_budget import capture_source_reads
    from pathlib import Path
    scores,entries,kwargs,expected,calls,args,path=report_fixture(tmp_path,originals,monkeypatch)
    model=serving.read_serving_model(kwargs['selections'][0],assessed_at=kwargs['assessed_at'],guard=lambda:None)
    numeric=forecasts._numeric;rollouts=[]
    def counted(*a,**kw):rollouts.append(1);return numeric(*a,**kw)
    monkeypatch.setattr(forecasts,'_numeric',counted)
    monkeypatch.setattr(reuse,'MAX_CAPTURE_CACHE_BYTES',8192)
    with reuse._model_reads(scores,kwargs['assessed_at']),reuse._capture_reads(lambda:None),capture_source_reads() as inventory:
        for _ in range(2):forecasts.read_serving_capture(Path(args['capture_path']),model,expected_capture_sha256=args['expected_capture_sha256'])
        assert len(rollouts)==1,'retained full capture copies exhausted the bounded validation metadata budget'
        inventory.verify()


def test_unknown_model_helper_leaves_capture_validation_unchanged(monkeypatch):
    import household_score_report_reuse as reuse,native_thermal_forecast as forecasts
    monkeypatch.setattr(reuse,'SUPPORTED_MODEL_HELPER_SHA256','0'*64)
    monkeypatch.setattr(reuse,'PRIOR_MODEL_HELPER_SHA256','0'*64)
    original=forecasts.validate_serving_capture
    with reuse._capture_reads(lambda:None):assert forecasts.validate_serving_capture is original


def test_reused_capture_refuses_same_byte_replacement_of_original_query(tmp_path,originals,monkeypatch):
    import household_score_report_reuse as reuse,native_thermal_forecast as forecasts
    import native_model_serving_receipt as serving
    from thermal_model.replay_budget import capture_source_reads
    from pathlib import Path
    import json
    scores,entries,kwargs,expected,calls,args,path=report_fixture(tmp_path,originals,monkeypatch)
    model=serving.read_serving_model(kwargs['selections'][0],assessed_at=kwargs['assessed_at'],guard=lambda:None)
    capture_path=Path(args['capture_path']);capture=json.loads(capture_path.read_bytes())
    target=Path(next(iter(capture['native_origin_binding']['query_sources'].values())))
    with pytest.raises(ValueError):
        with reuse._model_reads(scores,kwargs['assessed_at']),reuse._capture_reads(lambda:None),capture_source_reads() as inventory:
            forecasts.read_serving_capture(capture_path,model,expected_capture_sha256=args['expected_capture_sha256'])
            replacement=target.with_name('replacement-query');replacement.write_bytes(target.read_bytes());replacement.chmod(0o600);replacement.replace(target)
            forecasts.read_serving_capture(capture_path,model,expected_capture_sha256=args['expected_capture_sha256'])
            inventory.verify()
