from copy import deepcopy
from datetime import timedelta
import pytest
from test_weather_site_calibration import rows,T
from weather_learning.site_calibration import fit_residual
from weather_learning.contracts import identity


def test_cold_validation_reproduces_original_model_without_renewing_clock():
    from thermal_weather_admit import reproduce
    pairs=rows();original=fit_residual(pairs,kind='outdoor_temperature_c',cutoff=T+timedelta(days=8),trained_at=T+timedelta(days=20),correction_limit=6.)
    before=deepcopy(original)
    assert reproduce(original,pairs)==original['model_sha256']
    assert original==before
    changed=deepcopy(original);changed['intercept']+=.1;changed['model_sha256']=identity({k:v for k,v in changed.items() if k!='model_sha256'})
    with pytest.raises(ValueError,match='reproduce'):reproduce(changed,pairs)


# Exact retained uniform-row numerical fitting function; fixture producer only.
LEGACY_FIT = r'''
def fit_residual(rows,*,kind,cutoff,trained_at,correction_limit,ridge=1.,timezone_name='America/Denver'):
    import numpy as np
    cutoff,trained_at=utc(cutoff),utc(trained_at);zone=ZoneInfo(timezone_name)
    if (not isinstance(rows,list) or len(rows)>50000 or not cutoff<=trained_at or not finite(ridge) or ridge<=0 or
        not finite(correction_limit) or not 0<correction_limit<=100000):raise ValueError('bounded fresh residual fitting context required')
    # Select temporal eligibility before looking at future outcomes.
    selected=[_pair(row) for row in rows if row['kind']==kind and instant(row['target_at'])<cutoff]
    selected.sort(key=lambda r:(r['origin'],r['target_at'],r['pair_sha256']))
    if not selected:raise ValueError('completed earlier training outcomes required')
    if len({r['pair_sha256'] for r in selected})!=len(selected):raise ValueError('unique training pairs required')
    names=sorted(selected[0]['features'])
    if any(sorted(r['features'])!=names for r in selected):raise ValueError('consistent feature contract required')
    x=np.asarray([[r['features'][name] for name in names] for r in selected],dtype=float)
    y=np.asarray([r['outcome']-r['baseline'] for r in selected],dtype=float)
    centers=x.mean(axis=0);scales=x.std(axis=0);scales=np.where(scales>1e-12,scales,1.)
    x=(x-centers)/scales;intercept=float(y.mean())
    coefficients=np.linalg.solve(x.T@x+ridge*np.eye(len(names)),x.T@(y-intercept))
    out=dict(schema='earthship-site-calibration/v1',rule='standardized_ridge_residual_v1',kind=kind,feature_names=names,
        centers=centers.tolist(),scales=scales.tolist(),coefficients=coefficients.tolist(),intercept=intercept,
        correction_limit=float(correction_limit),ridge=float(ridge),cutoff=cutoff.isoformat(),trained_at=trained_at.isoformat(),
        training_start=min(r['target_at'] for r in selected),training_end=max(r['target_at'] for r in selected),sample_count=len(selected),
        origin_days=len({instant(r['origin']).astimezone(zone).date() for r in selected}),timezone=timezone_name,
        training_pair_sha256s=[r['pair_sha256'] for r in selected],forecast_sha256s=sorted({r['forecast_sha256'] for r in selected}),
        training_data_sha256=identity(selected),automatic_actuation=False)
    out['model_sha256']=identity(out);_model(out);return out
'''


