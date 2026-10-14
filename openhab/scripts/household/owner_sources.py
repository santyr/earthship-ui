"""Read-only rule-engine observations; no inference of physical permission."""
from datetime import timedelta
from hashlib import sha256
from .codec import canonical,loads
from .capabilities import CapabilityRegistry
from .evidence import digest,utc
from .control_contracts import instant

ENDPOINT='/rules?summary=true'
MAX_RAW_BYTES=65536
SOURCE_FIELDS={'schema','endpoint','raw','sha256','requested_at','received_at'}


def coordination_from_rules(source,*,snapshot_id,registry,horizon_hours,as_of):
    digest(snapshot_id);as_of=utc(as_of)
    if not isinstance(registry,CapabilityRegistry) or type(horizon_hours) is not int or horizon_hours not in (6,12,24):
        raise ValueError('original registry and supported horizon required')
    result=dict(schema='earthship-shadow-coordination/v2',snapshotId=snapshot_id,horizonHours=horizon_hours,
        baseline_soc_floor=None,facts={},owner_source=source)
    if source is None:return result
    if not isinstance(source,dict) or set(source)!=SOURCE_FIELDS or source['schema']!='earthship-household-owner-source/v1' or source['endpoint']!=ENDPOINT:
        raise ValueError('closed original owner source required')
    raw=source['raw']
    if not isinstance(raw,str) or not 1<=len(raw.encode())<=MAX_RAW_BYTES or sha256(raw.encode()).hexdigest()!=source['sha256']:
        raise ValueError('original owner response differs')
    requested,received=instant(source['requested_at']),instant(source['received_at'])
    if not requested<=received<=as_of or received-requested>timedelta(seconds=10):
        raise ValueError('original owner collection clock differs')
    wrapped=loads('{"rules":'+raw+'}')
    if set(wrapped)!={'rules'}:raise ValueError('one original rule array required')
    rows=wrapped['rules']
    if not isinstance(rows,list) or len(rows)>256:raise ValueError('bounded original rule summary required')
    owners={row['ownerRule'] for row in registry.to_dict()['capabilities'].values()}
    seen=set()
    for row in rows:
        if not isinstance(row,dict) or not isinstance(row.get('uid'),str) or not 1<=len(row['uid'])<=128 or row['uid'] in seen:
            raise ValueError('unique original rule identities required')
        seen.add(row['uid'])
        if row['uid'] not in owners:continue
        status=row.get('status')
        if not isinstance(status,dict):continue
        state,detail=status.get('status'),status.get('statusDetail')
        ready=None
        if state in ('IDLE','RUNNING') and detail=='NONE':ready=True
        elif state=='UNINITIALIZED' and detail in ('DISABLED','HANDLER_MISSING_ERROR','HANDLER_INITIALIZING_ERROR','CONFIGURATION_ERROR'):
            ready=False
        # Start the freshness window at the request: response latency never
        # renews the observation. Engine RUNNING does not mean equipment busy.
        until=requested+timedelta(seconds=120)
        if ready is None or as_of>=until:continue
        fact=canonical(dict(schema='earthship-shadow-coordination-fact/v1',kind='owner_available',owner=row['uid'],
            value=ready,snapshotId=snapshot_id,horizonHours=horizon_hours,receivedAt=requested.isoformat(),
            validUntil=until.isoformat(),scope='declared_shadow_bounds')).decode()
        result['facts'][row['uid']]={'owner_available':dict(raw=fact,sha256=sha256(fact.encode()).hexdigest())}
    return loads(canonical(result))


def validate_coordination(value,*,snapshot_id,registry,horizon_hours,as_of):
    if not isinstance(value,dict) or set(value)!={'schema','snapshotId','horizonHours','baseline_soc_floor','facts','owner_source'}:
        raise ValueError('closed source-bound coordination required')
    expected=coordination_from_rules(value['owner_source'],snapshot_id=snapshot_id,registry=registry,horizon_hours=horizon_hours,as_of=as_of)
    if canonical(value)!=canonical(expected):raise ValueError('owner facts differ from original rule observation')
    return {**{key:val for key,val in expected.items() if key!='owner_source'},'schema':'earthship-shadow-coordination/v1'}
