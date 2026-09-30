#!/usr/bin/env python3
"""One owned triggerless logging-only diagnostic; no equipment/Item writes.

Calls the actual configured OpenHAB averageBetween and bounded JDBC read
probes, then removes only its exact owned temporary rule. Numeric history is
not source-fresh evidence. This briefly creates/runs/deletes a production
logging-only rule; it is not a completely nonmutating host command.
"""
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import re
import secrets
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'openhab/scripts'))
import openhab_sanity_check as oh


def night_window(now):
    now = now.astimezone(ZoneInfo('America/Denver'))
    end = now.replace(hour=6, minute=0, second=0, microsecond=0)
    if now < end:
        end -= timedelta(days=1)
    start = (end - timedelta(days=1)).replace(hour=20, minute=30)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def definition(uid, marker, start, end):
    if not re.fullmatch(r'hex_diag_bms_avg_[0-9a-f]{24}', uid):
        raise ValueError('owned diagnostic identity required')
    source = '''const {items,time}=require('openhab');
try {
  // Match the candidate's native local-window construction. Do not parse an
  // offset ISO string with toZDT: this runtime silently discarded +00:00.
  const now=time.toZDT();
  let e=now.withHour(6).withMinute(0).withSecond(0).withNano(0);
  if(now.isBefore(e))e=e.minusDays(1);
  const b=e.minusDays(1).withHour(20).withMinute(30);
  if(b.toInstant().toEpochMilli()!==START_MS||e.toInstant().toEpochMilli()!==END_MS)throw Error('window mismatch');
  const i=items.getItem('ConextGateway_ACPowerValue');
  const P=Java.type('org.openhab.core.persistence.extensions.PersistenceExtensions');
  const F=Java.type('org.openhab.core.persistence.FilterCriteria');
  const D=Java.type('java.time.Duration');
  const JI=Java.type('java.time.Instant');
  const numeric=a=>a==null?NaN:(typeof a==='number'?a:parseFloat(a.numericState??a.state??a.toString()));
  const watts=numeric(i.persistence.averageBetween(b,e));
  const jdbcWatts=numeric(i.persistence.averageBetween(b,e,null,'jdbc'));
  const jdbcLeftWatts=numeric(P.averageBetween(i.rawItem,b,e,P.RiemannType.LEFT,'jdbc'));
  const carry=P.persistedState(i.rawItem,b,'jdbc');
  if(carry===null)throw Error('missing boundary');
  let previous=JI.parse(b.toInstant().toString()),previousW=parseFloat(String(carry.getState()));
  let jdbcRows=0,first=null,last=null,millisSum=0,preciseSum=0;
  const add=t=>{
    if(!Number.isFinite(previousW)||previousW<0||previousW>20000||t.isBefore(previous))throw Error('invalid history');
    const dt=D.between(previous,t);
    millisSum+=previousW*dt.toMillis();
    preciseSum+=previousW*Number(dt.toNanos())/1000000;
  };
  for(const row of P.getAllStatesBetween(i.rawItem,b,e,'jdbc')) {
    if(++jdbcRows>20000)throw Error('read budget');
    const t=row.getTimestamp().toInstant().toString();
    if(first===null)first=t;
    last=t;
    add(row.getTimestamp().toInstant());
    previous=row.getTimestamp().toInstant();
    previousW=parseFloat(String(row.getState()));
  }
  add(JI.parse(e.toInstant().toString()));
  const totalMillis=D.between(JI.parse(b.toInstant().toString()),JI.parse(e.toInstant().toString())).toMillis();
  const reconstructedMillisWatts=millisSum/totalMillis,preciseWatts=preciseSum/totalMillis;
  const ok=[watts,jdbcWatts,jdbcLeftWatts,reconstructedMillisWatts,preciseWatts].every(w=>Number.isFinite(w)&&w>=0&&w<=20000);
  console.info(MARKER+JSON.stringify({status:ok?'ok':'unavailable',watts,jdbcWatts,jdbcLeftWatts,jdbcRows,
    reconstructedMillisWatts,preciseWatts,
    defaultPageSize:new F().getPageSize(),begin:b.toInstant().toString(),end:e.toInstant().toString(),first,last}));
} catch (_) {console.info(MARKER+JSON.stringify({status:'failed'}));}
'''.replace('START_MS', str(int(start.timestamp()*1000))).replace('END_MS', str(int(end.timestamp()*1000))).replace('MARKER', json.dumps(marker))
    return {'uid': uid, 'name': 'Owned read-only overnight average diagnostic',
            'description': marker, 'tags': [marker], 'triggers': [], 'conditions': [],
            'actions': [{'id': 'read', 'type': 'script.ScriptAction',
                         'configuration': {'type': 'application/javascript', 'script': source}}]}


def owned(expected, actual):
    if not isinstance(actual, dict) or actual.get('editable') is not True:
        return False
    for key in ('uid', 'description', 'tags', 'triggers', 'conditions'):
        if actual.get(key) != expected[key]:
            return False
    actions = actual.get('actions', [])
    return (isinstance(actions, list) and len(actions) == 1 and isinstance(actions[0], dict)
            and set(actions[0]) <= {'id', 'type', 'configuration', 'inputs'}
            and actions[0].get('inputs', {}) == {}
            and all(actions[0].get(key) == expected['actions'][0][key]
                    for key in ('id', 'type', 'configuration')))