def bridge_fixture(tmp_path,monkeypatch):
    import ast,json
    from pathlib import Path
    from hashlib import sha256
    from datetime import datetime,timezone
    from types import SimpleNamespace
    from household_native_training import directory,save
    from household.thermal_weather_conditioning import capsule
    from thermal_weather_source import RUNTIME_SOURCES
    from weather_learning.training_dataset import retain_dataset
    from weather_learning import site_calibration as calibration
    from weather_learning.historical_serving import temperature_features
    from weather_learning.irradiance_learning import irradiance_features
    from test_thermal_weather_conditioning import bound_fixture,ISSUE
    args,_=bound_fixture(tmp_path/'serving',monkeypatch)
    source=Path(__file__).parent;consumer=directory(tmp_path/'consumer');producer=directory(tmp_path/'producer')
    names=set(RUNTIME_SOURCES)|{'weather_learning/__init__.py','weather_learning/config.py','weather_learning/evidence.py'}
    for root in (consumer,producer):
        for name in names:
            path=root/'openhab/scripts'/name;path.parent.mkdir(parents=True,exist_ok=True,mode=0o700);path.write_bytes((source/name).read_bytes());path.chmod(0o600)
        path=root/'openhab/household-solar-horizon.json';path.write_bytes((source.parent/'household-solar-horizon.json').read_bytes());path.chmod(0o600)
    path=producer/'openhab/scripts/weather_learning/site_calibration.py';text=path.read_text();tree=ast.parse(text);node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='fit_residual');text=text.replace(ast.get_source_segment(text,node),LEGACY_FIT.strip());path.write_text(text)
    ns=vars(calibration).copy();exec(LEGACY_FIT,ns)
    pointer=json.loads(args['selection'].read_bytes());old_path=Path(pointer['admission_path']);old=json.loads(old_path.read_bytes());old['models']={};old['originals']=[];old['source_experiments']={'original_fit_reproduced':True}
    manifest={'openhab/scripts/'+name:sha256((producer/'openhab/scripts'/name).read_bytes()).hexdigest() for name in names}
    def retained(path,maximum=4194304,source=False):
        old['originals'].append(dict(path=str(path),sha256=sha256(path.read_bytes()).hexdigest(),maximum=maximum,source=source))
    for kind in ('outdoor_temperature_c','irradiance_w_m2'):
        pairs=[]
        for day in range(3):
            origin=ISSUE-timedelta(days=5-day,hours=1)
            for lead in (1,6,12):
                target=origin+timedelta(hours=lead);base=10.+day if kind=='outdoor_temperature_c' else 400.+day*10
                features=temperature_features(SimpleNamespace(target_at=target,mean_c=base),origin=origin,origin_bias_c=1.,timezone_name='America/Denver') if kind=='outdoor_temperature_c' else irradiance_features(base,lead_hours=lead,target=target,position=dict(elevation_degrees=30.,azimuth_degrees=165.,horizon_elevation_degrees=10.))
                row=dict(schema='earthship-historical-learning-pair/v1',kind=kind,origin=origin.isoformat(),target_at=target.isoformat(),lead_hours=lead,availability_basis='retrospective_assumed_full_cycle_9h',forecast_sha256='b'*64,features=features,baseline=base,outcome=base+(1. if kind=='outdoor_temperature_c' else -20.),label={},origin_labels={},prospective_score=False,automatic_actuation=False);row['pair_sha256']=identity(row);pairs.append(row)
        model=ns['fit_residual'](pairs,kind=kind,cutoff=ISSUE-timedelta(days=1),trained_at=ISSUE-timedelta(hours=3),correction_limit=6. if kind=='outdoor_temperature_c' else 600.)
        folder=directory(tmp_path/kind);data=retain_dataset(folder,metadata={'kind':kind},pairs=pairs)
        model_path=folder/'final-model.json';save(model_path,model)
        experiment=dict(schema='earthship-historical-training-experiment/v1' if kind=='outdoor_temperature_c' else 'earthship-historical-irradiance-training/v1',runtime_manifest=manifest,automatic_actuation=False)
        if kind=='outdoor_temperature_c':experiment.update(final_models={kind:model['model_sha256']},datasets={kind:data['dataset_sha256']})
        else:experiment.update(final_model_sha256=model['model_sha256'],dataset_sha256=data['dataset_sha256'])
        experiment['receipt_sha256']=identity(experiment);save(folder/'experiment.json',experiment)
        old['source_experiments']['outdoor' if kind=='outdoor_temperature_c' else 'irradiance']=experiment['receipt_sha256']
        old['models'][kind]=capsule(model)
        for file in folder.iterdir():retained(file,33554432 if file.suffix=='.gz' else 4194304)
    horizon=producer/'openhab/household-solar-horizon.json';retained(horizon,16384,True);old['horizon_profile']=json.loads(horizon.read_bytes())['profile']
    old['runtime_manifest']={name:sha256((producer/'openhab/scripts'/name).read_bytes()).hexdigest() for name in RUNTIME_SOURCES if name not in ('weather_learning/weights.py','thermal_model/installed_shade_origin.py')}
    old['admission_sha256']=identity({k:v for k,v in old.items() if k!='admission_sha256'});save(old_path,old)
    pointer['admission_file_sha256']=sha256(old_path.read_bytes()).hexdigest();pointer['selection_sha256']=identity({k:v for k,v in pointer.items() if k!='selection_sha256'});save(args['selection'],pointer)
    kwargs=dict(original_selection=args['selection'],original_source_roots=[producer],consumer_source_root=consumer,output=tmp_path/'readmit',selection=args['selection'],clock=lambda:ISSUE-timedelta(minutes=1),guard=lambda:None)
    return args,kwargs,old,producer,consumer


