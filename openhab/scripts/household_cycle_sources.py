"""Private configuration and restricted originals for the household cycle."""
from pathlib import Path
import re
from household.codec import loads
from household_observation import _private_file

CONFIG_FIELDS={'schema','forecast_config','retained_energy_parameters','parameters_sha256','evidence_directory','observation_cache'}
PATH_FIELDS={'forecast_config','retained_energy_parameters','evidence_directory','observation_cache'}


def load_cycle_settings(path):
    raw,_=_private_file(Path(path).absolute(),8192)
    value=loads(raw)
    if set(value)!=CONFIG_FIELDS or value['schema']!='earthship-household-cycle-config/v1':
        raise ValueError('closed private household cycle configuration required')
    if not isinstance(value['parameters_sha256'],str) or re.fullmatch('[a-f0-9]{64}',value['parameters_sha256']) is None:
        raise ValueError('original parameter digest required')
    for key in PATH_FIELDS:
        text=value[key]
        if not isinstance(text,str) or not 1<=len(text)<=4096:
            raise ValueError('bounded original path required')
        original=Path(text)
        if not original.is_absolute() or original.resolve()!=original:
            raise ValueError('fixed resolved original path required')
    if value['forecast_config']==value['observation_cache'] or value['retained_energy_parameters']==value['observation_cache']:
        raise ValueError('source cannot be a publication target')
    return value
