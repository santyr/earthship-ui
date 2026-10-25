"""Weather validation may be shared only by successfully retained full captures."""
from copy import deepcopy
from datetime import timedelta
import json
import sys
import pytest
from test_native_serving_forecast import context,originals


def weather_captures(tmp_path,originals,monkeypatch):
    from household.codec import canonical,identity
    import thermal_weather_source as weather
    forecasts,_,candidate,model,inputs,kwargs,_=context(tmp_path,originals,monkeypatch)
    root=tmp_path/'weather';root.mkdir(mode=0o700)
    selected=dict(schema='earthship-thermal-weather-selection/v2',state_directory=str(root),
        source_sensor_epoch=candidate['fit']['sensor_epochs']['outdoor'],available_at=kwargs['available'].isoformat(),
        runtime_sha256=identity(weather.production_conditioning_runtime()),automatic_actuation=False)
    selected['selection_sha256']=identity(selected);path=root/'selection.json';path.write_bytes(canonical(selected));path.chmod(0o600)
    value=weather.collect_context(selection=path,forecast=inputs['forecast'],geometry=kwargs['geometry'],
        issue=kwargs['issue'],sensor_epoch=selected['source_sensor_epoch'],guard=lambda:None,clock=lambda:kwargs['available'])
    first=forecasts.build_serving_capture(model,inputs,weather_conditioning=value,**kwargs)
    second=forecasts.build_serving_capture(model,inputs,weather_conditioning=value,**{**kwargs,'published':kwargs['published']+timedelta(microseconds=1)})
    assert first['capture_sha256']!=second['capture_sha256']
    return forecasts,model,first,second,kwargs['issue']+timedelta(hours=1)


def count_weather():
    import thermal_weather_source as weather
    calls=[];code=weather.verify_bindings.__code__
    def profile(frame,event,arg):
        if event=='call' and frame.f_code is code:calls.append(1)
    return calls,profile


def test_distinct_valid_captures_reuse_complete_weather_subvalidation(tmp_path,originals,monkeypatch):
    import household_score_report_reuse as reuse,native_thermal_score as scores
    from thermal_model.replay_budget import capture_source_reads
    forecasts,model,first,second,at=weather_captures(tmp_path,originals,monkeypatch)
    calls,profile=count_weather();sys.setprofile(profile)
    try:
        with reuse._model_reads(scores,at),reuse._capture_reads(lambda:None),capture_source_reads() as inventory:
            for value in (first,second):
                assert forecasts.validate_serving_capture(value,model,expected_capture_sha256=value['capture_sha256'])==value
            inventory.verify()
        assert len(calls)==1,'distinct captures repeated identical original weather validation'
    finally:sys.setprofile(None)


def test_failed_full_capture_does_not_admit_weather_subvalidation(tmp_path,originals,monkeypatch):
    import household_score_report_reuse as reuse,native_thermal_score as scores
    from thermal_model.replay_budget import capture_source_reads
    forecasts,model,first,second,at=weather_captures(tmp_path,originals,monkeypatch)
    first['output']['trajectory'][0]['air_f']+=1;first['capture_sha256']=forecasts.digest(first,'capture_sha256')
    calls,profile=count_weather();sys.setprofile(profile)
    try:
        with reuse._model_reads(scores,at),reuse._capture_reads(lambda:None),capture_source_reads():
            with pytest.raises(ValueError):forecasts.validate_serving_capture(first,model,expected_capture_sha256=first['capture_sha256'])
            assert forecasts.validate_serving_capture(second,model,expected_capture_sha256=second['capture_sha256'])==second
        assert len(calls)==2
    finally:sys.setprofile(None)