def test_cold_bridge_preserves_models_expiry_and_enables_unchanged_serving_consumer(tmp_path,monkeypatch):
    import json
    from pathlib import Path
    from thermal_weather_source import collect_context,verify_bindings
    import thermal_weather_readmit as api
    args,kwargs,old,producer,consumer=bridge_fixture(tmp_path,monkeypatch)
    kwargs['original_source_roots']=[consumer,producer]
    with pytest.raises(ValueError,match='runtime or sensor'):collect_context(**args)
    result=api.readmit(**kwargs)
    assert result['status']=='thermal_weather_readmitted'
    pointer=json.loads(args['selection'].read_bytes());new=json.loads(Path(pointer['admission_path']).read_bytes())
    assert new['models']==old['models'] and new['expires_at']==old['expires_at']
    assert new['horizon_profile']==old['horizon_profile'] and new['source_sensor_epoch']==old['source_sensor_epoch']
    proof=collect_context(**args);verify_bindings(proof,guard=lambda:None)
    assert proof['admission']['admission_sha256']==result['admission_sha256']
    before=args['selection'].read_bytes()
    assert api.readmit(**kwargs)['status']=='already_current'
    assert args['selection'].read_bytes()==before
    receipt=json.loads(Path(result['compatibility_path']).read_bytes())
    assert receipt['training_procedure']=='original_uniform_row_standardized_ridge_residual_v1'
    assert receipt['automatic_actuation'] is False and receipt['weighted_refit_performed'] is False


