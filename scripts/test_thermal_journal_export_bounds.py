"""Synthetic proof-stream checks; no database connections or restores."""
from hashlib import sha256
import pytest


def module():
    import thermal_journal_export_bounds
    return thermal_journal_export_bounds


class Pace:
    def __init__(self):self.reserved=[]
    def reserve(self,size):self.reserved.append(size)


def test_hashing_retains_original_unicode_csv_and_paces_exact_bytes():
    pace=Pace();budget=module().ProofBudget(pace=pace)
    writer=budget.writer();writer.write('fixture,é\n');writer.write(b'next,row\n')
    assert writer.hexdigest()==sha256('fixture,é\nnext,row\n'.encode()).hexdigest()
    assert pace.reserved==[11,9]


def test_shared_byte_limit_refuses_before_hash_or_pacing():
    pace=Pace();budget=module().ProofBudget(pace=pace,maximum=12)
    first=budget.writer();first.write(b'12345678');second=budget.writer()
    with pytest.raises(ValueError):second.write(b'ABCDE')
    assert pace.reserved==[8]
    assert second.hexdigest()==sha256(b'').hexdigest()


class Cursor:
    def __init__(self,connection):self.connection=connection
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def execute(self,query):self.query=query;self.connection.queries.append(query)
    def fetchone(self):
        if self.query.startswith('SHOW transaction_read_only'):return (self.connection.readonly,)
        if self.query.startswith('SHOW transaction_isolation'):return (self.connection.isolation,)
        if self.query.startswith('SHOW server_encoding'):return (self.connection.server_encoding,)
        if self.query.startswith('SHOW client_encoding'):return (self.connection.client_encoding,)
        return self.connection.sizes
    def copy_expert(self,query,writer):
        self.connection.copies.append(query);writer.write(b'fixture,row\n')


class Connection:
    def __init__(self):
        self.readonly='on';self.isolation='repeatable read';self.server_encoding='UTF8';self.client_encoding='UTF8';self.sizes=(1,20,20);self.queries=[];self.copies=[]
    def cursor(self):return Cursor(self)


def test_all_table_hashes_preserve_order_and_share_one_bounded_stream():
    connection=Connection();pace=Pace()
    result=module().bounded_table_proofs(connection,budget=module().ProofBudget(pace=pace))
    assert set(result)=={'action_events','message_receipts','mode_events'}
    assert all(value=={'rows':1,'sha256':sha256(b'fixture,row\n').hexdigest()} for value in result.values())
    assert len(connection.copies)==3 and len(pace.reserved)==3
    assert all('ORDER BY' in query for query in connection.copies)


@pytest.mark.parametrize('damage',['write','isolation','rows','row_bytes','total_bytes'])
def test_bad_transaction_or_oversized_source_refuses_before_copy(damage):
    connection=Connection()
    if damage=='write':connection.readonly='off'
    elif damage=='isolation':connection.isolation='read committed'
    elif damage=='rows':connection.sizes=(10001,20,200020)
    elif damage=='row_bytes':connection.sizes=(1,2049,2049)
    else:connection.sizes=(10000,1000,10000000)
    with pytest.raises(ValueError):module().bounded_table_proofs(connection,budget=module().ProofBudget(pace=Pace()))
    assert connection.copies==[]


def test_pacing_delay_cannot_cross_deadline_and_emit_proof_bytes():
    now=[0]
    class Delayed:
        def reserve(self,size):now[0]=71
    budget=module().ProofBudget(pace=Delayed(),clock=lambda:now[0]);writer=budget.writer()
    with pytest.raises(ValueError):writer.write(b'bounded original')
    assert writer.hexdigest()==sha256(b'').hexdigest()


@pytest.mark.parametrize('value',['é'*8193,b'x'*16385])
def test_overlong_copy_chunk_refuses_without_pacing(value):
    pace=Pace();writer=module().ProofBudget(pace=pace).writer()
    with pytest.raises(ValueError):writer.write(value)
    assert pace.reserved==[] and writer.hexdigest()==sha256(b'').hexdigest()


@pytest.mark.parametrize('side',['server_encoding','client_encoding'])
def test_non_utf8_encoding_refuses_before_copy(side):
    connection=Connection();setattr(connection,side,'LATIN1')
    with pytest.raises(ValueError,match='UTF-8'):
        module().bounded_table_proofs(connection,budget=module().ProofBudget(pace=Pace()))
    assert connection.copies==[]
