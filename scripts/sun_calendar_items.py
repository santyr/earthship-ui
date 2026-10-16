"""Frozen Sun calendar display definitions and closed definition-only scope."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json
from urllib.parse import quote
import file_migration_batch as batch
ROOT=Path(__file__).resolve().parents[1]
SPEC=ROOT/'openhab/file-config/sun-calendar-migration.json'
SOURCE=ROOT/'openhab/file-config/items/sun-calendar.items'
SPEC_SHA='a7cc027a6f305fc60b30797602e1143443ef27078940cc6c6004045c79e5723d'
SOURCE_SHA='68c8ed3796472e10b649c6a2906f7809d178f535af1ce37daa6be593a513b4f9'
IDS={'Sun_Spring':80,'Sun_Summer':81,'Sun_Autumn':82,'Sun_Winter':83,
     'Sun_RingEclipse':89,'Sun_TotalEclipse':86,'Sun_PartialEclipse':87,
     'Sun_Eclipse_PartialElevation':88}
require=batch.require

def specification():
    require(not SPEC.is_symlink(),'specification symlink')
    body=SPEC.read_bytes();require(sha256(body).hexdigest()==SPEC_SHA,'specification drift')
    rows=json.loads(body)
    require({n:r['jdbc_id'] for n,r in rows.items()}==IDS,'calendar scope/identity drift')
    return rows

def render(rows):
    require(set(rows)==set(IDS),'renderer scope drift')
    lines=['// Original Sun calendar and eclipse display identities; sole file provider after cutover.']
    for name,row in sorted(rows.items()):
        item=row['item'];link=row['link']
        require(item['name']==name and item['groupNames']==['Sun'] and item['tags']==['Point']
                and item['category'] is None and link['configuration']=={},'unsupported renderer descriptor')
        lines.append(item['type']+' '+name+' '+json.dumps(item['label'])+' (Sun) ["Point"] { channel='+json.dumps(link['channelUID'])+' }')
    return ('\n'.join(lines)+'\n').encode()

def checked_source():
    require(not SOURCE.is_symlink(),'source symlink')
    body=SOURCE.read_bytes()
    require(sha256(body).hexdigest()==SOURCE_SHA and body==render(specification()),'source drift')
    return body

def managed_item(name):
    require(name in IDS,'unknown calendar Item')
    return {k:deepcopy(specification()[name]['item'][k]) for k in batch.ITEM_WRITABLE}

def validate_item(item,name,*,managed):
    require(type(managed) is bool and name in IDS and isinstance(item,dict),'invalid calendar descriptor')
    require(item.get('editable') is managed and batch.item_definition(item)==specification()[name]['item'],
            'calendar descriptor/provider drift')
    require(isinstance(item.get('state'),str) and item['state'] not in ('','NULL','UNDEF'),'calendar state unavailable')

def validate_links(links,name,*,managed):
    require(type(managed) is bool and name in IDS and isinstance(links,list),'invalid link census')
    selected=[l for l in links if l.get('itemName')==name];expected=specification()[name]['link']
    require(len(selected)==1 and selected[0].get('editable') is managed
            and {k:selected[0].get(k) for k in expected}==expected,'calendar link/profile/provider drift')

def allowed_mutation(method,path,body):
    for name,row in specification().items():
        if path=='/items/'+name:
            if method=='DELETE' and body is None:return
            if method=='PUT' and body==managed_item(name):return
        if path=='/links/'+name+'/'+quote(row['link']['channelUID'],safe=''):
            if method=='DELETE' and body is None:return
            if method=='PUT' and body==row['link']:return
    raise RuntimeError('mutation outside exact calendar Item/link definitions')