@pytest.mark.parametrize('damage',['original_source','consumer_kernel','consumer_binding','model','horizon','pair','selection_drift'])
def test_cold_bridge_refuses_unproved_or_concurrently_changed_inputs(tmp_path,monkeypatch,damage):
    import json
    from pathlib import Path
    from household_native_training import save
    import thermal_weather_readmit as api
    args,kwargs,old,producer,consumer=bridge_fixture(tmp_path,monkeypatch)
    before=args['selection'].read_bytes()
    if damage=='original_source':
        p=producer/'openhab/scripts/weather_learning/site_calibration.py';p.write_bytes(p.read_bytes()+b'\n# changed\n')
    if damage in ('consumer_kernel','consumer_binding'):
        p=consumer/'openhab/scripts/weather_learning/site_calibration.py';text=p.read_text();text=text.replace('return baseline+max','return baseline+1+max') if damage=='consumer_kernel' else text.replace('from math import fsum,isfinite','from math import fsum as unused,isfinite\nfsum=sum');p.write_text(text)
    if damage=='model':
        p=tmp_path/'outdoor_temperature_c/final-model.json';v=json.loads(p.read_bytes());v['intercept']+=1;v['model_sha256']=identity({k:v for k,v in v.items() if k!='model_sha256'});save(p,v)
    if damage=='horizon':
        p=consumer/'openhab/household-solar-horizon.json';v=json.loads(p.read_bytes());v['profile'][0]['elevation_degrees']+=1;save(p,v)
    if damage=='pair':
        p=next((tmp_path/'irradiance_w_m2').glob('*.pairs.json.gz'));p.write_bytes(p.read_bytes()+b'changed')
    if damage=='selection_drift':
        original=api._replay
        def changed(*a,**kw):
            result=original(*a,**kw);args['selection'].write_bytes(before+b' ');return result
        monkeypatch.setattr(api,'_replay',changed)
    with pytest.raises((ValueError,OSError)):api.readmit(**kwargs)
    assert args['selection'].read_bytes()==(before+b' ' if damage=='selection_drift' else before)


def test_cold_bridge_replaces_expired_target_with_fresh_candidate_without_refitting(tmp_path,monkeypatch):
    import json
    from pathlib import Path
    from hashlib import sha256
    from household_native_training import save
    import thermal_weather_readmit as api
    args,kwargs,original,_,_=bridge_fixture(tmp_path,monkeypatch)
    candidate_before=args['selection'].read_bytes();pointer=json.loads(candidate_before)
    expired=deepcopy(original);expired['expires_at']=(kwargs['clock']()-timedelta(seconds=1)).isoformat()
    expired['admission_sha256']=identity({k:v for k,v in expired.items() if k!='admission_sha256'})
    expired_path=tmp_path/'expired-admission.json';save(expired_path,expired)
    target=tmp_path/'global.json';pointer.update(admission_path=str(expired_path),admission_file_sha256=sha256(expired_path.read_bytes()).hexdigest())
    pointer['selection_sha256']=identity({k:v for k,v in pointer.items() if k!='selection_sha256'});save(target,pointer)
    kwargs['selection']=target
    result=api.readmit(**kwargs)
    new=json.loads(Path(json.loads(target.read_bytes())['admission_path']).read_bytes())
    assert new['models']==original['models'] and new['expires_at']==original['expires_at']
    assert args['selection'].read_bytes()==candidate_before
    before=target.read_bytes()
    assert api.readmit(**kwargs)['status']=='already_current'
    assert target.read_bytes()==before


def test_cold_bridge_never_overwrites_an_existing_immutable_proof(tmp_path,monkeypatch):
    from pathlib import Path
    import thermal_weather_readmit as api
    args,kwargs,_,_,_=bridge_fixture(tmp_path,monkeypatch)
    before=args['selection'].read_bytes();result=api.readmit(**kwargs)
    proof=Path(result['compatibility_path']);corrupt=proof.read_bytes()+b' '
    proof.write_bytes(corrupt);args['selection'].write_bytes(before)
    with pytest.raises(ValueError):api.readmit(**kwargs)
    assert args['selection'].read_bytes()==before and proof.read_bytes()==corrupt


def test_cold_bridge_deadline_refuses_before_any_publication(tmp_path,monkeypatch):
    import thermal_weather_readmit as api
    args,kwargs,_,_,_=bridge_fixture(tmp_path,monkeypatch);before=args['selection'].read_bytes()
    tick=[0.];monkeypatch.setattr(api.time,'monotonic',lambda:tick[0])
    kwargs['guard']=lambda:tick.__setitem__(0,2.)
    with pytest.raises(TimeoutError):api.readmit(**kwargs,maximum_seconds=1)
    assert args['selection'].read_bytes()==before and not kwargs['output'].exists()


