"""Persistent LoRaWAN ordering and qualification. No provider command path."""
import base64
from copy import deepcopy
import math
import re
from datetime import timedelta
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL
from services.observations.contract import canonical, digest, instant, strict_json, normalize
from .decoders import decode

MAX_EVENT_BYTES=65536


class Engine:
    def __init__(self,registry,store):
        self.registry=registry;self.store=store

    def _state(self,device):
        state=self.store.state(device['sensor_id'])
        if state is None or state['hardware_epoch']!=device['hardware_epoch']:
            return dict(hardware_epoch=device['hardware_epoch'],dev_addr=None,session=None,joined_at=None,
                fcnt=None,fingerprint=None,last_received_at=None,last_observed_at=None,
                contact_state=None,contact_observed_at=None,contact_received_at=None,
                last_transition_at=None,valid_until=None,battery={},tamper=None,rssi=None,snr=None,
                source_epoch=None,raw_sha256=None,fault=None,health='UNKNOWN',gaps=0,accepted=0)
        return state

    def ingest(self,raw,topic,*,received_at,retained=False):
        received_at=instant(received_at)
        if not isinstance(raw,bytes):raise ValueError('exact MQTT bytes required')
        raw_id=str(uuid4());points=[];gap=False;device=None;state=None;event_id=None;fingerprint=None;original_state=None
        decision='invalid_envelope'
        with self.store.transaction():
            try:
                if len(raw)>MAX_EVENT_BYTES:decision='oversized_input';raise ValueError()
                if retained:decision='retained_input';raise ValueError()
                row=strict_json(raw)
                match=re.fullmatch(r'application/([^/]+)/device/([0-9a-f]{16})/event/(up|join)',topic)
                if not match:decision='invalid_topic';raise ValueError()
                app,eui,event=match.groups()
                if app!=self.registry.config['application_id'] or row['deviceInfo']['applicationId']!=app or row['deviceInfo']['devEui']!=eui:
                    decision='identity_mismatch';raise ValueError()
                device=self.registry.by_lorawan.get(eui)
                if device is None:decision='unknown_device';raise ValueError()
                network_at=instant(row['time'])
                if network_at>received_at:decision='future_timestamp';raise ValueError()
                # Late transport delivery cannot become freshly observed evidence.
                if received_at-network_at>timedelta(seconds=device['offline_seconds']):
                    decision='late_event';raise ValueError()
                event_id=str(UUID(row['deduplicationId']))
                address=row['devAddr']
                if not re.fullmatch('[0-9a-f]{8}',address):raise ValueError()
                fingerprint=digest(canonical({k:row.get(k) for k in ('deviceInfo','devAddr','time','fCnt','fPort','data')}))
                known=self.store.seen(eui+':'+event_id)
                if known is not None:
                    decision='duplicate' if known==fingerprint else 'event_id_conflict';raise ValueError()
                state=self._state(device);original_state=deepcopy(state)
                if event=='join':
                    if state['joined_at'] and network_at<=instant(state['joined_at']):
                        decision='out_of_order';raise ValueError()
                    if state['last_observed_at'] and network_at<instant(state['last_observed_at']):
                        decision='out_of_order';raise ValueError()
                    state.update(dev_addr=address,session=event_id,source_epoch=event_id,
                        joined_at=network_at.isoformat(),fcnt=None,fingerprint=None,fault='awaiting_contact')
                    decision='joined'
                else:
                    counter=row['fCnt'];port=row['fPort']
                    if type(counter) is not int or not 0<=counter<=0xffffffff or type(port) is not int or not 1<=port<=223:
                        raise ValueError('invalid counter or port')
                    if state['dev_addr'] is not None and address!=state['dev_addr']:
                        decision='wrong_session';raise ValueError()
                    if state['joined_at'] and network_at<=instant(state['joined_at']):
                        decision='out_of_order';raise ValueError()
                    data=base64.b64decode(row['data'],validate=True)
                    payload_fingerprint=digest(canonical(dict(port=port,data=row['data'])))
                    if state['fcnt'] is not None and counter<=state['fcnt']:
                        if counter==state['fcnt']:
                            decision='duplicate' if payload_fingerprint==state['fingerprint'] else 'counter_conflict'
                        else:
                            decision='out_of_order' if network_at<=instant(state['last_observed_at']) else 'counter_regression'
                        if decision in ('counter_conflict','counter_regression'):state['fault']=decision
                        raise ValueError()
                    if state['last_observed_at'] and network_at<instant(state['last_observed_at']):
                        decision='out_of_order';raise ValueError()
                    if state['session'] is None:
                        state.update(session='bootstrap:'+address,source_epoch=str(uuid5(NAMESPACE_URL,device['hardware_epoch']+address)),dev_addr=address)
                    gap=state['fcnt'] is not None and counter>state['fcnt']+1
                    decision='invalid_payload'
                    decoded=decode(device['decoder'],data,port)
                    # Validate every record before changing persistent ordering state.
                    for point in decoded:
                        observed=instant(point['observed_at']) if point['observed_at'] else network_at
                        if observed>network_at:decision='future_timestamp';raise ValueError()
                        if point['historical'] and point['observed_at'] is None:raise ValueError('undated history refused')
                        if not point['historical'] and state['contact_observed_at'] and point['contact_state'] is not None and observed<instant(state['contact_observed_at']):
                            decision='out_of_order';raise ValueError()
                    if gap:state['fault']='missing_frames'
                    state['gaps']+=(counter-state['fcnt']-1) if gap else 0
                    state.update(fcnt=counter,fingerprint=payload_fingerprint,last_observed_at=network_at.isoformat(),
                        last_received_at=received_at.isoformat(),raw_sha256=digest(raw),accepted=state['accepted']+1)
                    rx=row.get('rxInfo',[])
                    if not isinstance(rx,list) or len(rx)>32:raise ValueError('bounded reception diagnostics required')
                    valid_rx=[r for r in rx if isinstance(r,dict) and type(r.get('rssi')) in (int,float) and
                        type(r.get('snr')) in (int,float) and math.isfinite(r['rssi']) and math.isfinite(r['snr']) and -200<=r['rssi']<=10 and -50<=r['snr']<=50]
                    if valid_rx:
                        best=max(valid_rx,key=lambda r:r['snr']);state.update(rssi=best['rssi'],snr=best['snr'])
                    for index,point in enumerate(decoded):
                        observed=instant(point['observed_at']) if point['observed_at'] else network_at
                        history=point['historical']
                        contact=point['contact_state']
                        until=observed+timedelta(seconds=device['state_stale_seconds'])
                        event_type=point['event_type']
                        if not history:
                            if point['battery']:state['battery']=point['battery']
                            if point['tamper'] is not None:
                                if state['tamper']!=point['tamper']:event_type='tamper' if point['tamper'] else 'tamper_cleared'
                                state['tamper']=point['tamper']
                            if contact is not None:
                                if state['contact_state']!=contact:
                                    state['last_transition_at']=observed.isoformat()
                                    if state['contact_state'] is not None:event_type='opened' if contact=='OPEN' else 'closed'
                                state.update(contact_state=contact,contact_observed_at=observed.isoformat(),
                                    contact_received_at=received_at.isoformat(),valid_until=until.isoformat(),fault=None)
                        timestamp_basis='device_clock' if point['observed_at'] is not None else 'network_reception'
                        point.update(schema='earthship-contact-observation/v1',device_id=eui,sensor_id=device['sensor_id'],
                            device_type=device['device_type'],location=device['location'],zone=device['zone'],
                            observed_at=observed.isoformat(),received_at=received_at.isoformat(),
                            valid_until=until.isoformat(),event_type=event_type,frame_counter=counter,
                            source_epoch=state['source_epoch'],hardware_epoch=device['hardware_epoch'],
                            source='chirpstack/v4',decoder=device['decoder'],raw_sha256=digest(raw),raw_id=raw_id,
                            synthetic=self.registry.config['environment']=='simulation',
                            quality='historical' if history else 'synthetic' if self.registry.config['environment']=='simulation' else
                                'qualified' if device['radio_verified'] else 'documented_unverified',
                            timestamp_basis=timestamp_basis,
                            rssi=state['rssi'],snr=state['snr'],continuity='gap' if gap else 'supervised_estimate')
                        points.append(point)
                    for point in points:
                        point['measurements']=[]
                        for kind,value,unit in [('contact_state',point['contact_state'],'state'),('tamper',point['tamper'],'boolean')]:
                            if value is None or kind not in device['observation_types'] or point['historical']:continue
                            normalized=normalize(sensor=device,kind=kind,value=value,unit=unit,
                                observed_at=point['observed_at'],received_at=received_at,valid_until=point['valid_until'],
                                source_identity='chirpstack/device/'+eui,raw_sha256=digest(raw),source_epoch=state['source_epoch'],
                                timestamp_basis=point['timestamp_basis'],synthetic=point['synthetic'],
                                qualified=not point['synthetic'] and device['radio_verified'] and instant(point['valid_until'])>received_at)
                            point['measurements'].append(normalized)
                    decision='accepted'
                self.store.mark_seen(eui+':'+event_id,fingerprint)
            except (ValueError,KeyError,TypeError,OverflowError,UnicodeError):
                # A validated new but corrupt payload withdraws contact validity.
                if original_state is not None:
                    if decision not in ('counter_conflict','counter_regression'):
                        state=original_state
                    if decision=='invalid_payload':
                        state['fault']='invalid_payload'
                        # A corrupt decoded reading still consumed a trusted transport frame.
                        state.update(fcnt=counter,fingerprint=payload_fingerprint,last_observed_at=network_at.isoformat())
                points=[]
            self.store.execute('INSERT INTO raw_events(id,received_at,topic,raw_sha256,raw_base64,decision) VALUES(?,?,?,?,?,?)',
                (raw_id,received_at.isoformat(),topic[:256],digest(raw),base64.b64encode(raw[:MAX_EVENT_BYTES]).decode(),decision))
            if state is not None:self.store.save_state(device['sensor_id'],state)
            for point in points:self.store.observation(raw_id,point)
            if gap and decision=='accepted':
                self.store.observation(raw_id,dict(schema='earthship-contact-observation/v1',sensor_id=device['sensor_id'],
                    hardware_epoch=device['hardware_epoch'],observed_at=original_state['contact_observed_at'] or received_at.isoformat(),
                    received_at=received_at.isoformat(),event_type='quality_barrier',contact_state=None,historical=False,
                    reason='missing_frames',synthetic=self.registry.config['environment']=='simulation'))
            if decision in ('invalid_payload','counter_conflict','counter_regression','joined') and device is not None:
                self.store.observation(raw_id,dict(schema='earthship-contact-observation/v1',sensor_id=device['sensor_id'],
                    hardware_epoch=device['hardware_epoch'],observed_at=received_at.isoformat(),received_at=received_at.isoformat(),
                    event_type='quality_barrier',contact_state=None,historical=False,reason=decision,
                    synthetic=self.registry.config['environment']=='simulation'))
        return decision

    def gateway_activity(self,raw,topic,received_at,retained=False):
        now=instant(received_at)
        match=re.fullmatch('us915_1/gateway/([0-9a-f]{16})/event/stats',topic)
        known={g['gateway_id'] for g in self.registry.config.get('gateways',[])}
        if retained or not match or match[1] not in known or not 1<=len(raw)<=16384:return 'refused_gateway_activity'
        # The payload may be protobuf. Receipt proves broker/bridge activity only.
        with self.store.transaction():
            self.store.save_state('gateway:'+match[1],dict(last_stats_received_at=now.isoformat()))
        return 'gateway_activity'

    def snapshot(self,now):
        from .history import summarize
        now=instant(now);sensors=[]
        with self.store.transaction():
            for device in self.registry.devices.values():
                if device['transport']!='lorawan' or not device['enabled']:continue
                state=self._state(device)
                received=instant(state['last_received_at']) if state['last_received_at'] else None
                age=(now-received).total_seconds() if received else None
                health='UNKNOWN' if age is None else 'OFFLINE' if age>=device['offline_seconds'] else 'STALE' if age>=device['communication_stale_seconds'] else 'ONLINE'
                valid=(state['contact_state'] is not None and state['valid_until'] is not None and
                    now<instant(state['valid_until']) and instant(state['contact_observed_at'])<=now and
                    health=='ONLINE' and state['fault'] is None)
                if health!=state['health']:
                    self.store.observation(None,dict(schema='earthship-contact-observation/v1',sensor_id=device['sensor_id'],
                        device_id=device['device_id'],hardware_epoch=device['hardware_epoch'],observed_at=now.isoformat(),
                        received_at=now.isoformat(),event_type='communication_'+health.lower(),historical=False,
                        synthetic=self.registry.config['environment']=='simulation',contact_state=None))
                    state['health']=health;self.store.save_state(device['sensor_id'],state)
                battery=dict(state['battery'])
                battery['condition']='UNKNOWN' if not battery else 'LOW' if (
                    battery.get('percent',101)<=device['battery_low_percent'] or battery.get('volts',11)<=device['battery_low_volts']) else 'OK'
                quality=(('synthetic' if self.registry.config['environment']=='simulation' else 'qualified' if device['radio_verified'] else 'documented_unverified') if valid else state['fault'] or (health.lower() if health!='ONLINE' else 'stale_contact'))
                sensors.append(dict(sensor_id=device['sensor_id'],device_id=device['device_id'],name=device['name'],location=device['location'],
                    zone=device['zone'],device_type=device['device_type'],transport=device['transport'],health=health,
                    contact_state=state['contact_state'],current_state=state['contact_state'] if valid else 'UNKNOWN',valid=valid,
                    quality=quality,
                    last_observed_at=state['contact_observed_at'],last_received_at=state['last_received_at'],
                    last_transition_at=state['last_transition_at'],valid_until=state['valid_until'],
                    communication_valid_until=(received+timedelta(seconds=device['communication_stale_seconds'])).isoformat() if received else None,
                    offline_at=(received+timedelta(seconds=device['offline_seconds'])).isoformat() if received else None,
                    battery=battery,tamper=state['tamper'],rssi=state['rssi'],snr=state['snr'],frame_counter=state['fcnt'],
                    source_epoch=state['source_epoch'],hardware_epoch=device['hardware_epoch'],raw_sha256=state['raw_sha256'],
                    decoder=device['decoder'],radio_verified=device['radio_verified'],accepted_uplinks=state['accepted'],missing_frame_estimate=state['gaps']))
            history=self.store.history(limit=5000)
        recent,durations,reliability=summarize(history,self.registry,now)
        return dict(schema='earthship-sensor-view/v1',environment=self.registry.config['environment'],
            registry_sha256=self.registry.sha256,generated_at=now.isoformat(),expires_at=(now+timedelta(seconds=45)).isoformat(),
            sensors=sensors,recent_events=recent,daily_durations=durations,reliability=reliability,
            history_coverage='bounded_5000_latest_records',authority='observation_only')


def profile_has_clock(profile):
    return profile=='dragino_ds03a_lb/v1'
