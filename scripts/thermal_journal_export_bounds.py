"""Bound journal row proofs in an existing read-only source snapshot.

No connection, dump, transfer, restore, installation or qualification authority.
The caller must separately audit the exact schema and retain the snapshot while
exporting. The original ordered PostgreSQL CSV bytes define each row digest.
"""
from hashlib import sha256
from time import monotonic
from thermal_model.environment_bundle import _pacer
from thermal_model.journal import ACTION_COLUMNS,MODE_COLUMNS

MAX_ROWS=10000
MAX_ROW_BYTES=2048
MAX_PROOF_BYTES=8388608
MAX_CHUNK_BYTES=16384
TABLES={'message_receipts':('idempotency_key',('idempotency_key','payload_digest','received_at','created_at')),
        'action_events':('event_id',ACTION_COLUMNS),'mode_events':('event_id',MODE_COLUMNS)}


class ProofBudget:
    def __init__(self,*,maximum=MAX_PROOF_BYTES,pace=None,clock=monotonic):
        if type(maximum) is not int or not 1<=maximum<=MAX_PROOF_BYTES:
            raise ValueError('bounded aggregate journal proof bytes required')
        self.maximum=maximum;self.used=0;self.pace=_pacer(1048576) if pace is None else pace
        self.clock=clock;self.deadline=clock()+70
    def check(self):
        if self.clock()>=self.deadline:raise ValueError('journal proof deadline exceeded')
    def writer(self):return _DigestWriter(self)


class _DigestWriter:
    def __init__(self,budget):self.budget=budget;self.digest=sha256()
    def write(self,value):
        self.budget.check()
        if not isinstance(value,(str,bytes)) or len(value)>MAX_CHUNK_BYTES:
            raise ValueError('bounded original COPY chunk required')
        raw=value.encode('utf-8') if isinstance(value,str) else value
        if len(raw)>MAX_CHUNK_BYTES or self.budget.used+len(raw)>self.budget.maximum:
            raise ValueError('journal proof byte budget exceeded')
        self.budget.pace.reserve(len(raw));self.budget.check()
        self.digest.update(raw);self.budget.used+=len(raw)
    def hexdigest(self):return self.digest.hexdigest()


def bounded_table_proofs(connection,*,budget=None):
    """Digest exact tables without permitting an unbounded source COPY."""
    budget=ProofBudget() if budget is None else budget
    budget.check();proofs={};sizes={}
    with connection.cursor() as cursor:
        cursor.execute('SHOW transaction_read_only')
        if cursor.fetchone()!=('on',):raise ValueError('read-only journal proof transaction required')
        cursor.execute('SHOW transaction_isolation')
        if cursor.fetchone()!=('repeatable read',):raise ValueError('one repeatable-read journal snapshot required')
        for setting in ('server_encoding','client_encoding'):
            cursor.execute('SHOW '+setting)
            if cursor.fetchone()!=('UTF8',):raise ValueError('UTF-8 server and client journal encoding required')
        cursor.execute("SET LOCAL statement_timeout='5s'")
        cursor.execute("SET LOCAL lock_timeout='1s'")
        cursor.execute("SET LOCAL TIME ZONE 'UTC'")
        cursor.execute('LOCK TABLE thermal_intel.action_events, thermal_intel.message_receipts, thermal_intel.mode_events IN ACCESS SHARE MODE')
        # Only trusted fixed identifiers enter these queries. A bounded ordered
        # prefix distinguishes an oversized table without scanning its tail.
        for table,(key,columns) in TABLES.items():
            budget.check()
            expression=' + '.join('COALESCE(octet_length('+column+'::text),0)::bigint' for column in columns)
            cursor.execute('SELECT count(*), COALESCE(max(row_bytes),0), COALESCE(sum(row_bytes),0)::bigint FROM '
                '(SELECT '+expression+' AS row_bytes FROM thermal_intel.'+table+' ORDER BY '+key+' LIMIT 10001) AS bounded_rows')
            count,largest,total=cursor.fetchone()
            if (any(type(value) is not int or value<0 for value in (count,largest,total)) or
                    count>MAX_ROWS or largest>MAX_ROW_BYTES):raise ValueError('journal source rows exceed export bounds')
            # CSV can double quotes; delimiters and timestamp/numeric rendering
            # fit within this conservative allowance per already bounded row.
            sizes[table]=(count,2*total+128*count)
        if sum(size for _,size in sizes.values())>budget.maximum-budget.used:
            raise ValueError('journal source exceeds aggregate proof budget')
        for table,(key,columns) in TABLES.items():
            budget.check();writer=budget.writer()
            cursor.copy_expert('COPY (SELECT * FROM thermal_intel.'+table+' ORDER BY '+key+') TO STDOUT WITH CSV',writer)
            budget.check();proofs[table]={'rows':sizes[table][0],'sha256':writer.hexdigest()}
    return proofs