@pytest.mark.parametrize('damage',['extra_field','weighted_claim','extended_expiry','wrong_reproduction','different_predictions'])
def test_cold_compatibility_proof_is_closed_and_preserves_original_procedure(tmp_path,monkeypatch,damage):
    import json
    from pathlib import Path
    import thermal_weather_readmit as api
    _,kwargs,original,_,_=bridge_fixture(tmp_path,monkeypatch)
    result=api.readmit(**kwargs);proof=json.loads(Path(result['compatibility_path']).read_bytes())
    runtime=deepcopy(proof['consumer_runtime_manifest'])
    if damage=='extra_field':proof['promote_model']=True
    if damage=='weighted_claim':proof['weighted_refit_performed']=True
    if damage=='extended_expiry':proof['original_expires_at']=(kwargs['clock']()+timedelta(days=30)).isoformat()
    if damage=='wrong_reproduction':proof['models']['outdoor_temperature_c']['reproduced_model_sha256']='f'*64
    if damage=='different_predictions':proof['models']['irradiance_w_m2']['consumer_predictions_sha256']='f'*64
    proof['proof_sha256']=identity({k:v for k,v in proof.items() if k!='proof_sha256'})
    with pytest.raises(ValueError):api.validate_proof(proof,original=original,runtime=runtime)


def test_selector_directory_sync_failure_after_publication_keeps_new_selection(tmp_path,monkeypatch):
    import os,stat
    import thermal_weather_readmit as api
    args,kwargs,_,_,_=bridge_fixture(tmp_path,monkeypatch)
    before=args['selection'].read_bytes();original=os.fsync;replace=os.replace;published=[False]
    def record_publish(source,target):
        result=replace(source,target)
        if target==args['selection']:published[0]=True
        return result
    def fail_directory(fd):
        if published[0] and stat.S_ISDIR(os.fstat(fd).st_mode):raise OSError('fixture directory sync failure')
        return original(fd)
    monkeypatch.setattr(os,'replace',record_publish);monkeypatch.setattr(os,'fsync',fail_directory)
    with pytest.raises(OSError,match='directory sync'):api.readmit(**kwargs)
    assert args['selection'].read_bytes()!=before


def test_cold_bridge_syncs_retained_dependencies_before_selecting(tmp_path,monkeypatch):
    import os,stat
    from pathlib import Path
    import thermal_weather_readmit as api
    args,kwargs,_,_,_=bridge_fixture(tmp_path,monkeypatch)
    sync=os.fsync;replace=os.replace;synced=set()
    def record_sync(fd):
        sync(fd)
        if stat.S_ISDIR(os.fstat(fd).st_mode):synced.add(Path(os.readlink('/proc/self/fd/'+str(fd))))
    def publish(source,target):
        if Path(target)==kwargs['selection']:
            assert {kwargs['output'],kwargs['output']/'admissions',kwargs['output'].parent}<=synced
        return replace(source,target)
    monkeypatch.setattr(os,'fsync',record_sync);monkeypatch.setattr(os,'replace',publish)
    result=api.readmit(**kwargs)
    assert result['status']=='thermal_weather_readmitted'


def test_cold_bridge_refuses_selection_if_dependency_directory_sync_fails(tmp_path,monkeypatch):
    import os,stat
    from pathlib import Path
    import thermal_weather_readmit as api
    args,kwargs,_,_,_=bridge_fixture(tmp_path,monkeypatch)
    before=args['selection'].read_bytes();sync=os.fsync
    def fail_dependency(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode) and Path(os.readlink('/proc/self/fd/'+str(fd)))==kwargs['output']:
            raise OSError('fixture dependency directory sync failure')
        return sync(fd)
    monkeypatch.setattr(os,'fsync',fail_dependency)
    with pytest.raises(OSError,match='dependency directory sync'):api.readmit(**kwargs)
    assert args['selection'].read_bytes()==before