def test_every_weather_field_participates_and_mutable_input_is_not_retained(tmp_path,originals,monkeypatch):
    import household_score_report_reuse as reuse,native_thermal_score as scores,thermal_weather_source as weather
    from thermal_model.replay_budget import capture_source_reads
    forecasts,model,first,second,at=weather_captures(tmp_path,originals,monkeypatch)
    value=first['weather_conditioning'];calls,profile=count_weather();sys.setprofile(profile)
    try:
        with reuse._model_reads(scores,at),reuse._capture_reads(lambda:None),capture_source_reads():
            forecasts.validate_serving_capture(first,model,expected_capture_sha256=first['capture_sha256'])
            for name,original in value.items():
                changed=deepcopy(value)
                changed[name]=(original+'changed' if type(original) is str else not original if type(original) is bool
                    else original+[None] if type(original) is list else {**original,'changed':True} if type(original) is dict else 'changed')
                before=len(calls)
                with pytest.raises((ValueError,TypeError,KeyError)):
                    weather.verify_bindings(changed,guard=lambda:None)
                assert len(calls)==before+1,name
            first['weather_conditioning']['rows'][0]['tempF']+=1
            before=len(calls)
            assert forecasts.validate_serving_capture(second,model,expected_capture_sha256=second['capture_sha256'])==second
            assert len(calls)==before
    finally:sys.setprofile(None)


@pytest.mark.parametrize('fallback',['bytes','entries','unknown_source','unknown_function','new_inventory','foreign_context','nested'])
def test_weather_subvalidation_fallback_and_context_lifetime(tmp_path,originals,monkeypatch,fallback):
    from contextvars import Context
    import household_score_report_reuse as reuse,native_thermal_score as scores,thermal_weather_source as weather
    from thermal_model.replay_budget import capture_source_reads
    forecasts,model,first,second,at=weather_captures(tmp_path,originals,monkeypatch)
    if fallback=='bytes':monkeypatch.setattr(reuse,'MAX_CAPTURE_CACHE_BYTES',1)
    if fallback=='entries':monkeypatch.setattr(reuse,'MAX_CAPTURE_CACHE_ENTRIES',0)
    if fallback=='unknown_source':monkeypatch.setitem(reuse.CAPTURE_WEATHER_RUNTIME,'thermal_weather_source.py','0'*64)
    if fallback=='unknown_function':
        delegate=weather.verify_bindings
        monkeypatch.setattr(weather,'verify_bindings',lambda value,*,guard:delegate(value,guard=guard))
    original=weather.verify_bindings;calls,profile=count_weather();sys.setprofile(profile)
    def validate():return forecasts.validate_serving_capture(second,model,expected_capture_sha256=second['capture_sha256'])
    try:
        with reuse._model_reads(scores,at),reuse._capture_reads(lambda:None),capture_source_reads():
            forecasts.validate_serving_capture(first,model,expected_capture_sha256=first['capture_sha256'])
            if fallback=='new_inventory':
                with capture_source_reads():assert validate()==second
            elif fallback=='foreign_context':assert Context().run(validate)==second
            elif fallback=='nested':
                with reuse._capture_reads(lambda:None):assert validate()==second
            else:assert validate()==second
        assert len(calls)==2
        assert weather.verify_bindings is original
    finally:sys.setprofile(None)


def test_weather_metadata_is_charged_within_existing_capture_budget(tmp_path,originals,monkeypatch):
    from hashlib import sha256
    import household_score_report_reuse as reuse,native_thermal_score as scores
    from thermal_model.replay_budget import capture_source_reads
    forecasts,model,first,_,at=weather_captures(tmp_path,originals,monkeypatch)
    # Independent accounting of the OLD retained metadata: enough before this
    # change, deliberately insufficient for its extra weather digest/container.
    old=(sha256(reuse._json_key(first)).digest(),sha256(model._encoded).digest(),
         sha256(model._selection._encoded).digest(),first['capture_sha256'])
    old_weight=sys.getsizeof(old)+sum(map(sys.getsizeof,old))+512
    monkeypatch.setattr(reuse,'MAX_CAPTURE_CACHE_BYTES',old_weight)
    calls,profile=count_weather();sys.setprofile(profile)
    try:
        with reuse._model_reads(scores,at),reuse._capture_reads(lambda:None),capture_source_reads():
            for _ in range(2):forecasts.validate_serving_capture(first,model,expected_capture_sha256=first['capture_sha256'])
        assert len(calls)==2,'weather digest was retained without charging the fixed metadata budget'
    finally:sys.setprofile(None)


