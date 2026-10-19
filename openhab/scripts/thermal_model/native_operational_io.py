"""Native issue/receipt/file helpers, independent of standalone publishers."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
from time import sleep
import os,stat
from .forcing_capture import _private_directory
from .graduation_policy import _utc
from .origin_capture import build_runtime_binding
from .installed_shade_live_inputs import TelemetryTransport

RUNTIME_ROOT=Path(__file__).resolve().parents[1]
# Preserve the existing model source closure while legacy entry points are
# retired separately. Listing a source does not import or execute its publisher.
RUNTIME_PATHS=frozenset({
    'hourly_temperature_runtime.py',
    'openhab_runtime_io.py',
    'thermal_installed_intel.py',
    'thermal_intel.py',
    'thermal_model/__init__.py',
    'thermal_model/action_history.py',
    'thermal_model/actions.py',
    'thermal_model/airflow_migration.py',
    'thermal_model/artifacts.py',
    'thermal_model/behavior.py',
    'thermal_model/capture_guard.py',
    'thermal_model/capture_readers.py',
    'thermal_model/dataset.py',
    'thermal_model/dynamics.py',
    'thermal_model/environment_bundle.py',
    'thermal_model/evaluation.py',
    'thermal_model/fit_evidence.py',
    'thermal_model/forcing_capture.py',
    'thermal_model/forecast_history.py',
    'thermal_model/graduation_decision.py',
    'thermal_model/graduation_evidence.py',
    'thermal_model/graduation_policy.py',
    'thermal_model/graduation_statistics.py',
    'thermal_model/installed_shade_artifact.py',
    'thermal_model/installed_shade_calibrated_artifact.py',
    'thermal_model/installed_shade_calibrated_origin.py',
    'thermal_model/installed_shade_calibration.py',
    'thermal_model/installed_shade_dynamics.py',
    'thermal_model/installed_shade_fit.py',
    'thermal_model/installed_shade_inputs.py',
    'thermal_model/installed_shade_live.py',
    'thermal_model/installed_shade_live_inputs.py',
    'thermal_model/installed_shade_origin.py',
    'thermal_model/installed_shade_publication.py',
    'thermal_model/installed_shade_published_origin.py',
    'thermal_model/installed_shade_qualification.py',
    'thermal_model/installed_shade_raw_score_sources.py',
    'thermal_model/installed_shade_score_collection.py',
    'thermal_model/installed_shade_score_inputs.py',
    'thermal_model/journal.py',
    'thermal_model/native_operational_io.py',
    'thermal_model/offline_training.py',
    'thermal_model/operational_origin.py',
    'thermal_model/origin_capture.py',
    'thermal_model/pipeline.py',
    'thermal_model/policy_registration.py',
    'thermal_model/provisional_artifact.py',
    'thermal_model/provisional_fit.py',
    'thermal_model/provisional_forecast.py',
    'thermal_model/provisional_score.py',
    'thermal_model/recent_cycles.py',
    'thermal_model/release.py',
    'thermal_model/replay_budget.py',
    'thermal_model/rollback.py',
    'thermal_model/runtime_bundle.py',
    'thermal_model/schema.py',
    'thermal_model/serial_publication_caps.py',
    'thermal_model/solar.py',
    'thermal_model/temperature_history.py',
    'thermal_model/training_assembly.py',
    'thermal_model/training_inputs.py',
    'thermal_model/training_pressure_guard.py',
    'thermal_model/training_sources.py',
    'thermal_temperature_runtime.py',
    'weather_learning/__init__.py',
    'weather_learning/archive.py',
    'weather_learning/config.py',
    'weather_learning/contracts.py',
    'weather_learning/evidence.py',
    'weather_learning/features.py',
    'weather_learning/native_backend.py',
    'weather_learning/native_forecast.py',
    'weather_learning/normalize.py',
    'weather_learning/transport.py',
    'weather_learning/weathernext_ee.py',
    'weather_source_files.py',
    'weather_temperature_config.py',
    'weather_temperature_evidence.py',
    'weather_temperature_history.py',
    'weather_temperature_reader.py',
    'weather_temperature_receiver.py',
    'weather_temperature_sources.py',
})


def _clock():return datetime.now(timezone.utc)


def current_runtime():return build_runtime_binding(RUNTIME_ROOT,sorted(RUNTIME_PATHS))


def _phase_directory(root,kind,at):
    parent=_private_directory(Path(root));folder=parent/(kind+'-'+_utc(at).strftime('%Y%m%d'))
    folder.mkdir(mode=0o700,exist_ok=True);return _private_directory(folder)


def delivery_directory(settings,at):return _phase_directory(settings['evidence_directory'],'origins',at)


def _next_issue(now):
    now=_utc(now)
    issue=now.replace(minute=now.minute//5*5,second=15,microsecond=0)
    return issue if now<issue else issue+timedelta(minutes=5)


def _folders(root,prefix,now):
    root=_private_directory(Path(root));result=[]
    for offset in range(3):
        path=root/(prefix+'-'+(_utc(now)-timedelta(days=offset)).strftime('%Y%m%d'))
        if path.exists():result.append(_private_directory(path))
    return result


def _fingerprint(path):
    path=Path(path);info=path.lstat()
    if (not path.is_absolute() or path.resolve()!=path or not stat.S_ISREG(info.st_mode) or
            info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1):
        raise ValueError('owned original monitoring source required')
    return [info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns]


def _persisted_after_write(backend,item,state,*,since,guard,clock=None):
    # JDBC writes are asynchronous. Recheck once with an actual later clock;
    # never substitute an accepted PUT or current state for a persisted receipt.
    for attempt in range(2):
        guard()
        try:
            if isinstance(backend,TelemetryTransport):
                return backend.persisted(item,state,since=since,until=(_clock() if clock is None else clock()),preflight=guard)
            return backend.persisted(item,state,since=since)
        except ValueError as error:
            if str(error)!='one exact actual persisted publication required' or attempt:raise
            sleep(1);guard()
