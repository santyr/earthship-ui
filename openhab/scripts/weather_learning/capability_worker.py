"""Explicit optional sidecar publication from the existing archive only.

No remote acquisition, model selection, Item writes or service installation.
Preparation is read-only; --apply retains the issued report and score work.
"""
import argparse,json,time
from datetime import datetime,timezone
from pathlib import Path
from .archive import Archive
from .capability_publish import build_capability_report,retain_capability_report
from .config import Site

def publish_capabilities(archive_path,state_path,*,decision,site,horizons=(24,336),apply=False,guard=lambda:None):
    if type(apply) is not bool:raise ValueError('explicit capability retention flag required')
    root=Path(state_path)
    if not root.is_absolute():raise ValueError('absolute capability state namespace required')
    archive=Archive.open_readonly(archive_path,allow_missing=True)
    guard();value=build_capability_report(archive,decision=decision,site=site,horizons=horizons,guard=guard);guard()
    if apply:retain_capability_report(root,value)
    return dict(status=value['status'],report_sha256=value['report_sha256'],retained=apply,
        temperature_hours=len(value['groups']['temperature']['hours']),
        local_coverage_qualified=False,automatic_actuation=False)

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',required=True)
    parser.add_argument('--state',required=True,help='explicit private shadow namespace, not its parent')
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args(argv)
    deadline=time.monotonic()+30
    def guard():
        if time.monotonic()>=deadline:raise TimeoutError('optional capability publication deadline elapsed')
    try:
        from .openhab import oh_get,I18N_CONFIG_PATH
        site=Site.from_openhab_config(oh_get(I18N_CONFIG_PATH));guard()
        result=publish_capabilities(args.archive,args.state,decision=datetime.now(timezone.utc),site=site,apply=args.apply,guard=guard)
        print(json.dumps(result));return 0
    except Exception as error:
        print(json.dumps(dict(status='unavailable',reason=type(error).__name__,automatic_actuation=False)));return 1

if __name__=='__main__':raise SystemExit(main())
