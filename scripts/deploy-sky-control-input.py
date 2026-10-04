#!/usr/bin/env python3
"""Default-off attended sky handoff; no restart, Item writes or pump commands.

Read-only preflight is the default. Apply is an exact file/managed/file round
trip with retained private recovery and continuity checks before every mutation.
The generic display migration gate is not opened or reused as authority.
"""
import argparse
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import sky_control_probe as sky

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('protected_sky_engine',
    ROOT/'scripts/migrate-season-countdown-rule.py')
engine = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = engine
spec.loader.exec_module(engine)
CONFIG = engine.RULES['sky']
RELEASE_READY = False
CUTOVER = datetime.fromisoformat('2026-10-02T20:00:09.206165+00:00')
MAPPINGS = {'SkyCondition':172, 'SkyConditionIcon':173,
            'SkyCondition_LastEval':540, 'SkyCondition_Diagnostic':541}
INPUTS = ('BMS_Comms_Status', 'BMS_SOC_Evidence_JSON', 'DCData_Voltage',
          'SchneiderTelemetry_Status', 'Schneider_DCData_LastUpdate',
          'Sun_Position_Elevation', 'Sun_Rise_Start', 'SouthOutlet_LastCycleStart',
          'WeatherData_HealthStatus', 'WeatherData_WH65B_AgeSeconds', *sky.PUMPS)
RELATED = tuple(dict.fromkeys([n for n,_ in CONFIG.items]+list(INPUTS)+[
    'SouthOutlet_ManualRequest','SouthOutlet_ManualResult','SouthOutlet_LastCycle',
    'SouthOutlet_LastAutoRun','SouthOutlet_AutoStatus']))
ITEM_FIELDS = ('name','type','label','category','tags','groupNames','metadata')
RULE_FIELDS = (*engine.FIELDS, 'visibility', 'configuration')


def timestamp(raw):
    raw = str(raw).split('[',1)[0]
    value = datetime.fromisoformat(raw.replace('Z','+00:00'))
    if value.utcoffset() is None: raise ValueError('explicit timestamp offset required')
    return value.astimezone(timezone.utc)


def number(raw):
    import math
    value = float(str(raw).split()[0])
    if not math.isfinite(value): raise ValueError('finite input required')
    return value


def check_safety(values, now):
    try:
        engine.require(all(values[n]=='OFF' for n in sky.PUMPS), 'pump not OFF')
        engine.require(values['BMS_Comms_Status']=='OK', 'BMS comms stale')
        engine.require(not engine.oh.atomic_soc_freshness(values['BMS_SOC_Evidence_JSON'],
                                                          now.timestamp()), 'SoC evidence stale')
        engine.require(40 <= number(values['DCData_Voltage']) <= 60, 'voltage invalid')
        engine.require(values['SchneiderTelemetry_Status'].startswith('OK,'), 'Schneider unhealthy')
        engine.require(-5 <= (now-timestamp(values['Schneider_DCData_LastUpdate'])).total_seconds()
                       <= 120, 'Schneider input stale')
        engine.require(str(values['WeatherData_HealthStatus']).upper() in ('OK','DEGRADED')
                       and 0 <= number(values['WeatherData_WH65B_AgeSeconds']) <= 120,
                       'weather unhealthy')
        # Require at least 15 minutes before eligibility can resume. A stale
        # past sunrise is NOT advanced a day or treated as tomorrow's event.
        if number(values['Sun_Position_Elevation']) <= 0:
            remaining = (timestamp(values['Sun_Rise_Start'])-now).total_seconds()
            engine.require(900 <= remaining <= 86400, 'native upcoming sunrise window required')
        else:
            elapsed = (now-timestamp(values['SouthOutlet_LastCycleStart'])).total_seconds()
            engine.require(0 <= elapsed <= 3600-900, '15-minute cooldown window required')
    except (ValueError, KeyError, TypeError):
        raise RuntimeError('valid source-bound telemetry and protected window required') from None


