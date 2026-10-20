#!/usr/bin/env python3
"""Cold compatibility admission of unchanged, originally fitted local weather.

No acquisition, promotion, provider requests or consumer/source modification.
The v1 serving envelope is preserved; a separate closed proof records original
uniform-row fit reproduction and exact inference closure/parity compatibility.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
import argparse
import ast
import json
import os
import subprocess
import sys
import time

from household.codec import canonical, identity, loads
from household.control_contracts import instant
from household.thermal_weather_conditioning import capsule, validate_admission, KINDS
from household_native_training import directory, save, daily_lock
from thermal_weather_source import RUNTIME_SOURCES, SELECTION_FIELDS, hash_reference
from weather_learning.contracts import digest
from weather_learning.site_calibration import _model
from weather_source_files import _read

SCHEMA = 'earthship-thermal-weather-compatibility-proof/v1'
PROCEDURE = 'original_uniform_row_standardized_ridge_residual_v1'
SCOPE = 'original_residual_and_feature_functions_only'
REPLAY_FILES = ('weather_learning/__init__.py', 'weather_learning/site_calibration.py',
    'weather_learning/contracts.py', 'weather_learning/evidence.py', 'weather_learning/config.py',
    'weather_learning/historical_serving.py', 'weather_learning/irradiance_learning.py')
FUNCTIONS = {'weather_learning/contracts.py': ('canonical','identity','instant','finite','digest'),
    'weather_learning/evidence.py': ('utc',),
    'weather_learning/site_calibration.py': ('_calculate',),
    'weather_learning/historical_serving.py': ('temperature_features',),
    'weather_learning/irradiance_learning.py': ('irradiance_features',)}
BINDINGS = {'weather_learning/contracts.py': {'json':('import','json'), 'math':('import','math'), 're':('import','re'),
    'sha256':('from',0,'hashlib','sha256'), 'datetime':('from',0,'datetime','datetime'),
    'timezone':('from',0,'datetime','timezone')},
    'weather_learning/evidence.py': {'datetime':('from',0,'datetime','datetime'), 'timezone':('from',0,'datetime','timezone')},
    'weather_learning/site_calibration.py': {'finite':('from',1,'contracts','finite'),
        'fsum':('from',0,'math','fsum'), 'isfinite':('from',0,'math','isfinite')},
    'weather_learning/historical_serving.py': {**{n:('from',0,'math',n) for n in ('sin','cos','pi','exp')},
        'ZoneInfo':('from',0,'zoneinfo','ZoneInfo')}}
PROOF_FIELDS = {'schema','scope','created_at','original_admission_sha256','original_admission_file_sha256',
    'original_expires_at','consumer_runtime_manifest','original_source_manifest','inference_contract_sha256',
    'training_procedure','models','replay_environment','validator_sha256','weighted_refit_performed',
    'physical_calibration_qualified','automatic_actuation','proof_sha256'}
MODEL_PROOF_FIELDS = {'model_sha256','capsule_sha256','training_data_sha256','reproduced_model_sha256',
    'pairs_checked','original_predictions_sha256','consumer_predictions_sha256'}


def _function(tree, name):
    nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name]
    if len(nodes)!=1: raise ValueError('one original inference function required')
    return nodes[0]


def _bindings(tree, name):
    result=[]
    for node in tree.body:
        if isinstance(node,ast.Import):
            result += [('import',a.name) for a in node.names if (a.asname or a.name.split('.')[0])==name]
        elif isinstance(node,ast.ImportFrom):
            result += [('from',node.level,node.module,a.name) for a in node.names if (a.asname or a.name)==name]
        elif isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name==name: result.append(('definition',))
        elif isinstance(node,(ast.Assign,ast.AnnAssign,ast.AugAssign)):
            targets=node.targets if isinstance(node,ast.Assign) else [node.target]
            if any(isinstance(n,ast.Name) and n.id==name for t in targets for n in ast.walk(t)): result.append(('assignment',))
    return result


def _contract(sources):
    """Exact function bodies plus the actual globals they resolve, not AST alone."""
    result={}
    builtins=('min','max','all','any','isinstance','len','sorted','zip','dict','list','set','str','float','int','tuple','ValueError')
    for name,functions in FUNCTIONS.items():
        tree=ast.parse(sources[name].decode())
        for builtin in builtins:
            if _bindings(tree,builtin): raise ValueError('shadowed inference builtin refused')
        for symbol,binding in BINDINGS.get(name,{}).items():
            if _bindings(tree,symbol)!=[binding]: raise ValueError('inference dependency binding differs')
        result[name]=dict(functions={fn:sha256(ast.dump(_function(tree,fn),include_attributes=False).encode()).hexdigest() for fn in functions},
            bindings=BINDINGS.get(name,{}))
    return identity(result)


def _source(root, name):
    if not isinstance(name,str) or Path(name).is_absolute() or '..' in Path(name).parts:
        raise ValueError('relative declared source required')
    return _read(root/'openhab/scripts'/name,262144,source=True)


def _root(path):
    path=Path(path)
    if not path.is_absolute() or path.resolve()!=path or not path.is_dir():
        raise ValueError('explicit resolved source root required')
    return path


def _runtime(root, guard=lambda:None):
    raw=_source(root,'thermal_weather_source.py');tree=ast.parse(raw.decode())
    values=[ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='RUNTIME_SOURCES' for t in n.targets)]
    if values!=[RUNTIME_SOURCES]: raise ValueError('supported original consumer source closure required')
    result={}
    for name in RUNTIME_SOURCES:
        guard();result[name]=sha256(_source(root,name)).hexdigest()
    return result


def _selection(path, now):
    raw=_read(path,16384);selected=loads(raw)
    if (set(selected)!=SELECTION_FIELDS or selected['schema']!='earthship-thermal-weather-selection/v1' or
            selected['automatic_actuation'] is not False or selected['selection_sha256']!=identity({k:v for k,v in selected.items() if k!='selection_sha256'}) or
            instant(selected['available_at'])>now): raise ValueError('original available selection required')
    admission_path=Path(selected['admission_path']);body=_read(admission_path,32768)
    if sha256(body).hexdigest()!=selected['admission_file_sha256']: raise ValueError('original admission bytes differ')
    admission=loads(body);validate_admission(admission,issue=now)
    if instant(admission['admitted_at'])>instant(selected['available_at']): raise ValueError('original admission chronology differs')
    return raw,admission_path,body,admission


def _optional(path):
    try: return _read(path,16384)
    except FileNotFoundError: return None


def _document(path, maximum, field):
    raw=_read(path,maximum);value=loads(raw)
    if value.get(field)!=identity({k:v for k,v in value.items() if k!=field}): raise ValueError('original document identity differs')
    return value


def _pairs(root, pin, references, guard):
    path=root/(pin+'.dataset.json')
    if str(path) not in references: raise ValueError('retained original dataset reference required')
    value=_document(path,1048576,'dataset_sha256')
    if value['dataset_sha256']!=pin or not 1<=len(value['chunks'])<=128: raise ValueError('bounded original dataset required')
    import gzip
    rows=[];total=0
    for chunk in value['chunks']:
        guard();p=root/(chunk['sha256']+'.pairs.json.gz')
        if str(p) not in references: raise ValueError('retained original pair reference required')
        with gzip.open(p,'rb') as stream: raw=stream.read(32*1024**2+1)
        total+=len(raw)
        if len(raw)>32*1024**2 or total>64*1024**2: raise ValueError('bounded original pair data required')
        part=loads(raw)
        if (part.get('chunk_sha256')!=chunk['sha256'] or part['chunk_sha256']!=identity({k:v for k,v in part.items() if k!='chunk_sha256'}) or
                len(part['pairs'])!=chunk['pair_count']): raise ValueError('original pair chunk differs')
        rows.extend(part['pairs'])
        if len(rows)>50000: raise ValueError('bounded original fit pairs required')
    if len(rows)!=value['pair_count']: raise ValueError('complete original fit data required')
    return rows


# A fresh isolated interpreter executes only the pinned original numerical
# function closure; neither producer module imports nor provider code execute.
WORKER = r'''
import ast,json,math,sys,hashlib,re
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
from types import SimpleNamespace
import numpy as np
p=json.load(sys.stdin)
def namespace(sources,original=False):
 env=dict(datetime=datetime,timedelta=timedelta,timezone=timezone,ZoneInfo=ZoneInfo,json=json,math=math,re=re,sha256=hashlib.sha256,
     fsum=math.fsum,sqrt=math.sqrt,isfinite=math.isfinite,sin=math.sin,cos=math.cos,pi=math.pi,exp=math.exp)
 for name,names in p['functions'].items():
  tree=ast.parse(sources[name])
  selected=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
  if original and name.endswith('/site_calibration.py'):
   for n in tree.body:
    if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in ('PAIR_FIELDS','MODEL_FIELDS','SCHEMA') for t in n.targets):
     for t in n.targets:
      if isinstance(t,ast.Name):env[t.id]=ast.literal_eval(n.value)
   selected += [n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('_pair','_model','fit_residual')]
  exec(compile(ast.Module(body=selected,type_ignores=[]),'<retained numerical closure>','exec'),env)
 return env
try:
 old=namespace(p['original'],True);new=namespace(p['consumer']);result={}
 for kind,entry in p['models'].items():
  model=entry['model'];rows=entry['pairs']
  replay=old['fit_residual'](rows,kind=kind,cutoff=datetime.fromisoformat(model['cutoff']),trained_at=datetime.fromisoformat(model['trained_at']),correction_limit=model['correction_limit'],ridge=model['ridge'],timezone_name=model['timezone'])
  if old['canonical'](replay)!=old['canonical'](model):raise ValueError('original fitter does not reproduce model')
  hashes=[hashlib.sha256(),hashlib.sha256()]
  for row in rows:
   values=[]
   for env in (old,new):
    prediction=env['_calculate'](model,row['features'],row['baseline'])
    if kind=='outdoor_temperature_c':
     features=[env['temperature_features'](SimpleNamespace(target_at=datetime.fromisoformat(row['target_at']),mean_c=row['baseline']),origin=datetime.fromisoformat(row['origin']),origin_bias_c=b,timezone_name=model['timezone']) for b in (-2.,0.,2.)]
    else:
     f=row['features'];position=dict(elevation_degrees=f['elevation_degrees'],azimuth_degrees=f['azimuth_degrees'],horizon_elevation_degrees=f['elevation_degrees']-f['horizon_margin_degrees'])
     features=env['irradiance_features'](row['baseline'],lead_hours=row['lead_hours'],target=datetime.fromisoformat(row['target_at']),position=position)
    values.append(env['canonical'](dict(pair_sha256=row['pair_sha256'],prediction=prediction,features=features)))
   if values[0]!=values[1]:raise ValueError('inference parity differs')
   for h,v in zip(hashes,values):h.update(v)
  result[kind]=dict(model_sha256=model['model_sha256'],capsule_sha256=entry['capsule_sha256'],training_data_sha256=model['training_data_sha256'],reproduced_model_sha256=replay['model_sha256'],pairs_checked=len(rows),original_predictions_sha256=hashes[0].hexdigest(),consumer_predictions_sha256=hashes[1].hexdigest())
 print(json.dumps(dict(models=result,environment=dict(python=sys.version.split()[0],numpy=np.__version__)),sort_keys=True,separators=(',',':')))
except Exception:
 sys.stderr.write('Original fit reproduction or inference parity refused.\n');sys.exit(1)
'''


def _replay(original, consumer, models, *, remaining):
    payload=canonical(dict(original={k:v.decode() for k,v in original.items()},consumer={k:v.decode() for k,v in consumer.items()},
        functions=FUNCTIONS,models=models))
    if len(payload)>128*1024**2: raise ValueError('bounded original replay input required')
    env=dict(os.environ);env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
    result=subprocess.run([sys.executable,'-I','-B','-c',WORKER],input=payload,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        timeout=remaining(),env=env,check=False)
    if result.returncode or len(result.stdout)>16384: raise ValueError('original fit reproduction or inference parity refused')
    return loads(result.stdout)


def validate_proof(proof, *, original, runtime):
    if (not isinstance(proof,dict) or set(proof)!=PROOF_FIELDS or proof['schema']!=SCHEMA or proof['scope']!=SCOPE or
            proof['proof_sha256']!=identity({k:v for k,v in proof.items() if k!='proof_sha256'}) or
            proof['original_admission_sha256']!=original['admission_sha256'] or proof['original_expires_at']!=original['expires_at'] or
            proof['consumer_runtime_manifest']!=runtime or proof['training_procedure']!=PROCEDURE or set(proof['models'])!=KINDS or
            any(proof[k] is not False for k in ('weighted_refit_performed','physical_calibration_qualified','automatic_actuation'))):
        raise ValueError('closed original compatibility proof required')
    for pin in ('original_admission_file_sha256','inference_contract_sha256','validator_sha256'):digest(proof[pin])
    if set(proof['original_source_manifest'])!=set(REPLAY_FILES): raise ValueError('complete original numerical source manifest required')
    if not instant(original['admitted_at'])<=instant(proof['created_at'])<instant(original['expires_at']):
        raise ValueError('original compatibility proof chronology required')
    for pin in proof['original_source_manifest'].values():digest(pin)
    if set(proof['replay_environment'])!={'python','numpy'} or any(not isinstance(v,str) or not 1<=len(v)<=64 for v in proof['replay_environment'].values()):
        raise ValueError('explicit bounded replay environment required')
    for kind,value in proof['models'].items():
        model=original['models'][kind]
        if (set(value)!=MODEL_PROOF_FIELDS or value['model_sha256']!=model['model_sha256'] or
                value['capsule_sha256']!=model['capsule_sha256'] or value['training_data_sha256']!=model['training_data_sha256'] or
                value['reproduced_model_sha256']!=model['model_sha256'] or type(value['pairs_checked']) is not int or not 1<=value['pairs_checked']<=50000 or
                value['original_predictions_sha256']!=value['consumer_predictions_sha256']):raise ValueError('original model reproduction/parity proof required')
        for key in MODEL_PROOF_FIELDS-{'pairs_checked'}:digest(value[key])
    return proof


def _retain(path, value, maximum):
    raw=canonical(value)
    if len(raw)>maximum:raise ValueError('bounded retained proof required')
    try:fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
    except FileExistsError:
        if _read(path,maximum)!=raw:raise ValueError('immutable retained proof differs')
    else:
        with os.fdopen(fd,'wb') as stream:
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
    if _read(path,maximum)!=raw:raise ValueError('retained original changed')


def readmit(*, original_selection, original_source_roots, consumer_source_root, output, selection,
            clock=lambda:datetime.now(timezone.utc), guard=lambda:None, maximum_seconds=60):
    if type(maximum_seconds) is not int or not 1<=maximum_seconds<=120:raise ValueError('bounded cold admission deadline required')
    deadline=time.monotonic()+maximum_seconds
    def check():
        guard()
        if time.monotonic()>=deadline:raise TimeoutError('cold admission deadline elapsed')
    def remaining():
        check();return max(.001,deadline-time.monotonic())
    now=clock();check();original_selection=Path(original_selection);selection=Path(selection)
    consumer_source_root=_root(consumer_source_root);runtime=_runtime(consumer_source_root,check)
    raw,old_path,old_raw,old=_selection(original_selection,now)
    target_before=_optional(selection)
    if not 1<=len(original_source_roots)<=4:raise ValueError('bounded explicit original producer allowlist required')
    references={r['path']:r for r in old['originals']}
    if len(references)!=len(old['originals']):raise ValueError('unique original references required')
    for ref in references.values():hash_reference(ref,guard=check)
    # Idempotency is a read-only validity check; it never renews source clocks.
    if old['runtime_manifest']==runtime and original_selection==selection:
        check();return dict(status='already_current',admission_sha256=old['admission_sha256'],automatic_actuation=False)
    if target_before is not None and original_selection!=selection:
        try: _,_,_,current=_selection(selection,now)
        except (OSError,ValueError,KeyError,TypeError): current=None
        # An expired/unusable target is opaque compare-before-publish bytes,
        # never a veto on replacing it with this fully validated fresh candidate.
        if (current is not None and current['runtime_manifest']==runtime and current['source_experiments'].get('compatibility_original_admission_sha256')==old['admission_sha256'] and
                all(current[k]==old[k] for k in ('models','expires_at','horizon_profile','source_sensor_epoch'))):
            for ref in current['originals']:hash_reference(ref,guard=check)
            check();return dict(status='already_current',admission_sha256=current['admission_sha256'],automatic_actuation=False)
    producers=[]
    for candidate in original_source_roots:
        check();root=_root(candidate)
        try:
            matching=True
            for name,pin in old['runtime_manifest'].items():
                check()
                if sha256(_source(root,name)).hexdigest()!=pin:
                    matching=False;break
        except (OSError,ValueError):matching=False
        if matching:producers.append(root)
    if not producers:raise ValueError('declared original producer does not match retained admission')
    producer=sorted(producers)[0];old_sources={name:_source(producer,name) for name in REPLAY_FILES}
    new_sources={name:_source(consumer_source_root,name) for name in REPLAY_FILES}
    contract=_contract(old_sources)
    if _contract(new_sources)!=contract:raise ValueError('original inference closure differs from consumer')
    models={};source_manifest={name:sha256(value).hexdigest() for name,value in old_sources.items()}
    experiments={}
    for ref in references.values():
        check();path=Path(ref['path'])
        if path.name=='experiment.json':
            value=_document(path,1048576,'receipt_sha256');experiments[value['receipt_sha256']]=(path.parent,value)
    for kind in sorted(KINDS):
        key='outdoor' if kind=='outdoor_temperature_c' else 'irradiance'
        folder,experiment=experiments[old['source_experiments'][key]]
        for name,pin in source_manifest.items():
            if experiment['runtime_manifest'].get('openhab/scripts/'+name)!=pin:raise ValueError('original fitter/import source closure differs from experiment')
        model_pin=experiment['final_models'][kind] if key=='outdoor' else experiment['final_model_sha256']
        data_pin=experiment['datasets'][kind] if key=='outdoor' else experiment['dataset_sha256']
        found=[]
        for ref in references.values():
            path=Path(ref['path'])
            if path.parent==folder and path.name.endswith('final-model.json'):
                model=_model(loads(_read(path,4194304)))
                if model['model_sha256']==model_pin:found.append(model)
        if len(found)!=1:raise ValueError('one original fitted model required')
        model=found[0]
        if (model['schema']!='earthship-site-calibration/v1' or model['rule']!='standardized_ridge_residual_v1' or
                capsule(model)!=old['models'][kind]):raise ValueError('original uniform-row model/capsule differs')
        models[kind]=dict(model=model,capsule_sha256=old['models'][kind]['capsule_sha256'],pairs=_pairs(folder,data_pin,references,check))
    # The retained profile must be the same original location-bound declaration,
    # not a new horizon silently attached to old fitted procedures.
    horizon=_read(consumer_source_root/'openhab/household-solar-horizon.json',16384,source=True)
    horizons=[r for r in references.values() if Path(r['path']).name=='household-solar-horizon.json']
    if len(horizons)!=1 or sha256(horizon).hexdigest()!=horizons[0]['sha256'] or loads(horizon)['profile']!=old['horizon_profile']:
        raise ValueError('original terrain declaration differs from consumer')
    check();result=_replay(old_sources,new_sources,models,remaining=remaining);check()
    proof=dict(schema=SCHEMA,scope=SCOPE,created_at=now.isoformat(),original_admission_sha256=old['admission_sha256'],
        original_admission_file_sha256=sha256(old_raw).hexdigest(),original_expires_at=old['expires_at'],
        consumer_runtime_manifest=runtime,original_source_manifest=source_manifest,inference_contract_sha256=contract,
        training_procedure=PROCEDURE,models=result['models'],replay_environment=result['environment'],
        validator_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),weighted_refit_performed=False,
        physical_calibration_qualified=False,automatic_actuation=False)
    proof['proof_sha256']=identity(proof);validate_proof(proof,original=old,runtime=runtime)
    def unchanged():
        check()
        if _read(original_selection,16384)!=raw or _optional(selection)!=target_before or _read(old_path,32768)!=old_raw:
            raise ValueError('selected original changed during cold admission')
        if _runtime(consumer_source_root,check)!=runtime:raise ValueError('consumer runtime changed during cold admission')
        for ref in references.values():hash_reference(ref,guard=check)
        for name,pin in {**old['runtime_manifest'],**source_manifest}.items():
            check()
            if sha256(_source(producer,name)).hexdigest()!=pin:raise ValueError('original numerical source changed')
        for name,source_bytes in new_sources.items():
            check()
            if _source(consumer_source_root,name)!=source_bytes:raise ValueError('consumer inference source changed')
        if _read(consumer_source_root/'openhab/household-solar-horizon.json',16384,source=True)!=horizon:
            raise ValueError('consumer terrain declaration changed')
    unchanged();output=directory(output)
    with daily_lock(output/'readmit.lock'):
        unchanged();proof_path=output/(proof['proof_sha256']+'.thermal-weather-compatibility-v1.json');_retain(proof_path,proof,16384)
        new=deepcopy(old);new['admitted_at']=now.isoformat();new['runtime_manifest']=runtime
        new['source_experiments'].update(compatibility_proof_schema=SCHEMA,compatibility_proof_sha256=proof['proof_sha256'],
            compatibility_original_admission_sha256=old['admission_sha256'],training_procedure=PROCEDURE,
            weighted_refit_performed=False,consumer_runtime_manifest_sha256=identity(runtime))
        refs=dict(references)
        def reference(path,maximum,source):
            raw_file=_read(path,maximum,source=source);refs[str(path)]=dict(path=str(path),sha256=sha256(raw_file).hexdigest(),maximum=maximum,source=source)
        reference(old_path,32768,False);reference(proof_path,16384,False)
        reference(consumer_source_root/'openhab/household-solar-horizon.json',16384,True)
        for root,names in ((producer,set(old['runtime_manifest'])|set(REPLAY_FILES)),(consumer_source_root,set(RUNTIME_SOURCES)|set(REPLAY_FILES))):
            for name in sorted(names):check();reference(root/'openhab/scripts'/name,262144,True)
        new['originals']=list(refs.values());new['admission_sha256']=identity({k:v for k,v in new.items() if k!='admission_sha256'})
        validate_admission(new,issue=now)
        if len(canonical(new))>32768:raise ValueError('bounded compatible serving admission required')
        new_path=directory(output/'admissions')/(new['admission_sha256']+'.json');_retain(new_path,new,32768)
        chosen=dict(schema='earthship-thermal-weather-selection/v1',admission_path=str(new_path),admission_file_sha256=sha256(_read(new_path,32768)).hexdigest(),available_at=clock().isoformat(),automatic_actuation=False)
        chosen['selection_sha256']=identity(chosen)
        # Failed/replayed jobs never restore another writer's selected bytes.
        unchanged();validate_admission(new,issue=clock());directory(selection.parent);save(selection,chosen)
    return dict(status='thermal_weather_readmitted',admission_sha256=new['admission_sha256'],
        compatibility_sha256=proof['proof_sha256'],compatibility_path=str(proof_path),expires_at=new['expires_at'],automatic_actuation=False)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--original-selection',type=Path,required=True)
    p.add_argument('--original-source-root',type=Path,action='append',required=True)
    p.add_argument('--consumer-source-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--selection',type=Path,required=True)
    p.add_argument('--maximum-seconds',type=int,default=60)
    a=p.parse_args(argv);os.umask(0o077)
    from household_cycle_pressure import PublicationHeadroom
    pressure=PublicationHeadroom()
    try:
        print(json.dumps(readmit(original_selection=a.original_selection,original_source_roots=a.original_source_root,
            consumer_source_root=a.consumer_source_root,output=a.output,selection=a.selection,
            maximum_seconds=a.maximum_seconds,guard=pressure.check)));return 0
    except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError):
        print(json.dumps(dict(status='thermal_weather_readmission_refused',automatic_actuation=False)));return 1


if __name__=='__main__':raise SystemExit(main())
