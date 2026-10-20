"""Rebuild public source inventory; static discovery is not execution evidence."""
import ast,json,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
OUTPUT=Path(__file__).with_name('inventory.json')
paths=subprocess.check_output(['git','ls-files'],cwd=ROOT,text=True).splitlines()
record=json.loads(OUTPUT.read_text())
record.update(audited_source_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
 public_tracked_files=len(paths),inventory_method='tracked public source only; discovery does not prove activation, execution or qualification',
 components=[p for p in paths if p.startswith('src/') and p.endswith('.svelte')],
 service_units=[p for p in paths if p.startswith('deploy/') and p.endswith(('.service','.timer','.service.in','.timer.in'))],
 item_definitions={},binding_link_files={},proxy_and_report_paths={},schema_contracts={},model_entry_points=[],archive_contract_modules=[])
for name in paths:
 p=ROOT/name
 if name.startswith('openhab/') and name.endswith('.items'):
  text=p.read_text();record['item_definitions'][name]=re.findall(r'^\s*(?:Switch|String|Contact|DateTime|Rollershutter|Dimmer|Color|Number(?::\w+)?|Group(?::\w+)*)\s+(\w+)',text,re.M)
  count=len(re.findall(r'channel\s*=',text))
  if count:record['binding_link_files'][name]={'links':count,'identities':'see original tracked source; identifiers not duplicated in audit'}
 if name.endswith('.things'):
  record['binding_link_files'][name]={'thing_declarations':len(re.findall(r'^\s*(?:Thing|Bridge)\s+',p.read_text(),re.M)),'identities':'see original tracked source'}
 if name.startswith('src/') or name=='vite.config.js':
  if p.suffix in ('.js','.svelte'):
   routes=sorted(set(re.findall(r'''["'](/(?:api|rest)/[A-Za-z0-9_./:-]+)["']''',p.read_text())))
   if routes:record['proxy_and_report_paths'][name]=routes
 if name.startswith(('openhab/scripts/','src/','services/')) and p.suffix in ('.py','.js','.svelte','.json') and '/tests/' not in name and not p.name.startswith('test_'):
  schemas=sorted(set(re.findall(r'earthship-[a-zA-Z0-9_-]+/v[0-9]+',p.read_text())))
  if schemas:record['schema_contracts'][name]=schemas
 if name.startswith('openhab/scripts/') and p.suffix=='.py' and not p.name.startswith('test_'):
  if any(word in p.name for word in ('archive','replay','source_bundle','training_dataset','receipt')):record['archive_contract_modules'].append(name)
  try:tree=ast.parse(p.read_text())
  except SyntaxError:continue
  if any(isinstance(n,ast.If) and '__name__' in ast.unparse(n.test) and '__main__' in ast.unparse(n.test) for n in tree.body):record['model_entry_points'].append(name)
record['javascript_tests']=[p for p in paths if p.startswith('tests/') and p.endswith(('.test.js','.spec.js','.test.mjs'))]
record['python_tests']=[p for p in paths if p.endswith('.py') and (Path(p).name.startswith('test_') or Path(p).name.endswith('_test.py'))]
OUTPUT.write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({key:len(value) for key,value in record.items() if isinstance(value,(list,dict))}))