def read_mappings():
    sys.path.insert(0,'/home/sat/Solar_PV/analytics/src')
    import psycopg2
    from earthship_energy.db import parse_openhab_jdbc_config
    settings = parse_openhab_jdbc_config('/home/sat/.config/hex/energy-power-reader.jdbc')
    engine.require((settings.host,settings.port,settings.dbname,settings.user)==
                   ('127.0.0.1',5432,'openhab','energy_power_reader'), 'restricted reader required')
    with psycopg2.connect(**settings.connect_kwargs,connect_timeout=3,
                         options='-c default_transaction_read_only=on') as db:
        db.set_session(readonly=True,isolation_level='REPEATABLE READ')
        with db.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout='2000ms'")
            cur.execute('SELECT itemname,itemid FROM public.items WHERE itemname = ANY(%s)',
                        (list(MAPPINGS),))
            rows = cur.fetchall()
    engine.require(len(rows)==len(MAPPINGS) and dict(rows)==MAPPINGS,
                   'exact sky JDBC identities required')
    return dict(rows)


def continuity(query):
    rules = engine.oh.get('/rules')
    engine.require(len({r['uid'] for r in rules})==len(rules), 'duplicate rule identities')
    result = {'rules':{r['uid']:{k:r[k] for k in RULE_FIELDS if k in r}
                       for r in rules if r['uid']!=CONFIG.uid},
              'items':{},'histories':{},'sources':{},'mapping':read_mappings()}
    sun = engine.oh.get('/things/astro:sun:local')
    result['sun_definition'] = {k:sun[k] for k in
        ('UID','thingTypeUID','label','configuration','channels','editable') if k in sun}
    for name in RELATED:
        item = engine.oh.get('/items/'+name+'?metadata=.*')
        result['items'][name] = {k:item[k] for k in ITEM_FIELDS if k in item}
    result['links'] = sorted((x for x in engine.oh.get('/links') if x.get('itemName') in RELATED),
                             key=lambda x:(x['itemName'],x['channelUID']))
    for name in MAPPINGS:
        result['histories'][name] = engine.oh.get('/persistence/items/'+name+'?'+query)
    for path in sorted(CONFIG.target.parent.glob('*.js')):
        if path.name==CONFIG.target.name: continue
        engine.require(path.is_file() and not path.is_symlink(), 'unowned script shape changed')
        result['sources'][path.name] = engine.digest(path.read_bytes())
    pid = subprocess.run(['systemctl','show','openhab.service','-p','MainPID','--value'],
                         capture_output=True,text=True,check=True,timeout=5).stdout.strip()
    engine.require(pid.isdecimal() and int(pid)>0, 'OpenHAB process unavailable')
    result['openhab_pid'] = int(pid)
    return result


def healthy_off():
    from thermal_radiation_runtime import collect, _validate_receipt
    now = datetime.now(timezone.utc)
    rows = collect(dict(target=now.isoformat(),assessed_at=now.isoformat(),cutover=CUTOVER.isoformat()),
        config_path='/home/sat/.config/hex/energy-power-reader.jdbc',
        policy_path='/home/sat/.config/hex/weather-radiation-policy.json')
    engine.require(len(rows)==1 and rows[0][0]==now, 'exact current native weather target required')
    evidence = _validate_receipt(rows[0][1],target=now,cutover=CUTOVER)
    sun = engine.oh.get('/things/astro:sun:local')
    engine.require(sun.get('statusInfo',{}).get('status')=='ONLINE', 'native Sun Thing unavailable')
    consumer = engine.oh.get('/rules/'+sky.UID)
    sky.control_payload(consumer,(ROOT/'openhab/rules/southoutlet-cycle-current.js').read_bytes(),
                        consumer_revision='durable-recovery')
    values = {n:engine.oh.get('/items/'+n)['state'] for n in INPUTS}
    now = datetime.now(timezone.utc)
    _validate_receipt(rows[0][1],target=now,cutover=CUTOVER)
    check_safety(values,now)
    engine.require(all(engine.oh.get('/items/'+n)['state']=='OFF' for n in sky.PUMPS),
                   'pump changed during preflight')
    return evidence['snapshotSha256']