def test_weather_validation_disappears_when_its_capture_entry_is_evicted(tmp_path,originals,monkeypatch):
    import household_score_report_reuse as reuse,native_thermal_score as scores
    from thermal_model.replay_budget import capture_source_reads
    forecasts,model,first,second,at=weather_captures(tmp_path,originals,monkeypatch)
    other=deepcopy(second);other['weather_conditioning']['reason']='production_temperature_test_unavailable'
    other['weather_conditioning']['context_sha256']=forecasts.digest(other['weather_conditioning'],'context_sha256')
    other['capture_sha256']=forecasts.digest(other,'capture_sha256')
    monkeypatch.setattr(reuse,'MAX_CAPTURE_CACHE_ENTRIES',1)
    calls,profile=count_weather();sys.setprofile(profile)
    try:
        with reuse._model_reads(scores,at),reuse._capture_reads(lambda:None),capture_source_reads():
            for value in (first,other,second):assert forecasts.validate_serving_capture(value,model,expected_capture_sha256=value['capture_sha256'])==value
        assert len(calls)==3,'evicted capture left independent weather validation state behind'
    finally:sys.setprofile(None)


def test_unknown_loaded_weather_function_cannot_admit_subvalidation(tmp_path,originals,monkeypatch):
    import household_score_report_reuse as reuse,native_thermal_score as scores,production_thermal_source as production
    from thermal_model.replay_budget import capture_source_reads
    forecasts,model,first,second,at=weather_captures(tmp_path,originals,monkeypatch)
    calls,profile=count_weather();original=production.verify;sys.setprofile(profile)
    try:
        with reuse._model_reads(scores,at),reuse._capture_reads(lambda:None),capture_source_reads():
            with monkeypatch.context() as patch:
                patch.setattr(production,'verify',lambda value,*,guard:original(value,guard=guard))
                forecasts.validate_serving_capture(first,model,expected_capture_sha256=first['capture_sha256'])
            assert forecasts.validate_serving_capture(second,model,expected_capture_sha256=second['capture_sha256'])==second
        assert len(calls)==2
    finally:sys.setprofile(None)


@pytest.mark.parametrize('error',[TimeoutError,KeyboardInterrupt])
def test_weather_hit_guard_refusal_restores_both_hooks(tmp_path,originals,monkeypatch,error):
    import household_score_report_reuse as reuse,native_thermal_score as scores,thermal_weather_source as weather
    from thermal_model.replay_budget import capture_source_reads
    forecasts,model,first,_,at=weather_captures(tmp_path,originals,monkeypatch)
    original=forecasts.validate_serving_capture;original_weather=weather.verify_bindings
    def fail():raise error()
    with pytest.raises(error):
        with reuse._model_reads(scores,at),reuse._capture_reads(lambda:None),capture_source_reads():
            forecasts.validate_serving_capture(first,model,expected_capture_sha256=first['capture_sha256'])
            weather.verify_bindings(first['weather_conditioning'],guard=fail)
    assert forecasts.validate_serving_capture is original and weather.verify_bindings is original_weather


def test_unknown_capture_source_does_not_require_weather_modules(monkeypatch):
    import builtins
    import household_score_report_reuse as reuse,native_thermal_forecast as forecasts
    original=forecasts.validate_serving_capture;import_module=builtins.__import__
    monkeypatch.setattr(reuse,'CAPTURE_SOURCE_SHA256','0'*64)
    def limited(name,*args,**kwargs):
        if name in ('thermal_weather_source','production_thermal_source'):raise ImportError('unknown archive lacks weather adapter')
        return import_module(name,*args,**kwargs)
    monkeypatch.setattr(builtins,'__import__',limited)
    with reuse._capture_reads(lambda:None):assert forecasts.validate_serving_capture is original


