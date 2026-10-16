"""Replay original greywater policy observations without authorizing equipment."""
from datetime import timedelta
from hashlib import sha256
import re
from .codec import canonical,loads
from .evidence import utc
from .control_contracts import instant

OWNER='hex_southoutlet_cycle'
RULE_ENDPOINT='/rules/'+OWNER
STATUS_ENDPOINT='/items/SouthOutlet_AutoStatus/state'
RULE_SHA256='4c34780e544d80af8eb36d047a949fa30e0198bb50fa57650285052db3c52d9b'
SOURCE_FIELDS={'schema','rule_before','status','rule_after'}
ROW_FIELDS={'endpoint','raw','sha256','requested_at','received_at'}
BLOCKERS={'after_dark':'curfew_allowed','cooldown_wait':'cooldown_ready','cooldown_initialized':'cooldown_ready',
          'cycle_started':'owner_idle','cycle_active':'owner_idle','busy':'owner_idle'}
PREDICTABLE={'cycle_started','cycle_active','cycle_completed','cooldown_wait','cooldown_initialized'}


def _original(row,endpoint,maximum):
    if not isinstance(row,dict) or set(row)!=ROW_FIELDS or row['endpoint']!=endpoint:
        raise ValueError('closed fixed original policy response required')
    raw=row['raw']
    if not isinstance(raw,str) or not 1<=len(raw.encode())<=maximum or sha256(raw.encode()).hexdigest()!=row['sha256']:
        raise ValueError('bounded original policy bytes differ')
    requested,received=instant(row['requested_at']),instant(row['received_at'])
    if not requested<=received or received-requested>timedelta(seconds=10):
        raise ValueError('original policy response clock differs')
    return raw,requested,received


def observe_policy(source,*,registry,as_of):
    """Return a fresh observed decision, or unknown for an unsupported policy.

    Bracket the status read with stable original rule definitions. The embedded
    evaluation time, not the later GET, starts freshness. Scheduling hints are
    conditional observations and never reservations or physical readiness.
    """
    as_of=utc(as_of)
    if source is None:return None
    if not isinstance(source,dict) or set(source)!=SOURCE_FIELDS or source['schema']!='earthship-greywater-policy-source/v1':
        raise ValueError('closed original greywater policy source required')
    before,bq,br=_original(source['rule_before'],RULE_ENDPOINT,65536)
    raw,sq,sr=_original(source['status'],STATUS_ENDPOINT,2048)
    after,aq,ar=_original(source['rule_after'],RULE_ENDPOINT,65536)
    if not bq<=br<=sq<=sr<=aq<=ar<=as_of or ar-bq>timedelta(seconds=10):
        raise ValueError('bracketed original policy chronology differs')
    first,last=loads(before),loads(after)
    fields=('uid','configuration','triggers','conditions','actions')
    if first.get('uid')!=OWNER or any(first.get(k)!=last.get(k) for k in fields):
        raise ValueError('owner policy changed during observation')
    if first.get('conditions')!=[]:raise ValueError('unrecognized outer owner policy conditions')
    actions=first.get('actions')
    if not isinstance(actions,list) or len(actions)!=1 or not isinstance(actions[0],dict):
        raise ValueError('single original script action required')
    config=actions[0].get('configuration')
    if (actions[0].get('type')!='script.ScriptAction' or not isinstance(config,dict) or
            config.get('type')!='application/javascript' or not isinstance(config.get('script'),str)):
        raise ValueError('original JavaScript policy required')
    if sha256(config['script'].encode()).hexdigest()!=RULE_SHA256:return None
    capability=registry.to_dict()['capabilities'].get('greywater-request-v1')
    if (capability is None or capability['ownerRule']!=OWNER or
            not {'SouthOutlet_Outlet2_Switch','East_Bed_Socket_Outlet_2_Power'}<=set(capability['protectedActuators']) or
            'BMS_SOC_Evidence_JSON' not in capability['safetyInputs']):
        raise ValueError('original policy ownership differs from registry')
    values={}
    for part in raw.split(','):
        key,separator,value=part.partition('=')
        if (not separator or key in values or not re.fullmatch('[A-Za-z][A-Za-z0-9]{0,63}',key) or
                not value or len(value)>256 or any(ord(c)<32 or ord(c)==127 for c in value)):
            raise ValueError('unambiguous original owner status required')
        values[key]=value
    if (values.get('scheduleVersion')!='1' or not re.fullmatch('[a-z_]{1,64}',values.get('reason','')) or
            values.get('scheduling') not in ('blocked','conditional','unavailable')):
        raise ValueError('versioned original scheduling observation required')
    evaluated=instant(values.get('evaluatedAt',''))
    if evaluated>sr:raise ValueError('owner evaluation unavailable at original status read')
    scheduling=values['scheduling'];reason=values['reason'];next_at=None;next_pump=None
    if scheduling=='conditional':
        if reason not in PREDICTABLE:raise ValueError('conditional owner reason differs')
        next_at=instant(values.get('nextEligibleAt',''));next_pump=values.get('nextPump')
        if not evaluated<=next_at<=evaluated+timedelta(hours=1) or next_pump not in ('south','east'):
            raise ValueError('bounded original conditional schedule required')
    elif 'nextEligibleAt' in values or 'nextPump' in values:
        raise ValueError('nonconditional owner status has scheduling hint')
    elif (reason in PREDICTABLE)!=(scheduling=='unavailable'):
        raise ValueError('original scheduling classification differs')
    until=evaluated+timedelta(seconds=120)
    if as_of>=until:return None
    return dict(owner=OWNER,reason=reason,evaluated_at=evaluated.isoformat(),valid_until=until.isoformat(),
        scheduling=scheduling,next_eligible_at=None if next_at is None else next_at.isoformat(),next_pump=next_pump,
        source_sha256=sha256(canonical(source)).hexdigest(),rule_sha256=RULE_SHA256,physical_permission=False)
