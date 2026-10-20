#!/usr/bin/env python3
"""Run the current score kernel against a matching retained forecast producer."""
from pathlib import Path
from hashlib import sha256
from datetime import datetime
from uuid import uuid4
import argparse,json,os,stat,subprocess,sys,time


def select_source_root(forecast,roots):
    manifest=forecast['runtime_manifest'];required={k:v for k,v in manifest.items() if k.startswith(('openhab/','scripts/'))}
    if 'openhab/scripts/household_calibrated_energy.py' not in required:raise ValueError('original calibrated producer manifest required')
    for selected in roots:
        root=Path(selected)
        try:
            info=root.lstat()
            if not root.is_absolute() or root.resolve()!=root or not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o022:continue
            matched=True
            for name,digest in required.items():
                if '..' in Path(name).parts:raise ValueError('resolved producer source required')
                path=root/name;info=path.lstat()
                if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o022 or info.st_size>2*1024**2 or path.resolve()!=path or sha256(path.read_bytes()).hexdigest()!=digest:
                    matched=False;break
            if matched:return root
        except FileNotFoundError:continue
    raise ValueError('matching retained numerical producer unavailable')


def require_producer_binding(replay,root):
    actual=Path(replay.__globals__['__file__']).resolve()
    if actual!=Path(root)/'openhab/scripts/household_calibrated_energy.py':raise ValueError('numerical replay bound to a different producer')


def producer_roots():
    from household_observation import _private_file
    result=[];config=Path.home()/'.config/earthship-weather'
    try:
        value=json.loads(_private_file(config/'calibrated-producers.json',32768)[0])
        if set(value)!={'schema','roots'} or value['schema']!='earthship-calibrated-producers/v1' or not isinstance(value['roots'],list) or len(value['roots'])>32:raise ValueError('bounded explicit producer registry required')
        result.extend(value['roots'])
    except FileNotFoundError:pass
    try:
        text=_private_file(config/'calibrated-energy.env',16384)[0].decode()
        for line in text.splitlines():
            key,sep,value=line.partition('=')
            if key=='EARTHSHIP_CALIBRATED_ENERGY_ROOT':result.append(value.strip().strip('\"\''))
    except FileNotFoundError:pass
    result.append(str(Path(__file__).resolve().parents[2]));paths=[]
    for value in result:
        p=Path(value)
        if not p.is_absolute() or p.resolve()!=p:raise ValueError('resolved retained producer root required')
        if p not in paths:paths.append(p)
    return paths


def model_operation(*,producer_root,mode,inputs,state,deadline,guard):
    from household_native_training import save,directory
    from household_observation import _private_file
    state=directory(state);nonce=uuid4().hex;request=state/('.model-request-'+nonce+'.json');result=state/('.model-result-'+nonce+'.json')
    body=dict(inputs)
    if 'assessed_at' in body:body['assessed_at']=body['assessed_at'].isoformat()
    if len(json.dumps(body,allow_nan=False).encode())>16*1024**2:raise ValueError('bounded model operation request required')
    save(request,body);guard();left=deadline-time.monotonic()-5
    if left<1:raise TimeoutError('retained model operation deadline elapsed')
    args=['/usr/bin/python3',str(Path(__file__).resolve()),'--child','--producer-root',str(producer_root),'--outcomes',str(Path(__file__).with_name('household_calibrated_outcomes.py')),'--mode',mode,'--request',str(request),'--result',str(result)]
    completed=subprocess.run(args,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'},capture_output=True,timeout=left)
    if len(completed.stdout)+len(completed.stderr)>32768:raise ValueError('bounded model operation diagnostics required')
    guard()
    if completed.returncode:
        save(state/'last-model-operation-error.json',dict(mode=mode,returncode=completed.returncode,request_path=str(request),diagnostic=completed.stderr.decode(errors='replace')[-8192:]))
        raise ValueError('retained numerical producer operation refused')
    value=json.loads(_private_file(result,5*1024**2)[0]);request.unlink();result.unlink();return value


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--child',action='store_true',required=True)
    for name in ('producer-root','outcomes','request','result'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--mode',choices=('origin','score'),required=True);a=p.parse_args(argv)
    # Insert the producer before any model imports. run_path executes the
    # current outside-model score kernel, whose numerical imports then bind
    # to the original immutable producer. No fitting or action API is called.
    sys.path.insert(0,str(a.producer_root/'openhab/scripts'))
    from household_observation import _private_file
    from household_native_training import save
    import runpy
    data=json.loads(_private_file(a.request,16*1024**2)[0]);select_source_root(data['forecast'],[a.producer_root])
    kernel=runpy.run_path(str(a.outcomes),run_name='earthship_current_calibrated_score')
    require_producer_binding(kernel['replay'],a.producer_root)
    if a.mode=='origin':
        original=kernel['replay'](data['forecast'],energy=data['energy'],plan=data['plan'],profiled=data['profiled'])
        value=kernel['_predictions'](original,data['plan'],data['profiled'])
    else:
        data['assessed_at']=datetime.fromisoformat(data['assessed_at']);value=kernel['seal_outcomes'](**data)
    save(a.result,value);return 0

if __name__=='__main__':raise SystemExit(main())