@pytest.mark.parametrize('layout',['absent','renamed','unknown_source'])
def test_optional_private_weather_layout_keeps_original_validation(tmp_path,originals,monkeypatch,layout):
    import household_score_report_reuse as reuse,native_thermal_score as scores,production_thermal_source as production
    from thermal_model.replay_budget import capture_source_reads
    forecasts,model,first,second,at=weather_captures(tmp_path,originals,monkeypatch)
    assert first['weather_conditioning']['mode']=='native_raw_fallback'
    if layout=='renamed':monkeypatch.setattr(production,'_renamed_points',production._points,raising=False)
    monkeypatch.delattr(production,'_points')
    if layout=='unknown_source':monkeypatch.setitem(reuse.CAPTURE_WEATHER_RUNTIME,'production_thermal_source.py','0'*64)
    # The real public verifier supports this valid fallback without _points.
    production.verify(first['weather_conditioning'],guard=lambda:None)
    calls,profile=count_weather();sys.setprofile(profile)
    try:
        with reuse._model_reads(scores,at),reuse._capture_reads(lambda:None),capture_source_reads():
            for value in (first,second,first):
                assert forecasts.validate_serving_capture(value,model,expected_capture_sha256=value['capture_sha256'])==value
        assert len(calls)==3,'unsupported layout retained weather-dependent capture validation'
    finally:sys.setprofile(None)


def copied_weather_runtime(tmp_path):
    from pathlib import Path
    import household_score_report_reuse as reuse,thermal_weather_source as weather
    root=tmp_path/'foreign-runtime';root.mkdir()
    for name in reuse.CAPTURE_WEATHER_RUNTIME:
        target=root/name;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes((Path(weather.__file__).parent/name).read_bytes());target.chmod(0o644)
    return root


def preload_weather(root,monkeypatch):
    import importlib.util
    for name in ('thermal_weather_source','production_thermal_source'):
        spec=importlib.util.spec_from_file_location(name,root/(name+'.py'))
        module=importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules,name,module);spec.loader.exec_module(module)


@pytest.mark.parametrize('same_capture',[False,True])
def test_foreign_preloaded_weather_uses_its_original_runtime_root(tmp_path,originals,monkeypatch,same_capture):
    import household_score_report_reuse as reuse,native_thermal_score as scores
    from thermal_model.replay_budget import capture_source_reads
    forecasts,model,first,second,at=weather_captures(tmp_path,originals,monkeypatch)
    foreign=copied_weather_runtime(tmp_path);preload_weather(foreign,monkeypatch)
    import thermal_weather_source as weather
    assert weather.production_conditioning_runtime()==first['weather_conditioning']['runtime_manifest']
    calls,profile=count_weather();sys.setprofile(profile)
    try:
        with reuse._model_reads(scores,at),reuse._capture_reads(lambda:None),capture_source_reads():
            assert forecasts.validate_serving_capture(first,model,expected_capture_sha256=first['capture_sha256'])==first
            target=foreign/'weather_learning/provider.py';target.write_bytes(target.read_bytes()+b'\n')
            value=first if same_capture else second
            with pytest.raises(ValueError,match='original production thermal runtime differs'):
                forecasts.validate_serving_capture(value,model,expected_capture_sha256=value['capture_sha256'])
        assert len(calls)==2,'foreign runtime did not execute original verification on every call'
    finally:sys.setprofile(None)


@pytest.mark.parametrize('same_capture',[False,True])
@pytest.mark.parametrize('changed',['bytes','permission','symlink','root_alias'])
def test_weather_runtime_root_change_after_admission_runs_original(tmp_path,originals,monkeypatch,same_capture,changed):
    import household_score_report_reuse as reuse,native_thermal_score as scores,thermal_weather_source as weather
    from thermal_model.replay_budget import capture_source_reads
    forecasts,model,first,second,at=weather_captures(tmp_path,originals,monkeypatch)
    foreign=copied_weather_runtime(tmp_path);target=foreign/'weather_learning/provider.py'
    calls,profile=count_weather();sys.setprofile(profile)
    try:
        with reuse._model_reads(scores,at),reuse._capture_reads(lambda:None),capture_source_reads():
            assert forecasts.validate_serving_capture(first,model,expected_capture_sha256=first['capture_sha256'])==first
            monkeypatch.setattr(weather,'SCRIPTS',foreign)
            if changed=='bytes':target.write_bytes(target.read_bytes()+b'\n')
            elif changed=='permission':target.chmod(0o666)
            elif changed=='symlink':
                saved=foreign/'saved-provider.py';target.rename(saved);target.symlink_to(saved)
            else:
                alias=tmp_path/'runtime-alias';alias.symlink_to(foreign,target_is_directory=True)
                monkeypatch.setattr(weather,'SCRIPTS',alias)
            value=first if same_capture else second
            with pytest.raises(ValueError,match='original production thermal runtime differs|owned bounded immutable source required'):
                forecasts.validate_serving_capture(value,model,expected_capture_sha256=value['capture_sha256'])
        assert len(calls)==2,'runtime-root change bypassed the original verifier'
    finally:sys.setprofile(None)


