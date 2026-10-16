"""One configured registry across transports, separate from actuator capabilities."""
import re
from uuid import UUID
from .contract import TYPES, canonical, digest, strict_json

PROFILES = {'dragino_lds02/v1', 'milesight_ws301/v1', 'dragino_ds03a_lb/v1'}
TRANSPORTS = {'lorawan', 'zigbee', 'rtl_sdr', 'wired', 'openhab', 'simulation'}
FIELDS = {'device_id','sensor_id','name','location','zone','device_type','transport','manufacturer',
          'model','capabilities','observation_types','units','decoder','hardware_epoch','radio_verified',
          'state_stale_seconds','communication_stale_seconds','offline_seconds','battery_low_percent',
          'battery_low_volts','enabled','firmware','protocol','calibration','relationships','security_policy','source_verified'}


class Registry:
    def __init__(self, config):
        if (set(config)-{'schema','environment','application_id','devices','gateways'} or not {'schema','environment','application_id','devices'}<=set(config) or
            config['schema'] != 'earthship-sensor-registry/v1' or
            config['environment'] not in ('production','simulation')):
            raise ValueError('versioned registry and explicit environment required')
        if str(UUID(config['application_id'])) != config['application_id']:
            raise ValueError('canonical application UUID required')
        if not isinstance(config['devices'], list) or len(config['devices']) > 256:
            raise ValueError('bounded configurable registry required')
        self.config = strict_json(canonical(config))
        self.config.setdefault('gateways',[])
        gateway_ids=set()
        if not isinstance(self.config['gateways'],list) or len(self.config['gateways'])>16:raise ValueError('bounded configured gateways required')
        for gateway in self.config['gateways']:
            if (set(gateway)!={'gateway_id','name','offline_seconds'} or not re.fullmatch('[0-9a-f]{16}',gateway['gateway_id']) or
                gateway['gateway_id'] in gateway_ids or not isinstance(gateway['name'],str) or not 1<=len(gateway['name'])<=128 or
                type(gateway['offline_seconds']) is not int or not 30<=gateway['offline_seconds']<=86400):
                raise ValueError('explicit unique gateway supervision required')
            gateway_ids.add(gateway['gateway_id'])
        self.sha256 = digest(canonical(config))
        self.devices = {}
        ids = set()
        identities = set()
        for device in self.config['devices']:
            if set(device)-FIELDS:
                raise ValueError('unknown registry field or secret')
            # Optional metadata has neutral defaults; identities/thresholds never do.
            defaults = dict(transport='lorawan', manufacturer=None, model=None,
                capabilities=['contact_state','battery','radio_health'], observation_types=['contact_state'],
                units={'contact_state':'state'}, enabled=True, firmware=None, protocol=None,
                calibration=None, relationships=[], security_policy=None,source_verified=device.get('radio_verified',False))
            for key, value in defaults.items():
                device.setdefault(key, value)
            if set(device) != FIELDS:
                raise ValueError('complete sensor metadata and policy required')
            if (device['transport'] not in TRANSPORTS or
                not isinstance(device['sensor_id'],str) or not re.fullmatch('[a-z][a-z0-9_]{0,47}',device['sensor_id'])):
                raise ValueError('safe stable logical identity and transport required')
            physical = device['device_id']
            if (not isinstance(physical,str) or not 1<=len(physical)<=128 or
                (device['transport']=='lorawan' and not re.fullmatch('[0-9a-f]{16}',physical))):
                raise ValueError('explicit physical identity required')
            identity=(device['transport'],physical)
            if identity in identities or device['sensor_id'] in ids:
                raise ValueError('duplicate logical or physical identity')
            identities.add(identity);ids.add(device['sensor_id'])
            if device['transport']=='lorawan' and device['decoder'] not in PROFILES:
                raise ValueError('documented decoder profile required')
            if type(device['enabled']) is not bool or type(device['radio_verified']) is not bool or type(device['source_verified']) is not bool:
                raise ValueError('explicit boolean commissioning flags required')
            if str(UUID(device['hardware_epoch'])) != device['hardware_epoch'] or UUID(device['hardware_epoch']).int==0:
                raise ValueError('nonzero hardware epoch required')
            for key in ('name','location','zone','device_type'):
                if not isinstance(device[key],str) or not 1<=len(device[key])<=128 or any(ord(c)<32 for c in device[key]):
                    raise ValueError('bounded display metadata required')
            kinds=device['observation_types']
            if (not isinstance(kinds,list) or not kinds or len(kinds)!=len(set(kinds)) or
                any(kind not in TYPES for kind in kinds) or device['units']!={kind:TYPES[kind][0] for kind in kinds}):
                raise ValueError('registered observation types and exact units required')
            if (not isinstance(device['capabilities'],list) or len(device['capabilities'])>32 or
                any(not isinstance(c,str) or not re.fullmatch('[a-z][a-z0-9_]{0,47}',c) for c in device['capabilities']) or
                not set(kinds)<=set(device['capabilities'])):
                raise ValueError('explicit observational capabilities required')
            for key in ('state_stale_seconds','communication_stale_seconds','offline_seconds'):
                if type(device[key]) is not int or not 1<=device[key]<=604800:
                    raise ValueError('explicit bounded supervision threshold required')
            if device['offline_seconds'] < max(device['state_stale_seconds'],device['communication_stale_seconds']):
                raise ValueError('offline threshold must not precede freshness')
            if type(device['battery_low_percent']) is not int or not 0<=device['battery_low_percent']<=100:
                raise ValueError('bounded battery threshold required')
            if type(device['battery_low_volts']) not in (int,float) or not 0<device['battery_low_volts']<=10:
                raise ValueError('bounded battery threshold required')
            for key in ('manufacturer','model','firmware','protocol'):
                if device[key] is not None and (not isinstance(device[key],str) or len(device[key])>128):
                    raise ValueError('bounded device metadata required')
            if device['calibration'] is not None and (not isinstance(device['calibration'],dict) or len(canonical(device['calibration']))>4096):
                raise ValueError('bounded explicit calibration metadata required')
            if not isinstance(device['relationships'],list) or len(device['relationships'])>32:
                raise ValueError('bounded relationships required')
            if device['security_policy'] is not None and device['security_policy'] not in ('observe_only','disabled'):
                raise ValueError('security observations have no control authority')
            self.devices[device['sensor_id']]=device
        self.sha256=digest(canonical(self.config))
        self.by_lorawan={d['device_id']:d for d in self.devices.values() if d['transport']=='lorawan' and d['enabled']}

    @classmethod
    def read(cls,path):
        with open(path,'rb') as source:
            raw=source.read(262145)
        if len(raw)>262144:
            raise ValueError('registry too large')
        return cls(strict_json(raw))
