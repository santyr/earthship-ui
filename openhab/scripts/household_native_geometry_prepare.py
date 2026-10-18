"""Prepare the selected native forecast geometry before the issuance window.

This command computes private observational geometry only. It cannot fit a
model, publish telemetry, select a model or issue a household device command.
"""
from datetime import datetime,timedelta,timezone
from pathlib import Path
import time


def _library_paths(raw):
    from astro_geometry_worker import ROLES
    from household.codec import loads
    value=loads(raw)
    if (set(value)!={'schema','library_paths'} or value['schema']!='earthship-native-geometry-libraries/v1' or
        not isinstance(value['library_paths'],dict) or set(value['library_paths'])!=ROLES):
        raise ValueError('closed native library configuration required')
    result={}
    for role,name in value['library_paths'].items():
        if not isinstance(name,str) or not 1<=len(name)<=1024:
            raise ValueError('bounded original native library path required')
        path=Path(name)
        if not path.is_absolute() or path.resolve()!=path:
            raise ValueError('resolved original native library path required')
        result[role]=path
    return result



class _SourceGuard:
    """Reuse path syntax; read original bytes and permissions on every check."""
    def __init__(self,config,libraries,source):
        from household_observation import _private_file
        from thermal_model.origin_capture import _source_bytes
        self.config=config;self.libraries=libraries;self.source=source
        self.original_config=_private_file(config,8192)
        self.original_libraries=_private_file(libraries,8192)
        self.original_source=_source_bytes(source,maximum=262144)
        # Cache syntax only. Shared ancestors need one fresh check on each
        # side of the complete read, rather than six repeated traversals.
        self.components=tuple(dict.fromkeys(component for path in (config,libraries,source)
            for component in reversed(path.parents)))

    def _directories(self):
        import stat
        result={}
        for component in self.components:
            info=component.lstat()
            if not stat.S_ISDIR(info.st_mode):raise ValueError('native preparation source directory changed')
            result[component]=(info.st_dev,info.st_ino)
        return result

    def _read(self,path,parents,*,source=False):
        import os,stat
        from household_observation import _private_file
        before_parent=parents[path.parent]
        parent_fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            row=os.fstat(parent_fd)
            if (row.st_dev,row.st_ino)!=before_parent:raise ValueError('native preparation source parent changed')
            if not source:
                result=_private_file(Path(path.name),8192,directory_fd=parent_fd)
            else:
                info=path.lstat()
                if (not stat.S_ISREG(info.st_mode) or info.st_uid not in (0,os.getuid()) or
                        info.st_mode&0o022 or info.st_size>262144):
                    raise ValueError('bounded non-writable preparation source required')
                fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=parent_fd)
                try:
                    before=os.fstat(fd)
                    if (before.st_dev,before.st_ino)!=(info.st_dev,info.st_ino):raise ValueError('preparation source changed')
                    with os.fdopen(fd,'rb',closefd=False) as stream:raw=stream.read(262145)
                    after=os.fstat(fd)
                finally:os.close(fd)
                if (len(raw)!=info.st_size or len(raw)>262144 or
                    (before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_size,after.st_mtime_ns,after.st_ctime_ns)):
                    raise ValueError('preparation source changed while reading')
                from thermal_model.replay_budget import observe_source_bytes
                observe_source_bytes(path,raw);result=raw
            return result
        finally:os.close(parent_fd)

    def check(self):
        parents=self._directories()
        if (self._read(self.config,parents)!=self.original_config or self._read(self.libraries,parents)!=self.original_libraries or
                self._read(self.source,parents,source=True)!=self.original_source):
            raise ValueError('native preparation source or configuration changed')
        if self._directories()!=parents:
            raise ValueError('native preparation source directories changed during read')