def test_weather_free_capture_does_not_require_optional_weather_layout(tmp_path,originals,monkeypatch):
    import household_score_report_reuse as reuse,native_thermal_score as scores,thermal_weather_source as weather
    from thermal_model.replay_budget import capture_source_reads
    forecasts,_,_,model,inputs,kwargs,_=context(tmp_path,originals,monkeypatch)
    value=forecasts.build_serving_capture(model,inputs,**kwargs)
    monkeypatch.delattr(weather,'verify_bindings')
    with reuse._model_reads(scores,kwargs['issue']+timedelta(hours=1)),reuse._capture_reads(lambda:None),capture_source_reads():
        assert forecasts.validate_serving_capture(value,model,expected_capture_sha256=value['capture_sha256'])==value


@pytest.mark.parametrize('full_capture_hit',[False,True])
def test_weather_hit_guard_root_change_requires_original_validation(tmp_path,originals,monkeypatch,full_capture_hit):
    import household_score_report_reuse as reuse,native_thermal_score as scores,thermal_weather_source as weather
    from thermal_model.replay_budget import capture_source_reads
    forecasts,model,first,_,at=weather_captures(tmp_path,originals,monkeypatch)
    foreign=copied_weather_runtime(tmp_path);target=foreign/'weather_learning/provider.py'
    target.write_bytes(target.read_bytes()+b'\n')
    checks=[]
    def changing_guard():
        checks.append(1)
        if len(checks)==2:monkeypatch.setattr(weather,'SCRIPTS',foreign)
    calls,profile=count_weather();sys.setprofile(profile)
    try:
        with reuse._model_reads(scores,at),reuse._capture_reads(lambda:None),capture_source_reads():
            forecasts.validate_serving_capture(first,model,expected_capture_sha256=first['capture_sha256'])
            with pytest.raises(ValueError,match='original production thermal runtime differs'):
                if full_capture_hit:
                    forecasts.validate_serving_capture(first,model,expected_capture_sha256=first['capture_sha256'],check_budget=changing_guard)
                else:weather.verify_bindings(first['weather_conditioning'],guard=changing_guard)
        assert len(checks)>=2 and len(calls)==2
    finally:sys.setprofile(None)


@pytest.mark.parametrize('location',['weather','production'])
def test_loaded_weather_source_location_change_falls_back(tmp_path,originals,monkeypatch,location):
    import household_score_report_reuse as reuse,native_thermal_score as scores,thermal_weather_source as weather,production_thermal_source as production
    from thermal_model.replay_budget import capture_source_reads
    forecasts,model,first,_,at=weather_captures(tmp_path,originals,monkeypatch)
    foreign=copied_weather_runtime(tmp_path)
    calls,profile=count_weather();sys.setprofile(profile)
    try:
        with reuse._model_reads(scores,at),reuse._capture_reads(lambda:None),capture_source_reads():
            forecasts.validate_serving_capture(first,model,expected_capture_sha256=first['capture_sha256'])
            module=weather if location=='weather' else production
            monkeypatch.setattr(module,'__file__',str(foreign/(module.__name__+'.py')))
            assert forecasts.validate_serving_capture(first,model,expected_capture_sha256=first['capture_sha256'])==first
        assert len(calls)==2,'loaded source-location change retained a full-capture skip'
    finally:sys.setprofile(None)
