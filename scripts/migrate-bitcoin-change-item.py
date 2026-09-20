#!/usr/bin/env python3
"""Attended exact-target display Item transfer and provider rollback rehearsal."""
import json, os, subprocess, sys, tempfile, time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from decimal import Decimal, InvalidOperation
sys.path[:0] = ['/home/sat/earthship-ui/openhab/scripts', '/home/sat/Solar_PV/analytics/src']
import openhab_sanity_check as oh
from earthship_energy.db import parse_openhab_jdbc_config
import psycopg2

NAME = 'BTC_Price_24h_PercentChange'
RULE = 'hex_btc_24h_change'
SOURCE = Path('/home/sat/earthship-ui/openhab/file-config/drafts/bitcoin-change.items')
TARGET = Path('/etc/openhab/items/bitcoin-change.items')
EXPECTED = dict(name=NAME, type='Number', label='"BTC 24h Change [%.2f %%]"',
                category='', tags=[], groupNames=['BTC_Price'])

def request(path, method, data=None, content='application/json'):
    with urlopen(Request(oh.BASE+path, method=method, data=data,
        headers={'Authorization':'Bearer '+oh.token(),'Content-Type':content}), timeout=15) as r:
        assert r.status in (200,201,202,204)

def item():
    try:return oh.get('/items/'+NAME+'?metadata=all')
    except HTTPError as e:
        if e.code==404:return None
        raise

def validate(i):
    assert i is not None
    actual={k:i.get(k) for k in EXPECTED}
    actual['category']=actual['category'] or ''
    if actual!=EXPECTED:raise ValueError('Item definition mismatch: '+json.dumps(actual))
    assert not i.get('metadata')

def same_number(left, right):
    try:a,b=Decimal(left),Decimal(right)
    except (InvalidOperation, TypeError, ValueError):return False
    return a.is_finite() and b.is_finite() and a==b

def wait(provider, state=None):
    for _ in range(100):
        i=item()
        if provider is None and i is None:return
        if i is not None and i.get('editable') is provider:
            validate(i)
            if state is None or same_number(i['state'],state):return
        time.sleep(.2)
    raise RuntimeError('provider or persisted state did not restore')

def definitions():
    return {r['uid']:{k:v for k,v in r.items() if k not in
        ('status','editable','configDescriptions','templateState')} for r in oh.get('/rules')}

def main():
    assert not TARGET.exists() and not TARGET.is_symlink()
    original=item();validate(original);assert original['editable'] is True
    assert oh.get('/rules/'+RULE)['status']['status']=='IDLE'
    links=oh.get('/links');assert not any(x['itemName']==NAME for x in links)
    rules=definitions();source=SOURCE.read_bytes()
    os.umask(0o077);receipt=Path(tempfile.mkdtemp(prefix='bitcoin-item-transfer-'))
    def save(name,data):
        body=json.dumps(data,indent=2,default=str)+'\n'
        patch='*** Begin Patch\n*** Add File: '+str(receipt/name)+'\n'+''.join('+'+l+'\n' for l in body.splitlines())+'*** End Patch\n'
        subprocess.run(['apply_patch'],input=patch,text=True,check=True,capture_output=True)
    db=psycopg2.connect(**parse_openhab_jdbc_config('/var/lib/openhab/config/org/openhab/jdbc.config').connect_kwargs,connect_timeout=5)
    db.set_session(readonly=True,autocommit=True)
    def history(cutoff=None):
        with db.cursor() as c:
            c.execute("SET statement_timeout='5s'")
            c.execute('SELECT itemid FROM public.items WHERE itemname=%s',(NAME,));assert c.fetchall()==[(139,)]
            c.execute("SELECT count(*),max(time),md5(string_agg(md5(value::text),'' ORDER BY time,value)) FROM public.item0139"+
                      (' WHERE time<=%s' if cutoff else ''),(cutoff,) if cutoff else ())
            return c.fetchone()
    succeeded=False;deleted=False
    try:
        save('before.json',{'item':original,'rules':rules,'links':links})
        print('private_receipt='+str(receipt),flush=True)
        request('/rules/'+RULE+'/enable','POST',b'false','text/plain')
        for _ in range(100):
            if oh.get('/rules/'+RULE)['status']=={'status':'UNINITIALIZED','statusDetail':'DISABLED'}:break
            time.sleep(.2)
        else:raise RuntimeError('writer did not disable')
        original=item();validate(original);assert original['editable'] is True
        before=history();assert before[0]>0
        with db.cursor() as c:
            c.execute('SELECT value::text FROM public.item0139 ORDER BY time DESC LIMIT 1')
            assert same_number(c.fetchone()[0],original['state'])
        save('paused.json',{'item':original,'history':before})
        assert SOURCE.read_bytes()==source and definitions()==rules and oh.get('/links')==links
        request('/items/'+NAME,'DELETE');deleted=True;wait(None)
        subprocess.run(['install','-m','644',str(SOURCE),str(TARGET)],check=True)
        wait(False,original['state'])
        assert TARGET.read_bytes()==source
        TARGET.rename(receipt/'rollback.items');wait(None)
        request('/items/'+NAME,'PUT',json.dumps(EXPECTED).encode());wait(True,original['state'])
        request('/items/'+NAME,'DELETE');wait(None)
        (receipt/'rollback.items').rename(TARGET);wait(False,original['state'])
        assert history(before[1])==before and definitions()==rules and oh.get('/links')==links
        save('verified.json',{'provider':'file','rollback_restoration_verified':True,
             'history_preserved':True,'other_definitions_and_links_unchanged':True})
        succeeded=True
    finally:
        try:
            if not succeeded and deleted:
                if TARGET.exists():
                    assert not TARGET.is_symlink() and TARGET.read_bytes()==source
                    TARGET.rename(receipt/'failed.items');wait(None)
                current=item()
                if current is None:request('/items/'+NAME,'PUT',json.dumps(EXPECTED).encode())
                wait(True,original['state'])
        finally:
            db.close()
            request('/rules/'+RULE+'/enable','POST',b'true','text/plain')
    print('file_transfer_and_rollback_verified=true',flush=True)
    print('writer_reenabled=true',flush=True)

if __name__=='__main__':
    raise SystemExit('Migration held: resolve file-provider label normalization before running')