class Transaction:
    def __init__(self, original, receipt, guard, *, config=CONFIG):
        self.original,self.receipt,self.guard,self.config = original,Path(receipt),guard,config
        self.owned_identity=None
        self.withdrawals=0
        self.mutated=False

    def managed_original(self, current):
        return (engine.managed_rule_ok(current,self.original)
                and all(current.get(k)==self.original.get(k) for k in RULE_FIELDS))

    def verify_owned(self):
        info=self.config.target.lstat()
        engine.require(stat.S_ISREG(info.st_mode) and not self.config.target.is_symlink()
                       and (info.st_dev,info.st_ino)==self.owned_identity
                       and engine.digest(self.config.target.read_bytes())==self.config.source_sha,
                       'unowned sky file; refuse withdrawal or completion')

    def install_exclusive(self):
        source=self.config.source.read_bytes()
        engine.require(engine.digest(source)==self.config.source_sha, 'candidate source drift')
        fd,name=tempfile.mkstemp(prefix='.protected-sky-',suffix='.tmp',dir=self.config.target.parent)
        staged=Path(name)
        try:
            os.fchmod(fd,0o644)
            with os.fdopen(fd,'wb') as stream:
                stream.write(source); stream.flush(); os.fsync(stream.fileno())
            os.link(staged,self.config.target)  # Atomic publish; never overwrite a racing file.
            info=self.config.target.lstat()
            self.owned_identity=(info.st_dev,info.st_ino)
        finally:
            staged.unlink()

    def withdraw_owned(self):
        self.verify_owned()
        self.withdrawals+=1
        target=self.receipt/f'withdrawn-{self.withdrawals}.js'
        engine.require(not target.exists() and not target.is_symlink(), 'private withdrawal target exists')
        self.config.target.rename(target)
        os.chmod(target,0o600)

    def to_file(self):
        self.guard()
        engine.require(self.managed_original(engine.rule_or_none(self.config))
                       and not self.config.target.exists() and not self.config.target.is_symlink(),
                       'exact managed preimage and absent sky file required')
        self.mutated=True
        engine.require(engine.request('DELETE','/rules/'+self.config.uid) in (200,204),
                       'managed sky withdrawal refused')
        engine.wait_rule(lambda r:r is None,self.config)
        self.guard()
        self.install_exclusive()
        engine.wait_rule(lambda r:engine.file_rule_ok(r,self.config),self.config)
        self.guard()
        self.verify_owned()
        engine.require(sum(r.get('uid')==self.config.uid for r in engine.oh.get('/rules'))==1,
                       'sky provider is not unique')

    def to_managed(self):
        self.guard()
        current=engine.rule_or_none(self.config)
        if self.managed_original(current):
            engine.require(not self.config.target.exists() and not self.config.target.is_symlink(),
                           'managed/file overlap; refuse rollback')
            return
        if self.config.target.exists() or self.config.target.is_symlink():
            engine.require(current is None or current.get('editable') is False,
                           'unexpected managed owner; refuse rollback')
            self.withdraw_owned()
            engine.wait_rule(lambda r:r is None,self.config)
        engine.require(engine.rule_or_none(self.config) is None, 'unknown sky owner; refuse rollback')
        self.guard()
        payload={k:self.original[k] for k in RULE_FIELDS if k in self.original}
        engine.require(engine.request('POST','/rules',payload)==201, 'managed sky restore refused')
        engine.wait_rule(self.managed_original,self.config)
        self.guard()

    def apply(self):
        try:
            self.to_file()
            self.to_managed()  # Exercise the actual original provider before final transfer.
            self.to_file()
        except Exception:
            if self.mutated: self.to_managed()
            raise


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--attended',action='store_true')
    parser.add_argument('--physical-pumps-off',action='store_true')
    args=parser.parse_args(argv)
    if args.apply:
        engine.require(RELEASE_READY, 'protected sky release gate remains closed')
        engine.require(args.attended and args.physical_pumps_off, 'fresh physical attendance/OFF required')
    original,_=engine.preflight(CONFIG)
    healthy_off()
    now=datetime.now(ZoneInfo('America/Denver'))
    end=now.replace(hour=0,minute=0,second=0,microsecond=0)
    query=urlencode(dict(serviceId='jdbc',starttime=(end-timedelta(days=1)).isoformat(),
                         endtime=end.isoformat(),boundary='false'))
    before=continuity(query)
    def guarded():
        engine.require(continuity(query)==before, 'unowned definition/source/history/PID drift')
        healthy_off()
    guarded()
    print('protected_sky_preflight=passed; fixed_history=previous_complete_local_day',flush=True)
    if not args.apply: return
    directory=engine.backup(original,CONFIG)
    for name,value in [('continuity.json',dict(history_query=query,snapshot=before))]:
        fd=os.open(directory/name,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(fd,'w') as stream:
            json.dump(value,stream,sort_keys=True); stream.flush(); os.fsync(stream.fileno())
    print('private_backup='+str(directory),flush=True)
    Transaction(original,directory,guarded).apply()
    print('status=file_provider_provisional; managed_rollback_exercised=true; natural_update_pending=true',
          flush=True)


if __name__=='__main__':
    os.umask(0o077)
    main()
