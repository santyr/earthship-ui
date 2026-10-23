#!/usr/bin/env python3
"""Bounded offline assessment of retained actual publication refresh policies."""
import argparse,gzip,json,os,platform,sys,time
from collections import Counter
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from hashlib import sha256
from pathlib import Path
from weather_source_files import _read,_directory
from weather_learning.archive import Archive
from weather_learning.config import Site
from weather_learning.contracts import canonical,identity,instant
from weather_learning.features import local_temperature_outcome
from weather_learning.atmospheric_dataset import document,temperature_receipts
from weather_learning.source_bundle import capture_sources,verify_sources,retain_sources
from weather_learning.refresh_scoring import compile_refresh_decision,score_refresh_target,summarize_refresh_scores,CONTRACT_SHA256
from atmospheric_ablation_experiment import offline_audit


class _Archive(Archive):
    def read(self,name):
        self.input_reader(self.objects/(name+'.json'),8*1024**2)
        return super().read(name)


def run(*,publication_directory,archive_path,measurement_root,output,site,root,audit_state):
    began=time.monotonic();now=datetime.now(timezone.utc);root=Path(root);pins={};runtime=capture_sources(root)
    def guard():
        if time.monotonic()-began>120:raise TimeoutError('frozen refresh experiment120second deadline elapsed')
    def read(path,maximum,source=False):
        guard();path=Path(path);raw=_read(path,maximum,source=source);pin=sha256(raw).hexdigest()
        if str(path) in pins and pins[str(path)]['sha256']!=pin:raise ValueError('original refresh input changed')
        pins[str(path)]=dict(sha256=pin,maximum=maximum,source=source);return raw
    def immutable(path,raw):
        try:fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        except FileExistsError:
            if _read(path,64*1024**2)!=raw:raise ValueError('immutable refresh experiment collision')
        else:
            with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    policy_path=root/'docs/operations/weathernext3-capabilities/refresh-evaluation-protocol.json'
    policy_raw=read(policy_path,65536,source=True);policy=json.loads(policy_raw)
    if policy.get('score_contract_sha256')!=CONTRACT_SHA256:raise ValueError('frozen refresh score contract differs')
    publication_directory=Path(publication_directory);measurement_root=Path(measurement_root)
    attempts=sorted(publication_directory.glob('*.publication-attempt-v1.json'))
    result_paths=sorted(publication_directory.glob('*.publication-result-v1.json'))
    if not 1<=len(attempts)<=256 or len(result_paths)>256:raise ValueError('bounded retained publication population required')
    results={}
    for path in result_paths:
        value=json.loads(read(path,512*1024));key=value['attempt_sha256']
        if key in results:raise ValueError('conflicting original publication result')
        results[key]=value
    originals=[]
    for path in attempts:
        value=json.loads(read(path,512*1024));key=value['attempt_sha256']
        if key not in results:raise ValueError('retained original publication result missing')
        originals.append((value,results[key]))
    originals.sort(key=lambda pair:(pair[0]['started_at'],pair[0]['attempt_sha256']))
    index=document(measurement_root/'temperature-index.json','index_sha256',read=read)
    start=min(instant(pair[0]['started_at']) for pair in originals)
    days=[d for d in index['days'] if instant(d['date']+'T00:00:00+00:00')<=now and
        instant(d['date']+'T00:00:00+00:00')+timedelta(days=1)>=start]
    if len(days)>32:raise ValueError('bounded retained measurement-day window required')
    labels,availability=temperature_receipts(measurement_root,days,read=read,guard=guard)
    policies={}
    for day in days:
        grid=document(measurement_root/(day['grid_sha256']+'.temperature-grid.json'),'grid_sha256',read=read)
        pin=identity(grid['policy']['policies']['outdoor'])
        for at,label in zip(grid['targets'],grid['streams']['outdoor']):
            if label is None:continue
            if at in policies and policies[at]!=pin:raise ValueError('conflicting original target observation policy')
            policies[at]=pin
    archive=_Archive.open_readonly(archive_path);archive.input_reader=read
    compiled=[];scores=[];withheld=Counter();previous=None
    for attempt,result in originals:
        guard()
        if result['status']!='PUBLISHED':withheld['not_successfully_published']+=1;continue
        record=compile_refresh_decision(attempt,result,archive=archive,site=site,previous=previous,clock=lambda:now)
        body=record.to_dict();compiled.append(body);previous=record
        for row in body['targets']:
            guard();at=instant(row['target_at'])
            if at+timedelta(minutes=2)>now:withheld['not_mature']+=1;continue
            label=labels.get(row['target_at'],{}).get('outdoor')
            if label is None:withheld['no_retained_qualified_outcome']+=1;continue
            if label.get('receiptVersion')!=2:withheld['legacy_receipt_epoch_not_inferred']+=1;continue
            metadata={k:label[k] for k in ('temperatureF','receivedAt','storedAt','validUntil','streamEpoch','snapshotSha256','receiptVersion','sensorEpoch')}
            for key in ('receivedAt','storedAt','validUntil'):metadata[key]=instant(metadata[key])
            try:
                outcome=local_temperature_outcome(metadata,target_at=at,assessed_at=now,sensor_epoch=label['sensorEpoch'])
                actual=availability[(row['target_at'],'outdoor')]
                outcome=replace(outcome,available_at=max(at,instant(actual)))
                score=score_refresh_target(record,target_at=at,outcome=outcome,observation_policy_sha256=policies[row['target_at']],measurement_quality='qualified_receipt_v2')
            except (ValueError,KeyError,TypeError):withheld['outcome_quality_or_availability_withheld']+=1;continue
            scores.append(score)
            if len(scores)>10000:raise ValueError('frozen refresh10000paired-row limit exceeded')
    report=summarize_refresh_scores(scores);guard();verify_sources(root,runtime)
    for name,ref in pins.items():
        guard()
        if sha256(_read(Path(name),ref['maximum'],source=ref['source'])).hexdigest()!=ref['sha256']:raise ValueError('original refresh input changed after assessment')
    if audit_state['blocked_attempts']:raise RuntimeError('offline refresh experiment attempted a forbidden operation')
    output=Path(output);output.mkdir(mode=0o700,exist_ok=True);output=_directory(output);source_manifest={name:sha256(raw).hexdigest() for name,raw in runtime.items()};source_pin=identity(source_manifest)
    package=output/('sources-'+source_pin)
    if package.exists():
        if any(sha256(_read(package/'sources'/name,1024**2)).hexdigest()!=pin for name,pin in source_manifest.items()):raise ValueError('retained refresh source package differs')
    else:retain_sources(package,runtime)
    # Retain literal source bytes as well as their current external locations.
    original_root=output/'originals';original_root.mkdir(mode=0o700,exist_ok=True)
    for name,ref in pins.items():
        guard();raw=_read(Path(name),ref['maximum'],source=ref['source']);immutable(original_root/ref['sha256'],raw)
    dataset=dict(schema='earthship-retained-refresh-dataset/v1',decisions=compiled,scores=scores,original_inputs=pins,
        sampling=policy['durable_score_sampling'],contract_sha256=CONTRACT_SHA256,automatic_actuation=False)
    dataset['dataset_sha256']=identity(dataset);encoded=canonical(dataset)
    if len(encoded)>64*1024**2:raise ValueError('bounded retained refresh dataset required')
    immutable(output/(dataset['dataset_sha256']+'.dataset.json.gz'),gzip.compress(encoded,compresslevel=3,mtime=0))
    experiment=dict(schema='earthship-retained-refresh-experiment/v1',assessed_at=now.isoformat(),dataset_sha256=dataset['dataset_sha256'],
        protocol_file_sha256=sha256(policy_raw).hexdigest(),contract_sha256=CONTRACT_SHA256,source_package_sha256=source_pin,source_runtime=source_manifest,
        environment=dict(python=platform.python_version(),interpreter_sha256=sha256(Path(sys.executable).read_bytes()).hexdigest()),
        population='all retained publication pairs frozen at experiment start; not all scheduled cycles',retained_attempts=len(attempts),
        successful_decisions=len(compiled),qualified_scores=len(scores),measurement_days=[d['date'] for d in days],withheld=dict(withheld),
        report=report,original_files=len(pins),duration_seconds=time.monotonic()-began,
        network_access=False,child_processes=False,blocked_operation_attempts=dict(audit_state['blocked_attempts']),production_changed=False,
        release_authorized=False,probability_claim=False,automatic_actuation=False)
    experiment['experiment_sha256']=identity(experiment);raw=canonical(experiment)
    if len(raw)>64*1024**2:raise ValueError('bounded refresh report required')
    immutable(output/(experiment['experiment_sha256']+'.experiment.json'),raw);guard()
    return dict(status='retained_refresh_experiment_complete',experiment_sha256=experiment['experiment_sha256'],dataset_sha256=dataset['dataset_sha256'],
        decisions=len(compiled),qualified_scores=len(scores),withheld=dict(withheld),duration_seconds=experiment['duration_seconds'],production_changed=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('publication-directory','archive','measurement-root','output','site-json'):parser.add_argument('--'+name,required=True,type=Path)
    args=parser.parse_args();os.umask(0o077)
    audit={'blocked_attempts':{}};sys.addaudithook(offline_audit(audit))
    site=Site(**json.loads(_read(args.site_json,16384,source=True)))
    result=run(publication_directory=args.publication_directory,archive_path=args.archive,measurement_root=args.measurement_root,
        output=args.output,site=site,root=Path(__file__).resolve().parents[2],audit_state=audit)
    print(json.dumps(result),flush=True);return 0

if __name__=='__main__':raise SystemExit(main())
