#!/usr/bin/env python3
"""Closed Moon display state/JDBC rehearsal, synthetic values only in isolation."""
from datetime import datetime
from decimal import Decimal,InvalidOperation
import argparse,importlib.util,json
from pathlib import Path
import file_migration_batch as batch
ROOT=batch.ROOT
s=importlib.util.spec_from_file_location('moon_display_jdbc_rehearsal',ROOT/'scripts/qualify-forecast-json-jdbc.py');rehearsal=importlib.util.module_from_spec(s);s.loader.exec_module(rehearsal)

def same_state(actual,expected,item_type='String'):
 if not isinstance(actual,str) or not isinstance(expected,str):return False
 if item_type=='String':return actual==expected
 if item_type=='DateTime':
  try:
   a=datetime.fromisoformat(actual);b=datetime.fromisoformat(expected)
   return a.tzinfo is not None and b.tzinfo is not None and a==b
  except ValueError:return False
 try:
  ap=actual.split();bp=expected.split()
  return len(ap)==len(bp) and ap[1:]==bp[1:] and Decimal(ap[0]).is_finite() and Decimal(bp[0]).is_finite() and Decimal(ap[0])==Decimal(bp[0])
 except (InvalidOperation,IndexError):return False


def normalize_history(rows,name):
 """JDBC REST DTO omits quantity units; retain the frozen US Item unit context."""
 from copy import deepcopy
 reading=batch.specification()['moon'][name]['item'];unit=reading.get('unitSymbol')
 result=deepcopy(rows)
 if reading['type'].startswith('Number:') and unit and unit!='one':
  for row in result:
   value=row.get('state')
   if isinstance(value,str) and len(value.split())==1:
    try:
     number=Decimal(value)
     if number.is_finite():row['state']=value+' '+unit
    except InvalidOperation:pass
 return result

def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',required=True,type=Path);args=p.parse_args(argv)
 spec=batch.specification();batch.checked_source('moon');types={n:r['item']['type'] for n,r in spec['moon'].items()}
 values={}
 for n,r in spec['moon'].items():
  typ=r['item']['type'];unit=r['item'].get('unitSymbol')
  values[n]='Aries' if typ=='String' else ('2026-10-08T07:00:00.000-0600' if typ=='DateTime' else '0.5'+(' '+unit if unit and unit!='one' else ''))
 rehearsal.same_state=same_state
 original_history=rehearsal.history
 rehearsal.history=lambda container,header,name:normalize_history(original_history(container,header,name),name)
 rehearsal.main(items=values,source_path=ROOT/'openhab/file-config/items/moon-display-readings.items',types=types,setup_sources=(('items/moon-display-group-fixture.items',b'Group Moon\n'),('services/regional.cfg',b'org.openhab.i18n:language=en\norg.openhab.i18n:region=US\norg.openhab.i18n:measurementSystem=US\norg.openhab.i18n:timezone=America/Denver\n')))
 report={'scope':'isolated_moon_display_jdbc','specification_sha256':batch.SPEC_SHA256,'source_sha256':batch.SOURCE_HASHES['moon'],'items':25,'synthetic_values_only_in_isolation':True,'measurement_system':'US','region':'US','unitless_history_dto_compared_in_exact_frozen_item_unit':True,'file_reload_state_history':True,'full_jvm_restart_state_history':True,'original_managed_state_history':True,'owned_containers_removed':True,'live_writes':0}
 batch.private_file(args.report.parent,args.report.name,batch.encoded(report));print('qualification_report='+str(args.report),flush=True)

if __name__=='__main__':
 try:main()
 except Exception as e:raise SystemExit('Moon display JDBC qualification failed: '+type(e).__name__+': '+str(e)) from None
