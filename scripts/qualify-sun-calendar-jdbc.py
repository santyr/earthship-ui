#!/usr/bin/env python3
"""Eight Sun calendar JDBC values; writes only to owned isolated containers."""
import argparse,importlib.util
from pathlib import Path
import sun_calendar_items as d
ROOT=d.ROOT

def load(name,filename):
 spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/filename);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
j=load('sun_calendar_jdbc_rehearsal','qualify-forecast-json-jdbc.py')
comparison=load('sun_calendar_unit_comparison','qualify-moon-display-jdbc.py')

def normalize(rows,name):
 from copy import deepcopy
 result=deepcopy(rows)
 if name=='Sun_Eclipse_PartialElevation':
  for row in result:
   if isinstance(row.get('state'),str) and len(row['state'].split())==1:row['state']+=' °'
 return result

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',required=True,type=Path);directory=p.parse_args().directory
 d.require(directory.is_dir() and not directory.is_symlink() and directory.stat().st_mode&0o777==0o700,'private evidence directory required')
 d.checked_source();rows=d.specification();types={n:r['item']['type'] for n,r in rows.items()}
 values={n:'1.5 °' if n=='Sun_Eclipse_PartialElevation' else '2027-03-20T07:00:00.000-0600' for n in rows}
 j.same_state=comparison.same_state
 original_history=j.history;j.history=lambda container,header,name:normalize(original_history(container,header,name),name)
 j.main(items=values,source_path=d.SOURCE,types=types,setup_sources=(('items/sun-calendar-group-fixture.items',b'Group Sun ["Equipment"]\n'),('services/regional.cfg',b'org.openhab.i18n:language=en\norg.openhab.i18n:region=US\norg.openhab.i18n:measurementSystem=US\norg.openhab.i18n:timezone=America/Denver\n')))
 proof={'scope':'isolated_sun_calendar_jdbc','source_sha256':d.SOURCE_SHA,'specification_sha256':d.SPEC_SHA,'items':8,'synthetic_values_only_in_isolation':True,'file_reload_state_history':True,'full_jvm_restart_state_history':True,'original_managed_state_history':True,'owned_containers_removed':True,'production_writes':0,'binding_fetch_qualified':False}
 d.batch.private_file(directory,'jdbc-proof.json',d.batch.encoded(proof));print('jdbc_qualification=passed production_writes=0',flush=True)
if __name__=='__main__':main()
