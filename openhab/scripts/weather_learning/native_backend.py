"""Explicit Google-only native collector; local observation/journal policies stay.

The release worker supplies its held shared-lock guard and private configuration.
No forecast database credential, provider fallback, model selection or activation
is available here. The inherited telemetry transport retains its fixed Item list.
"""
from copy import deepcopy
from .config import Site
from .native_forecast import load_native_forecast

SCHEMA='earthship-weathernext-native-backend/v1'


def make_native_backend(settings,*,archive,site,shared_lock_guard):
    from thermal_model.installed_shade_live_inputs import CompressedSourceLiveBackend,SOURCE_PATHS
    expected=(SOURCE_PATHS-{'forecast_dsn_file'})|{'schema','openhab_base','evidence_directory'}
    if (not isinstance(settings,dict) or set(settings)!=expected or settings['schema']!=SCHEMA or
            not isinstance(site,Site) or not callable(shared_lock_guard)):
        raise ValueError('explicit private Google native backend and held guard required')
    def read(*,issue,available_by,horizon_hours):
        shared_lock_guard()
        result=load_native_forecast(archive,origin=issue,available_by=available_by,horizon_hours=horizon_hours,site=site)
        shared_lock_guard()
        return result
    return CompressedSourceLiveBackend(deepcopy(settings),shared_lock_guard=shared_lock_guard,forecast_reader=read)


SOURCE_SCHEMA='earthship-weathernext-native-source/v1'


def native_source(value,*,withdraw=False):
    """Closed pinned site/archive selection, without forecast database access."""
    from pathlib import Path
    from thermal_model.forcing_capture import _private_directory
    if (not isinstance(value,dict) or set(value)!={'schema','archive_directory','site'} or
            value['schema']!=SOURCE_SCHEMA or not isinstance(value['site'],dict) or
            set(value['site'])!={'latitude','longitude','timezone'}):
        raise ValueError('closed Google weather source required')
    site=Site(**value['site']);root=Path(value['archive_directory'])
    if not root.is_absolute() or root.resolve()!=root:raise ValueError('resolved Google archive required')
    _private_directory(root.parent)
    if not withdraw:_private_directory(root)
    return root,site
