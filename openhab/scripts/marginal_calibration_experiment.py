#!/usr/bin/env python3
"""Bounded offline marginal population capture and one-cohort evaluation."""
import argparse,gzip,json,os,platform,sys,time
from pathlib import Path
from datetime import datetime,timezone
from dataclasses import asdict
from hashlib import sha256
from weather_source_files import _read
from weather_learning.contracts import canonical,identity,digest
from weather_learning.source_bundle import capture_sources,verify_sources,retain_sources
from weather_learning.probabilistic_retained import build_population,restore_population
from weather_learning.probabilistic_evaluation import assess_marginals
from atmospheric_ablation_experiment import offline_audit


def immutable(path,raw):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    try:fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    except FileExistsError:
        if _read(path,64*1024**2)!=raw:raise ValueError('original marginal experiment artifact collision')
    else:
        with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    descriptor=os.open(path.parent,os.O_DIRECTORY|os.O_RDONLY)
    try:os.fsync(descriptor)
    finally:os.close(descriptor)


def retain_original(output,pin,raw):
    digest(pin)
    if sha256(raw).hexdigest()!=pin:raise ValueError('original retained bytes differ from digest')
    encoded=gzip.compress(raw,compresslevel=3,mtime=0);path=Path(output)/'originals'/(pin+'.bin.gz')
    immutable(path,encoded)
    if gzip.decompress(_read(path,64*1024**2))!=raw:raise ValueError('original compressed byte readback differs')
    # Migrate only our unpublished partial raw-copy attempt, after lossless
    # preservation. Never touch the source archive or an original selector.
    prior=Path(output)/'originals'/(pin+'.bin')
    if prior.exists():
        if _read(prior,64*1024**2)!=raw:raise ValueError('partial original raw copy differs')
        prior.unlink()
    return len(encoded)


