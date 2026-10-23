"""Read-only shade acquisition, bounded immutable history and movement episodes."""
from datetime import timedelta
from pathlib import Path
import os,sqlite3,stat,re
from ..codec import canonical,loads,identity
from ..control_contracts import instant
from ..evidence import utc
from .contracts import closed,number,name

MAP_FIELDS={'schema','shade_id','zone','device_id','epoch','source','convention','native_max','resolution','feedback_basis','valid_from','freshness_seconds'}
PACKET_FIELDS={'event_id','sequence','native_position','native_target','movement','origin','observed_at','received_at','available_at','online','time_basis','device_id','source'}
EVENT_FIELDS={'schema','shade_id','zone','epoch','mapping','mapping_sha256','event_id','sequence','native_position','native_target','position_open_pct','target_open_pct','movement','origin','feedback_basis','observed_at','received_at','available_at','valid_until','quality','online','time_basis','device_id','source','event_sha256'}
MAX_EVENTS=8192


def normalize_event(mapping,packet):
    closed(mapping,MAP_FIELDS);closed(packet,PACKET_FIELDS)
    if packet['device_id']!=mapping['device_id'] or packet['source']!=mapping['source']:raise ValueError('captured acquisition device or source differs from mapping')
    if mapping['schema']!='earthship-shade-mapping/v1':raise ValueError('versioned mapping required')
    for key in ('shade_id','zone','epoch'):name(mapping[key])
    for key in ('device_id','source'):
        if not isinstance(mapping[key],str) or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:/@+-]{0,191}',mapping[key]) is None:raise ValueError('bounded native device or source identity required')
    if mapping['convention'] not in ('closed_100','open_100') or mapping['feedback_basis'] not in ('independent_position','travel_time_estimate','controller_estimate'):raise ValueError('explicit native mapping and feedback basis required')
    scale=number(mapping['native_max'],.01,100000);number(mapping['resolution'],.000001,scale);number(mapping['freshness_seconds'],1,86400)
    name(packet['event_id'])
    if type(packet['sequence']) is not int or not 0<=packet['sequence']<2**53 or packet['online'] is not None and type(packet['online']) is not bool:raise ValueError('explicit acquisition ordering and availability required')
    if packet['time_basis'] not in ('source_observed','adapter_report_reception'):raise ValueError('explicit acquisition clock basis required')
    if packet['movement'] not in ('opening','closing','stopped','unknown') or packet['origin'] not in ('manual','existing_automation','identified_other','unknown'):raise ValueError('closed movement and supported-origin catalog required')
    observed,received,available=map(instant,(packet['observed_at'],packet['received_at'],packet['available_at']))
    if not instant(mapping['valid_from'])<=observed<=received<=available:raise ValueError('acquisition clocks or installation epoch differ')
    values={}
    for key in ('native_position','native_target'):
        raw=packet[key]
        if raw is not None:number(raw,0,scale)
        # No rounding: preserve actual native report precision.
        values[key]=None if raw is None else (scale-raw if mapping['convention']=='closed_100' else raw)*100/scale
    qualified=packet['online'] and packet['native_position'] is not None and available<observed+timedelta(seconds=mapping['freshness_seconds'])
    event=dict(schema='earthship-shade-observation/v1',shade_id=mapping['shade_id'],zone=mapping['zone'],epoch=mapping['epoch'],mapping=mapping,mapping_sha256=identity(mapping),
        **packet,position_open_pct=values['native_position'],target_open_pct=values['native_target'],feedback_basis=mapping['feedback_basis'],
        valid_until=(observed+timedelta(seconds=mapping['freshness_seconds'])).isoformat(),quality='qualified' if qualified else 'unavailable')
    event['event_sha256']=identity(event);return loads(canonical(event))


def validate_event(value):
    closed(value,EVENT_FIELDS)
    expected=normalize_event(value['mapping'],{key:value[key] for key in PACKET_FIELDS})
    if canonical(value)!=canonical(expected):raise ValueError('shade acquisition or mapping identity differs')
    return expected


def target_observed(events,targets,*,now):
    now=utc(now)
    if not isinstance(targets,dict) or not 1<=len(targets)<=26:return False
    rows={};physical=set()
    for e in events:
        validate_event(e)
        device=(e['source'],e['device_id'])
        if e['shade_id'] in rows or device in physical:return False
        physical.add(device);rows[e['shade_id']]=e
    for shade,target in targets.items():
        number(target,0,100);e=rows.get(shade)
        if not e or e['quality']!='qualified' or e['feedback_basis']!='independent_position' or e['movement']!='stopped' or not instant(e['available_at'])<=now<instant(e['valid_until']):return False
        if abs(e['position_open_pct']-target)>1e-9:return False
    return True