def result_from_log(body, marker):
    matches = [line.split(marker, 1)[1] for line in body.splitlines() if marker in line]
    if not matches:
        return None
    if len(matches) != 1:
        raise RuntimeError('diagnostic has duplicate log receipts')
    result = json.loads(matches[0])
    fields = {'status', 'watts', 'jdbcWatts', 'jdbcLeftWatts', 'jdbcRows',
              'reconstructedMillisWatts', 'preciseWatts', 'defaultPageSize', 'begin', 'end', 'first', 'last'}
    if (not isinstance(result, dict) or set(result) != fields or result['status'] != 'ok'
            or any(type(result[key]) not in (int, float) or not math.isfinite(result[key])
                   or not 0 <= result[key] <= 20000 for key in
                   ('watts', 'jdbcWatts', 'jdbcLeftWatts', 'reconstructedMillisWatts', 'preciseWatts'))
            or type(result['jdbcRows']) is not int or not 0 < result['jdbcRows'] <= 20000
            or type(result['defaultPageSize']) is not int or not 0 < result['defaultPageSize'] <= 2147483647):
        raise RuntimeError('diagnostic has no valid numeric result')
    clocks = []
    for key in ('begin', 'first', 'last', 'end'):
        value = result[key]
        if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?Z', value):
            raise RuntimeError('diagnostic has no valid clock result')
        clocks.append(datetime.fromisoformat(value))
    if not clocks[0] <= clocks[1] <= clocks[2] <= clocks[3]:
        raise RuntimeError('diagnostic history outside requested interval')
    return result


def main():
    start, end = night_window(datetime.now(timezone.utc))
    suffix = secrets.token_hex(12)
    uid, marker = 'hex_diag_bms_avg_' + suffix, 'HEX_NIGHT_AVG_' + suffix + ':'
    expected = definition(uid, marker, start, end)
    path = '/rules/' + uid
    log = Path('/var/log/openhab/openhab.log')
    if not log.is_file():
        raise RuntimeError('known OpenHAB log unavailable')
    with log.open('rb') as stream:
        stream.seek(0, 2)
        offset = stream.tell()
        try:
            oh.get(path)
        except HTTPError as error:
            if error.code != 404:
                raise RuntimeError('diagnostic preflight failed') from None
        else:
            raise RuntimeError('diagnostic identity collision')
        attempted = False
        def mutate(method, target, body=None):
            if (method, target) not in {('POST', '/rules'), ('POST', path + '/runnow'), ('DELETE', path)}:
                raise RuntimeError('diagnostic mutation outside owned scope')
            req = Request(oh.BASE + target,
                          data=None if body is None else json.dumps(body).encode(), method=method,
                          headers={'Authorization': 'Bearer ' + oh.token(), 'Content-Type': 'application/json'})
            with urlopen(req, timeout=10) as response:
                return response.status
        try:
            attempted = True
            if mutate('POST', '/rules', expected) != 201 or not owned(expected, oh.get(path)):
                raise RuntimeError('diagnostic creation/readback failed')
            for _ in range(20):
                current = oh.get(path)
                if not owned(expected, current):
                    raise RuntimeError('diagnostic drift during initialization')
                if current.get('status', {}).get('status') == 'IDLE':
                    break
                time.sleep(1)
            else:
                raise RuntimeError('diagnostic did not initialize')
            if mutate('POST', path + '/runnow', {}) != 200:
                raise RuntimeError('diagnostic execution not accepted')
            watts = None
            for _ in range(30):
                stream.seek(offset)
                raw = stream.read(1048577)
                if len(raw) > 1048576:
                    raise RuntimeError('diagnostic log budget exceeded')
                watts = result_from_log(raw.decode(errors='replace'), marker)
                if watts is not None:
                    break
                time.sleep(1)
            if watts is None:
                raise RuntimeError('diagnostic result receipt missing')
        finally:
            if attempted:
                try:
                    current = oh.get(path)
                except HTTPError as error:
                    if error.code != 404:
                        raise RuntimeError('diagnostic cleanup read failed') from None
                else:
                    if not owned(expected, current):
                        raise RuntimeError('diagnostic cleanup ownership mismatch')
                    if mutate('DELETE', path) not in (200, 204):
                        raise RuntimeError('diagnostic cleanup refused')
                    try:
                        oh.get(path)
                    except HTTPError as error:
                        if error.code != 404:
                            raise RuntimeError('diagnostic cleanup verification failed') from None
                    else:
                        raise RuntimeError('diagnostic still registered after cleanup')
    if (datetime.fromisoformat(watts['begin']) != start
            or datetime.fromisoformat(watts['end']) != end):
        raise RuntimeError('diagnostic parsed a different window')
    print(json.dumps({'window': [start.isoformat(), end.isoformat()], 'javaProbe': watts,
                      'ownedDiagnosticRemoved': True, 'itemWrites': 0, 'persistenceWrites': 0,
                      'equipmentCommands': 0, 'sourceFreshnessQualified': False}))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('live average verification refused; private detail withheld') from None
