#!/usr/bin/env python3
"""Read original private qualification inputs; write matching immutable reports."""
import argparse
import json
import os
from pathlib import Path
import stat
import sys
from datetime import datetime,timezone
from uuid import uuid4

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'openhab/scripts'))
from thermal_model.artifacts import _artifact_from_payload
from thermal_model.forcing_capture import _private_directory,_canonical
from thermal_graduation_decision import qualify_candidate,qualify_sensor_candidate,render_qualification_report


def read_input(path,maximum=64000000):
    path=Path(path);_private_directory(path.parent);info=path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or
            stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1 or info.st_size>maximum):
        raise ValueError('owned bounded private qualification input required')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
    try:
        before=os.fstat(fd)
        if (before.st_dev,before.st_ino)!=(info.st_dev,info.st_ino):raise ValueError('qualification input changed')
        with os.fdopen(fd,'rb',closefd=False) as stream:raw=stream.read(maximum+1)
        after=os.fstat(fd)
    finally:os.close(fd)
    if len(raw)!=info.st_size or (before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(
            after.st_size,after.st_mtime_ns,after.st_ctime_ns):raise ValueError('qualification input changed during read')
    def pairs(entries):
        value={}
        for key,item in entries:
            if key in value:raise ValueError('duplicate qualification input key')
            value[key]=item
        return value
    def constant(_):raise ValueError('nonfinite qualification input')
    try:return json.loads(raw,object_pairs_hook=pairs,parse_constant=constant)
    except (UnicodeDecodeError,json.JSONDecodeError):raise ValueError('qualification input JSON invalid') from None


def write_report(directory,report):
    root=_private_directory(Path(directory));stem='qualification-'+report['report_sha256']
    outputs={root/(stem+'.json'):_canonical(report)+b'\n',
             root/(stem+'.md'):render_qualification_report(report).encode()}
    for target,raw in outputs.items():
        temporary=root/('.qualification-'+uuid4().hex+'.tmp')
        fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        try:
            with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
            try:os.link(temporary,target,follow_symlinks=False)
            except FileExistsError:
                existing=target.lstat()
                if (not stat.S_ISREG(existing.st_mode) or existing.st_uid!=os.getuid() or
                        stat.S_IMODE(existing.st_mode)!=0o600 or existing.st_nlink!=1 or target.read_bytes()!=raw):
                    raise ValueError('qualification report identity has different content')
        finally:temporary.unlink(missing_ok=True)
    fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)
    return [str(path) for path in outputs]


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('registration','artifact','fit-evidence','training-sources','runtime-bundle','pairs'):
        parser.add_argument('--'+name,type=Path)
    parser.add_argument('--report-directory',type=Path,required=True)
    parser.add_argument('--receipt-version',type=int,choices=(1,2),default=1)
    args=parser.parse_args(argv)
    try:
        # Optional absent inputs generate explicit failed gates, not a pass.
        artifact=_artifact_from_payload(read_input(args.artifact)) if args.artifact else None
        training=read_input(args.training_sources) if args.training_sources else None
        pairs=read_input(args.pairs) if args.pairs else []
        report=(qualify_sensor_candidate if args.receipt_version==2 else qualify_candidate)(registration_path=args.registration,artifact=artifact,
            fit_evidence_path=args.fit_evidence,training_sources=training,
            runtime_bundle_path=args.runtime_bundle,original_pairs=pairs,now=datetime.now(timezone.utc))
        paths=write_report(args.report_directory,report)
        print(json.dumps(dict(recommended_stage=report['recommended_stage'],
            forecast_qualified=report['forecast_qualified'],advisory_qualified=report['advisory_qualified'],
            report_sha256=report['report_sha256'],reports=paths),sort_keys=True))
        return 0 if report['forecast_qualified'] else 1
    except (OSError,ValueError,TypeError,KeyError,AttributeError):
        print(json.dumps({'status':'refused','reason':'qualification input or report storage unavailable'}),file=sys.stderr)
        return 2


if __name__=='__main__':raise SystemExit(main())
