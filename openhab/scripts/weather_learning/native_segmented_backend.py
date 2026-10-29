"""Explicit successor collector; one original snapshot for all thermal roles."""
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

from .config import Site
from .native_forecast import load_native_forecast
from thermal_model.installed_shade_live_inputs import LiveBackend, SOURCE_PATHS
from thermal_model.forcing_capture import _canonical
from thermal_model.temperature_history import STREAMS, POLICY
from astro_geometry import _instant

SCHEMA='earthship-weathernext-native-segmented-backend/v1'


def make_segmented_native_backend(settings,*,archive,site,shared_lock_guard):
    if (not isinstance(settings,dict) or set(settings)!=SOURCE_PATHS|{'schema','openhab_base','evidence_directory'} or
            settings['schema']!=SCHEMA or not isinstance(site,Site) or not callable(shared_lock_guard)):
        raise ValueError('explicit private shared native backend and held guard required')
    def read(*,issue,available_by,horizon_hours):
        shared_lock_guard()
        result=load_native_forecast(archive,origin=issue,available_by=available_by,horizon_hours=horizon_hours,site=site)
        shared_lock_guard();return result
    return SegmentedSourceLiveBackend(deepcopy(settings),shared_lock_guard=shared_lock_guard,forecast_reader=read)


class SegmentedSourceLiveBackend(LiveBackend):
    source_profile='segmented-v1'

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self._shared_request=None;self._shared_grid=None;self._shared_snapshot={};self._native_source_paths={}

    def verify_unchanged(self):
        from native_thermal_forecast import _segmented_helpers,verify_origin_source_snapshot
        super().verify_unchanged()
        _segmented_helpers()
        verify_origin_source_snapshot(getattr(self,'_shared_snapshot',{}),check_budget=self.budget.remaining)

    def _temperature_grid(self,stream,targets,assessed):
        from hourly_temperature_runtime import read_db_config
        from weather_temperature_config import load_temperature_receiver_configuration
        from psycopg2.extensions import make_dsn
        from thermal_model.capture_readers import bounded_journal_dsn
        from thermal_model.replay_budget import remaining_budget
        from native_thermal_forecast import _segmented_helpers,_source_fingerprints
        self.verify_unchanged();binding,_=_segmented_helpers()
        policies,epochs=load_temperature_receiver_configuration(self.settings['native_policy'])
        contexts={}
        for role,(name,model,sensor) in STREAMS.items():
            if (epochs is None or name not in policies or
                    asdict(policies[name])!=dict(model=model,sensor_id=sensor,**POLICY) or
                    epochs.get(name)!=self.epochs[role]):
                raise ValueError('approved shared native policy or hardware phase changed')
            contexts[role]=dict(stream=name,policy=policies[name],sensor_epoch=epochs[name])
        role=next((role for role,identity in STREAMS.items() if identity[0]==stream),None)
        if role is None:raise ValueError('approved shared native stream required')
        targets=list(map(_instant,deepcopy(targets)));assessed=_instant(assessed)
        key=_canonical(dict(targets=targets,assessed_at=assessed,
            contexts={role:dict(value,policy=asdict(value['policy'])) for role,value in contexts.items()}))
        if self._shared_request is not None and key!=self._shared_request:
            raise ValueError('one frozen shared native request per collection required')
        if self._shared_request is None:
            config=read_db_config(self.settings['native_db_config'])
            def remaining():return remaining_budget(self.budget.remaining())
            source=binding.fetch_shared_temperature_source(lambda:self._connect(bounded_journal_dsn(make_dsn(**config))),
                targets=targets,assessed_at=assessed,contexts=contexts,remaining_timeout=remaining,guard=self.budget.remaining)
            self.verify_unchanged()
            path=binding.write_shared_temperature_source(Path(self.settings['evidence_directory']),source,guard=self.budget.remaining)
            source=binding.read_shared_temperature_source(path.parent,path,guard=self.budget.remaining)
            grid=binding.replay_shared_temperature_source(source,guard=self.budget.remaining)
            files=binding.shared_temperature_source_files(source)
            snapshot=_source_fingerprints(files,check_budget=self.budget.remaining)
            self._shared_request=key;self._shared_grid=grid;self._shared_snapshot=snapshot
            self._native_source_paths={role:str(path) for role in STREAMS}
        self.verify_unchanged()
        return deepcopy(self._shared_grid[role])

    def _collect(self,*,issue,known_at):
        from native_thermal_forecast import _segmented_helpers
        self._shared_request=None;self._shared_grid=None;self._shared_snapshot={};self._native_source_paths={}
        result=super()._collect(issue=issue,known_at=known_at)
        binding,_=_segmented_helpers()
        paths=deepcopy(self._native_source_paths)
        binding.build_segmented_native_origin_binding(result['origin_temperatures'],source_paths=paths,
            issue_at=issue,check_budget=self.budget.remaining)
        self.verify_unchanged()
        return dict(result,native_source_paths=paths)
