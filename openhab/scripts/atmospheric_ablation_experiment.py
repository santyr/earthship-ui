#!/usr/bin/env python3
"""Bounded retained-original atmospheric experiment. No network or publication."""
import argparse,gzip,json,os,platform,sys,time
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
from weather_source_files import _read
from weather_learning.contracts import canonical,identity
from weather_learning.source_bundle import capture_sources,verify_sources,retain_sources
from weather_learning.atmospheric_retained import build_retained_rows
from weather_learning.atmospheric_ablation import assess_ablation


def offline_audit(state):
    state['blocked_attempts']={}
    def hook(event,arguments):
        if event in ('socket.connect','subprocess.Popen','os.system','os.posix_spawn','os.fork','os.forkpty') or event.startswith('os.exec'):
            state['blocked_attempts'][event]=state['blocked_attempts'].get(event,0)+1
            raise RuntimeError('retained experiment cannot connect or launch processes')
    return hook


def run(*,base,temperature_parent,wind_parent,thermal_parent,output,root,audit_state):
    began=time.monotonic();now=datetime.now(timezone.utc);pins={};runtime=capture_sources(root)
    def guard():
        if time.monotonic()-began>120:raise TimeoutError('frozen atmospheric experiment120second deadline elapsed')
    def read(path,maximum,source=False):
        guard();path=Path(path);raw=_read(path,maximum,source=source);pin=sha256(raw).hexdigest()
        if str(path) in pins and pins[str(path)]['sha256']!=pin:raise ValueError('original input changed during experiment')
        pins[str(path)]=dict(sha256=pin,maximum=maximum,source=source);return raw
    def progress(**record):print(json.dumps(dict(record,seconds=round(time.monotonic()-began,3))),flush=True)
    docs=root/'docs/operations/weathernext3-capabilities'
    protocol_raw=read(docs/'evaluation-protocol.json',65536,source=True);protocol=json.loads(protocol_raw)
    policy=json.loads(read(docs/'atmospheric-ablation-protocol.json',65536,source=True))
    if policy['general_protocol_sha256']!=sha256(protocol_raw).hexdigest():raise ValueError('frozen general evaluation protocol differs')
    data=build_retained_rows(base=base,temperature_parent=temperature_parent,wind_parent=wind_parent,thermal_parent=thermal_parent,root=root,
        assessed_at=now,read=read,guard=guard,progress=progress)
    progress(phase='chronological_fitting',pairs=len(data['rows']))
    report=assess_ablation(data['rows'],policy=policy,protocol=protocol,timezone_name=data['timezone'],guard=guard,cohort_contexts=data['cohort_contexts'])
    progress(phase='assessment_complete',cohorts=len(report['cohorts']),models=len(report['models']))
    guard();verify_sources(root,runtime)
    for name,ref in pins.items():
        guard()
        if sha256(_read(Path(name),ref['maximum'],source=ref['source'])).hexdigest()!=ref['sha256']:raise ValueError('original source changed during experiment')
    source_manifest={name:sha256(raw).hexdigest() for name,raw in runtime.items()};source_pin=identity(source_manifest)
    import numpy,scipy,numpy.linalg._umath_linalg,numpy._core._multiarray_umath
    binary_paths=[Path(sys.executable).resolve(),Path(numpy.linalg._umath_linalg.__file__),Path(numpy._core._multiarray_umath.__file__)]
    environment=dict(python=platform.python_version(),numpy=numpy.__version__,scipy=scipy.__version__,numerical_binary_sha256s={p.name:sha256(p.read_bytes()).hexdigest() for p in binary_paths})
    if audit_state['blocked_attempts']:raise RuntimeError('offline experiment attempted a forbidden operation')
    guard();output.mkdir(parents=True,exist_ok=True,mode=0o700);package=output/('sources-'+source_pin)
    if package.exists():
        if any(sha256(_read(package/'sources'/name,1024**2)).hexdigest()!=pin for name,pin in source_manifest.items()):raise ValueError('retained experiment source package differs')
    else:retain_sources(package,runtime)
    dataset=dict(schema='earthship-retained-atmospheric-ablation-dataset/v1',**data,source_inputs=pins,feature_policy_sha256=identity(policy),protocol_sha256=identity(protocol),automatic_actuation=False)
    dataset['dataset_sha256']=identity(dataset);encoded=canonical(dataset)
    if len(encoded)>64*1024**2:raise ValueError('bounded retained atmospheric dataset required')
    def immutable(path,raw):
        try:fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        except FileExistsError:
            if _read(path,64*1024**2)!=raw:raise ValueError('retained experiment artifact collision')
        else:
            with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    immutable(output/(dataset['dataset_sha256']+'.pairs.json.gz'),gzip.compress(encoded,compresslevel=3,mtime=0))
    result=dict(schema='earthship-retained-atmospheric-ablation-experiment/v1',assessed_at=now.isoformat(),dataset_sha256=dataset['dataset_sha256'],parents=data['parents'],parent_counts=data['parent_counts'],
        feature_policy_sha256=identity(policy),protocol_sha256=identity(protocol),source_package_sha256=source_pin,source_runtime=source_manifest,environment=environment,
        original_files=len(pins),forecast_originals=len(data['weather_originals']),excluded=data['excluded'],report=report,duration_seconds=time.monotonic()-began,
        network_access=False,child_processes=False,blocked_operation_attempts=dict(audit_state['blocked_attempts']),production_changed=False,prospective_score=False,physical_calibration_qualified=False,release_authorized=False,automatic_actuation=False)
    result['experiment_sha256']=identity(result);raw=canonical(result)
    if len(raw)>64*1024**2:raise ValueError('bounded atmospheric assessment artifact required')
    immutable(output/(result['experiment_sha256']+'.experiment.json'),raw);guard()
    return dict(status='retained_atmospheric_experiment_complete',experiment_sha256=result['experiment_sha256'],dataset_sha256=dataset['dataset_sha256'],
        duration_seconds=result['duration_seconds'],pairs=len(data['rows']),cohorts=len(report['cohorts']),models=len(report['models']),excluded=len(data['excluded']),production_changed=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('base','temperature-parent','wind-parent','thermal-parent','output'):parser.add_argument('--'+name,required=True,type=Path)
    args=parser.parse_args();os.umask(0o077)
    audit_state={};sys.addaudithook(offline_audit(audit_state))
    result=run(base=args.base,temperature_parent=args.temperature_parent,wind_parent=args.wind_parent,thermal_parent=args.thermal_parent,output=args.output,
        root=Path(__file__).resolve().parents[2],audit_state=audit_state);print(json.dumps(result),flush=True);return 0

if __name__=='__main__':raise SystemExit(main())