def run(args,*,root,audit_state):
    began=time.monotonic();now=datetime.now(timezone.utc);pins={};runtime=capture_sources(root);output=Path(args.output)
    def guard():
        if time.monotonic()-began>120:raise TimeoutError('frozen marginal experiment120second deadline elapsed')
    def read(path,maximum,source=False):
        guard();path=Path(path);raw=_read(path,maximum,source=source);pin=sha256(raw).hexdigest()
        if str(path) in pins and pins[str(path)]['sha256']!=pin:raise ValueError('marginal original input changed during experiment')
        pins[str(path)]=dict(sha256=pin,maximum=maximum,source=source);return raw
    def progress(**record):print(json.dumps(dict(record,seconds=round(time.monotonic()-began,3))),flush=True)
    docs=root/'docs/operations/weathernext3-capabilities';policy=json.loads(read(docs/'marginal-calibration-protocol.json',65536,source=True))
    general=read(docs/'evaluation-protocol.json',65536,source=True)
    if policy['general_protocol_file_sha256']!=sha256(general).hexdigest():raise ValueError('frozen general marginal protocol changed')
    if args.action=='prepare':
        data=build_population(base=args.base,temperature_parent=args.temperature_parent,wind_parent=args.wind_parent,assessed_at=now,read=read,guard=guard,progress=progress)
        rows=data.pop('pairs');body=dict(schema='earthship-marginal-calibration-population/v1',assessed_at=now.isoformat(),policy_sha256=policy['policy_sha256'],rows=[asdict(p) for p in rows],**data)
        cohorts={}
        for p in rows:
            f=p.forecast;cohorts.setdefault(f.cohort_sha256,dict(kind=f.kind,availability_basis=f.availability_basis,grid_sha256=f.grid_sha256,rows=0))['rows']+=1
        body['cohorts']=cohorts;stage='population'
    else:
        digest(args.cohort);rows,metadata=restore_population(args.population,policy=policy,read=read,guard=guard)
        selected=[r for r in rows if r.forecast.cohort_sha256==args.cohort]
        if not selected or len(selected)>10000:raise ValueError('one existing coherent bounded marginal cohort required')
        progress(phase='cohort_originals_loaded',kind=selected[0].forecast.kind,rows=len(selected))
        report=assess_marginals(selected,policy=policy,guard=guard)
        body=dict(schema='earthship-retained-marginal-experiment/v1',assessed_at=now.isoformat(),population_sha256=metadata['population_sha256'],cohort_sha256=args.cohort,policy_sha256=policy['policy_sha256'],report=report)
        stage='experiment';progress(phase='cohort_assessed',models=len(report['models']),predictions=len(report['predictions']))
    guard();verify_sources(root,runtime)
    total=compressed=0
    if len(pins)>policy['limits']['original_package_objects']:raise ValueError('bounded complete marginal original object count exceeded')
    for name,ref in pins.items():
        guard();raw=_read(Path(name),ref['maximum'],source=ref['source'])
        if sha256(raw).hexdigest()!=ref['sha256']:raise ValueError('marginal original file changed during verification')
        total+=len(raw)
        if total>policy['limits']['original_package_raw_bytes']:raise ValueError('bounded complete marginal raw original package exceeded')
        compressed+=retain_original(output,ref['sha256'],raw)
        if compressed>policy['limits']['original_package_compressed_bytes']:raise ValueError('bounded complete marginal compressed original package exceeded')
    manifest={name:sha256(raw).hexdigest() for name,raw in runtime.items()};source_pin=identity(manifest);package=output/('sources-'+source_pin)
    if not package.exists():retain_sources(package,runtime)
    import numpy,scipy,numpy.linalg._umath_linalg,numpy._core._multiarray_umath,scipy.optimize._lbfgsb,scipy.special._ufuncs
    binaries=[Path(sys.executable).resolve(),Path(numpy.linalg._umath_linalg.__file__),Path(numpy._core._multiarray_umath.__file__),Path(scipy.optimize._lbfgsb.__file__),Path(scipy.special._ufuncs.__file__)]
    environment=dict(python=platform.python_version(),numpy=numpy.__version__,scipy=scipy.__version__,numerical_binary_sha256s={p.name:sha256(p.read_bytes()).hexdigest() for p in binaries})
    if audit_state['blocked_attempts']:raise RuntimeError('marginal experiment attempted network or process launch')
    body.update(source_inputs=pins,source_package_sha256=source_pin,source_runtime=manifest,environment=environment,duration_seconds=time.monotonic()-began,
        original_package_raw_bytes=total,original_package_compressed_bytes=compressed,original_package_encoding='lossless_gzip_original_sha256',
        network_access=False,child_processes=False,blocked_operation_attempts=dict(audit_state['blocked_attempts']),production_changed=False,issued=False,local_coverage_qualified=False,probability_claim=False,automatic_actuation=False)
    key=stage+'_sha256';body[key]=identity(body);raw=canonical(body)
    if len(raw)>64*1024**2:raise ValueError('bounded marginal experiment artifact exceeded')
    path=output/(body[key]+('.population.json.gz' if stage=='population' else '.experiment.json'))
    immutable(path,gzip.compress(raw,compresslevel=3,mtime=0) if stage=='population' else raw);guard()
    return dict(status='retained_marginal_'+stage+'_complete',path=str(path),duration_seconds=time.monotonic()-began,original_files=len(pins),source_files=len(manifest),
        **({key:body[key],'rows':len(rows),'cohorts':cohorts} if stage=='population' else {key:body[key],'cohort_sha256':args.cohort,'models':len(report['models']),'predictions':len(report['predictions'])}))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=('prepare','assess'))
    for name in ('base','temperature-parent','wind-parent','population','output'):parser.add_argument('--'+name,type=Path,required=name=='output')
    parser.add_argument('--cohort');args=parser.parse_args()
    if args.action=='prepare' and any(getattr(args,k) is None for k in ('base','temperature_parent','wind_parent')):parser.error('prepare requires base and both explicit original parent paths')
    if args.action=='assess' and (args.population is None or args.cohort is None):parser.error('assess requires original population and cohort digest')
    os.umask(0o077);audit={};sys.addaudithook(offline_audit(audit));print(json.dumps(run(args,root=Path(__file__).resolve().parents[2],audit_state=audit)),flush=True);return 0

if __name__=='__main__':raise SystemExit(main())