class ShadeHistory:
    """Original events are immutable; exhausted capacity refuses ingestion visibly."""
    def __init__(self,path):
        self.path=Path(path)
        if self.path.is_symlink() or self.path.parent.resolve()!=self.path.parent.absolute():raise ValueError('private direct history path required')
        if not self.path.exists():
            fd=os.open(self.path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
        info=self.path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077 or info.st_nlink!=1:raise ValueError('private owned history required')
        with self._connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, shade TEXT, epoch TEXT, available TEXT, observed TEXT, seq INTEGER, raw BLOB, disposition TEXT)')

    def _connect(self):
        return sqlite3.connect(self.path,timeout=1)

    def ingest(self,event):
        e=validate_event(event);key=identity([e['shade_id'],e['epoch'],e['event_id']]);raw=canonical(e)
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            previous=db.execute('SELECT raw FROM events WHERE id=?',(key,)).fetchone()
            if previous:
                if bytes(previous[0])!=raw:raise ValueError('duplicate acquisition changed original bytes')
                return 'duplicate'
            if db.execute('SELECT count(*) FROM events').fetchone()[0]>=MAX_EVENTS:raise ValueError('shade history capacity exhausted')
            originals=[loads(r[0]) for r in db.execute('SELECT raw FROM events WHERE shade=? AND disposition=?',(e['shade_id'],'retained'))]
            disposition='retained'
            if originals:
                latest=max(originals,key=lambda r:(instant(r['mapping']['valid_from']),instant(r['observed_at']),r['sequence']))
                if e['epoch']==latest['epoch'] and (e['sequence']<=latest['sequence'] or instant(e['observed_at'])<instant(latest['observed_at'])):disposition='out_of_order'
                elif instant(e['mapping']['valid_from'])<instant(latest['mapping']['valid_from']):disposition='out_of_order'
                elif e['epoch']==latest['epoch'] and e['mapping_sha256']!=latest['mapping_sha256']:raise ValueError('mapping change requires a new installation epoch')
            db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?)',(key,e['shade_id'],e['epoch'],e['available_at'],e['observed_at'],e['sequence'],raw,disposition))
            return disposition

    def originals(self):
        with self._connect() as db:return [loads(r[0]) for r in db.execute('SELECT raw FROM events WHERE disposition=? ORDER BY rowid',('retained',))]

    def current(self,*,now):
        now=utc(now);latest={}
        for e in self.originals():
            if instant(e['available_at'])>now:continue
            old=latest.get(e['shade_id'])
            key=lambda r:(instant(r['mapping']['valid_from']),instant(r['observed_at']),r['sequence'])
            if old is None or key(e)>key(old):latest[e['shade_id']]=e
        # Unavailable/offline rows must be attached as gaps so declarations and
        # stale epochs cannot silently become current; callers can request them.
        return [r for _,r in sorted(latest.items()) if r['quality']=='qualified' and now<instant(r['valid_until'])]

    def latest(self,*,now):
        now=utc(now);rows={}
        for e in self.originals():
            if instant(e['available_at'])>now:continue
            old=rows.get(e['shade_id'])
            if old is None or (instant(e['mapping']['valid_from']),instant(e['observed_at']),e['sequence'])>(instant(old['mapping']['valid_from']),instant(old['observed_at']),old['sequence']):rows[e['shade_id']]=e
        return list(rows.values())

    def movements(self):
        rows=self.originals();groups={};episodes=[]
        for e in rows:groups.setdefault((e['shade_id'],e['epoch']),[]).append(e)
        for (shade,epoch),events in groups.items():
            previous=None;pending=[]
            for e in sorted(events,key=lambda r:(instant(r['observed_at']),r['sequence'])):
                if e['quality']!='qualified' or e['position_open_pct'] is None:
                    pending=[];previous=None;continue
                if previous and not pending and (e['position_open_pct']!=previous['position_open_pct'] or e['movement'] in ('opening','closing')):pending=[previous]
                if pending:
                    pending.append(e)
                    if e['movement']=='stopped':
                        origins={r['origin'] for r in pending[1:]}
                        episode=dict(shade_id=shade,epoch=epoch,from_open_pct=pending[0]['position_open_pct'],to_open_pct=e['position_open_pct'],
                            start_earliest=pending[0]['observed_at'],start_latest=pending[1]['observed_at'],stop_observed_at=e['observed_at'],
                            intermediate_open_pct=[r['position_open_pct'] for r in pending[1:-1]],event_refs=[r['event_sha256'] for r in pending],
                            origin=origins.pop() if len(origins)==1 else 'unknown',thermal_benefit_verified=False)
                        episode['episode_id']=identity(episode);episodes.append(episode);pending=[]
                previous=e
        return episodes