def run(config,libraries,*,stage=None,deployment_sha256=None,clock=lambda:datetime.now(timezone.utc),monotonic=time.monotonic):
    from contextlib import nullcontext
    from household_cycle_resources import publication_native_policy
    with publication_native_policy() if deployment_sha256 is not None else nullcontext():
        return _run(config,libraries,stage=stage,deployment_sha256=deployment_sha256,clock=clock,monotonic=monotonic)


def _run(config,libraries,*,stage=None,deployment_sha256=None,clock=lambda:datetime.now(timezone.utc),monotonic=time.monotonic):
    from native_thermal_live import load_settings,prepare_geometry,_resource_preflight
    from thermal_model.provisional_live import _next_issue
    from thermal_model.capture_guard import SharedScoreLock
    from native_inference_pressure import NativeInferenceHeadroom
    from thermal_model.origin_capture import _source_bytes
    from household_observation import _private_file
    _resource_preflight()
    config,libraries=map(lambda path:Path(path).absolute(),(config,libraries))
    source=Path(__file__).resolve();originals=_SourceGuard(config,libraries,source)
    settings=load_settings(config);paths=_library_paths(originals.original_libraries[0])
    from native_thermal_live import SERVING_SCHEMAS
    receipt_profile=settings.get('schema') in SERVING_SCHEMAS
    if receipt_profile and (stage is None or deployment_sha256 is None):
        raise ValueError('external receipt-serving preparation selection required')
    now=clock();issue=_next_issue(now)
    if issue-now<timedelta(seconds=120):
        raise BlockingIOError('original forecast preparation window reserved')
    verifier=None;binding=None
    if stage is not None:
        from household_cycle_deploy import verify_stage
        stage=Path(stage).absolute()
        if receipt_profile:
            from thermal_model.graduation_policy import _sha
            _sha(deployment_sha256)
            def verifier(actual):return verify_stage(actual,expected_deployment_sha256=deployment_sha256)
        else:verifier=verify_stage
        binding=verifier(stage)
        if source!=stage/'sources/openhab/scripts/household_native_geometry_prepare.py':
            raise ValueError('staged native preparer execution required')
    with SharedScoreLock(settings['shared_lock']) as lock:
        pressure=NativeInferenceHeadroom();pressure.preflight()
        deadline=monotonic()+75
        def guard():
            lock.verify();pressure.check()
            if monotonic()>=deadline or clock()>=issue-timedelta(seconds=35):
                raise ValueError('native preparation lifetime elapsed')
            originals.check()
        guard()
        if receipt_profile:
            from native_model_serving_receipt import load_serving_selection,read_serving_model
            selected=load_serving_selection(stage,expected_deployment_sha256=deployment_sha256,assessed_at=clock(),guard=guard)
            model=read_serving_model(selected,assessed_at=clock(),guard=guard)
            from household_cycle_resources import publication_geometry_policy
            with publication_geometry_policy():
                result=prepare_geometry(settings,issue=issue,library_paths=paths,guard=guard,serving_model=model)
        else:
            result=prepare_geometry(settings,issue=issue,library_paths=paths,guard=guard)
        guard()
        if verifier is not None and verifier(stage)!=binding:
            raise ValueError('staged native preparation runtime changed')
        guard();return result


def main(argv=None):
    import argparse,json
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True,type=Path)
    parser.add_argument('--libraries',required=True,type=Path)
    parser.add_argument('--stage',type=Path);parser.add_argument('--deployment-sha256')
    args=parser.parse_args(argv)
    try:
        selection={} if args.deployment_sha256 is None else dict(deployment_sha256=args.deployment_sha256)
        result=run(args.config,args.libraries,stage=args.stage,**selection)
    except BlockingIOError:
        print(json.dumps(dict(status='busy',fit_executed=False,automatic_actuation=False)));return 75
    except Exception:
        print(json.dumps(dict(status='geometry_withheld',fit_executed=False,automatic_actuation=False)));return 1
    print(json.dumps(result));return 0 if result.get('status')=='prepared' else 1


if __name__=='__main__':raise SystemExit(main())
