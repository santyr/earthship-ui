"""Closed observational sky diagnostic definitions; no network or live release path."""
from pathlib import Path
from datetime import datetime
import re
SOURCE=Path(__file__).resolve().parents[1]/'openhab/file-config/items/sky-diagnostics.items'
ITEMS={
 'SkyCondition_Diagnostic':{'type':'String','label':'Sky condition diagnostic','pattern':'%s','jdbc_id':541},
 'SkyCondition_LastEval':{'type':'DateTime','label':'Sky condition last eval','pattern':'%1$tF %1$tT','jdbc_id':540},
}
def require(condition,reason):
 if not condition:raise ValueError(reason)
def original_item(name):
 require(name in ITEMS,'unknown diagnostic Item');row=ITEMS[name]
 return {'name':name,'type':row['type'],'label':row['label'],'category':'','tags':[],'groupNames':['gWeatherHealth']}
def metadata(name):
 require(name in ITEMS,'unknown metadata scope');return {'value':' ','config':{'pattern':ITEMS[name]['pattern']}}
def validate_item(row,name,*,managed):
 require(type(managed) is bool and isinstance(row,dict),'invalid provider/descriptor')
 for key,value in original_item(name).items():
  require(row.get(key) in (None,'') if key=='category' else row.get(key)==value,'diagnostic descriptor drift: '+key)
 require(row.get('editable') is managed and not row.get('unitSymbol'),'diagnostic provider/unit drift')
 require(row.get('metadata')=={'stateDescription':{**metadata(name),'editable':managed}},'metadata ownership/definition drift')
 require(row.get('stateDescription')=={'pattern':ITEMS[name]['pattern'],'readOnly':False,'options':[]},'display semantics drift')
 state=row.get('state');require(isinstance(state,str) and state not in ('','NULL','UNDEF'),'diagnostic state unavailable')
 if ITEMS[name]['type']=='DateTime':
  require(re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:?\d{2})',state) is not None,'native DateTime syntax required')
  try:value=datetime.fromisoformat(state.replace('Z','+00:00'))
  except ValueError:raise ValueError('invalid native DateTime') from None
  require(value.tzinfo is not None,'DateTime timezone absent')
def validate_links(rows):
 require(isinstance(rows,list) and not any(row.get('itemName') in ITEMS for row in rows),'diagnostic Item unexpectedly linked')
def allowed_mutation(method,path,body):
 for name in ITEMS:
  if path=='/items/'+name:
   if method=='DELETE' and body is None:return
   if method=='PUT' and body==original_item(name):return
  if path=='/items/'+name+'/metadata/stateDescription':
   if method=='DELETE' and body is None:return
   if method=='PUT' and body==metadata(name):return
 raise ValueError('mutation outside exact diagnostic-definition scope')
