"""Manufacturer-documented decoders, not radio-qualified firmware claims.

References and deliberately unsupported modes: docs/operations/lorawan-sensors.md.
No device has its bytes silently interpreted using another profile.
"""
from datetime import datetime, timezone


def _point(**updates):
    return dict(contact_state=None, battery={}, tamper=None, observed_at=None,
                historical=False, event_type='status', diagnostics={}, **updates)


def _dragino_record(data, historical=False):
    seconds=int.from_bytes(data[7:11],'big')
    return dict(contact_state='OPEN' if data[0]&1 else 'CLOSED', battery={}, tamper=None,
        observed_at=datetime.fromtimestamp(seconds,timezone.utc).isoformat() if seconds else None,
        historical=historical, event_type='history' if historical else 'heartbeat' if data[0]&4 else 'state_report',
        diagnostics=dict(open_count=int.from_bytes(data[1:4],'big'), last_open_seconds=int.from_bytes(data[4:7],'big'),
                         timeout_alarm=bool(data[0]&2)))


def decode(profile, data, port):
    if not isinstance(data,bytes) or not 1<=len(data)<=242 or type(port) is not int:
        raise ValueError('bounded payload and application port required')
    if profile=='dragino_lds02/v1':
        if port!=10 or len(data)!=10 or data[2]!=1 or data[9]!=0:
            raise ValueError('LDS02 normal contact mode FPort 10 required; EDC is not contact evidence')
        return [dict(contact_state='OPEN' if data[0]&0x80 else 'CLOSED',
            battery={'volts':(int.from_bytes(data[:2],'big')&0x3fff)/1000}, tamper=None,
            observed_at=None,historical=False,event_type='state_report',
            diagnostics={'open_count':int.from_bytes(data[3:6],'big'),'last_open_minutes':int.from_bytes(data[6:9],'big')})]
    if profile=='milesight_ws301/v1':
        if port!=85:
            raise ValueError('WS301 configured application FPort 85 required')
        point=_point();seen=set();offset=0
        sizes={(0xff,0x0b):1,(0xff,0x01):1,(0xff,0x09):2,(0xff,0x0a):2,
               (0xff,0x0f):1,(0xff,0x08):6,(1,0x75):1,(3,0):1,(4,0):1}
        while offset<len(data):
            if offset+2>len(data):
                raise ValueError('truncated WS301 channel')
            key=tuple(data[offset:offset+2]);offset+=2
            if key not in sizes or key in seen or offset+sizes[key]>len(data):
                raise ValueError('unknown, duplicate or truncated WS301 channel')
            seen.add(key);value=data[offset:offset+sizes[key]];offset+=sizes[key]
            if key==(1,0x75):
                if value[0]>100:raise ValueError('invalid battery percent')
                point['battery']={'percent':value[0]}
            elif key in ((3,0),(4,0)):
                if value[0] not in (0,1):raise ValueError('invalid binary state')
                if key==(3,0):point.update(contact_state='OPEN' if value[0] else 'CLOSED',event_type='state_report')
                else:point['tamper']=bool(value[0])
            else:point['diagnostics'][f'{key[0]:02x}{key[1]:02x}']=value.hex()
        return [point]
    if profile=='dragino_ds03a_lb/v1':
        if port==5 and len(data)==7 and data[0]==0x1b:
            point=_point();point['battery']={'volts':int.from_bytes(data[5:7],'big')/1000}
            point['diagnostics']={'firmware':data[1:3].hex(),'band':data[3],'sub_band':data[4]}
            return [point]
        if port==2 and len(data)==11 and not data[0]&0xf0:
            return [_dragino_record(data)]
        if port==3 and len(data)%11==0:
            return [_dragino_record(data[i:i+11],True) for i in range(0,len(data),11)]
        # Dual-channel firmware is intentionally not mapped to a single opening.
        raise ValueError('DS03A single-channel FPort 2/3 or device status FPort 5 required')
    raise ValueError('unknown decoder profile')
