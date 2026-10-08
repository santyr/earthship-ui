"""Tiny local subprocess fixtures only; never execute pg_dump or access a DB."""
from pathlib import Path
from hashlib import sha256
import subprocess,sys
import pytest


def module():
    import thermal_journal_dump
    return thermal_journal_dump


def inputs(tmp_path):
    return dict(target=tmp_path/'journal.dump',params=dict(host='127.0.0.1',port='5432',dbname='openhab',user='fixture_reader',password='synthetic-only'),snapshot='00000003-0000001B-1')


def child(monkeypatch,code):
    source=module();real=subprocess.Popen;calls=[]
    def launch(argv,**kwargs):
        calls.append((argv,kwargs))
        return real([sys.executable,'-c',code],**kwargs)
    monkeypatch.setattr(source.subprocess,'Popen',launch)
    return calls


def test_dump_retains_exact_bounded_bytes_with_private_credentials(tmp_path,monkeypatch):
    calls=child(monkeypatch,"import os; os.write(1,b'PGDMPsynthetic')")
    data=inputs(tmp_path);result=module().dump_journal(**data)
    assert data['target'].read_bytes()==b'PGDMPsynthetic'
    assert result=={'bytes':14,'sha256':sha256(b'PGDMPsynthetic').hexdigest()}
    assert data['target'].stat().st_mode&0o777==0o600
    assert calls[0][0][0]=='/usr/bin/pg_dump'
    assert 'synthetic-only' not in ' '.join(calls[0][0])
    assert calls[0][1]['env']['PGPASSWORD']=='synthetic-only'
    assert calls[0][1]['start_new_session'] is True


@pytest.mark.parametrize('code',["import os; os.write(1,b'PGDMP'+b'x'*50)","import os; os.write(1,b'bad dump')","raise SystemExit(1)"])
def test_invalid_or_oversized_dump_leaves_no_partial_archive(tmp_path,monkeypatch,code):
    child(monkeypatch,code);monkeypatch.setattr(module(),'MAX_ARCHIVE_BYTES',20)
    data=inputs(tmp_path)
    with pytest.raises(ValueError):module().dump_journal(**data)
    assert not data['target'].exists()


def test_blocking_dump_hits_deadline_and_cleans_partial_file(tmp_path,monkeypatch):
    child(monkeypatch,"import time; time.sleep(20)")
    monkeypatch.setattr(module(),'DUMP_SECONDS',1)
    data=inputs(tmp_path)
    with pytest.raises(ValueError,match='deadline'):module().dump_journal(**data)
    assert not data['target'].exists()


@pytest.mark.parametrize('damage',['snapshot','host','role','existing'])
def test_invalid_request_never_launches_a_process(tmp_path,monkeypatch,damage):
    data=inputs(tmp_path)
    if damage=='snapshot':data['snapshot']='unsafe --argument'
    elif damage=='host':data['params']['host']='192.0.2.1'
    elif damage=='role':data['params']['user']='postgres'
    else:data['target'].write_bytes(b'original')
    monkeypatch.setattr(module().subprocess,'Popen',lambda *args,**kwargs:pytest.fail('invalid dump launched'))
    with pytest.raises((ValueError,FileExistsError)):module().dump_journal(**data)
    if damage=='existing':assert data['target'].read_bytes()==b'original'


def test_replaced_destination_is_never_removed_as_partial_output(tmp_path,monkeypatch):
    data=inputs(tmp_path);child(monkeypatch,"import os; os.write(1,b'PGDMPsynthetic')")
    class Changed:
        done=False
        def reserve(self,amount):
            if not self.done:
                self.done=True;data['target'].unlink();data['target'].write_bytes(b'foreign replacement')
    monkeypatch.setattr(module(),'_pacer',lambda rate:Changed())
    with pytest.raises(ValueError,match='target changed'):module().dump_journal(**data)
    assert data['target'].read_bytes()==b'foreign replacement'


def test_timeout_cleans_owned_descendant_holding_the_pipe(tmp_path,monkeypatch):
    import time
    pin=tmp_path/'descendant.pid'
    code="import os,time; from pathlib import Path; child=os.fork(); Path("+repr(str(pin))+").write_text(str(child)) if child else time.sleep(20)"
    child(monkeypatch,code);monkeypatch.setattr(module(),'DUMP_SECONDS',1)
    with pytest.raises(ValueError,match='deadline'):module().dump_journal(**inputs(tmp_path))
    process=Path('/proc')/pin.read_text()/'stat';deadline=time.monotonic()+1
    while process.exists():
        try:state=process.read_text().rsplit(')',1)[1].split()[0]
        except FileNotFoundError:break
        if state=='Z':break
        assert time.monotonic()<deadline,'owned descendant remained alive'
        time.sleep(.01)


def test_pipe_reads_are_reserved_before_receiving_bytes(tmp_path,monkeypatch):
    source=module();real=subprocess.Popen;owned=[];credits=[];reads=[]
    def launch(argv,**kwargs):
        process=real([sys.executable,'-c',"import os; os.write(1,b'PGDMPsynthetic')"],**kwargs)
        owned.append(process.stdout.fileno());return process
    class Pace:
        def reserve(self,amount):credits.append(amount)
    read=source.os.read
    def measured(fd,amount):
        if fd in owned:
            assert credits and credits.pop(0)>=amount
            reads.append(amount)
        return read(fd,amount)
    monkeypatch.setattr(source.subprocess,'Popen',launch)
    monkeypatch.setattr(source,'_pacer',lambda rate:Pace())
    monkeypatch.setattr(source.os,'read',measured)
    result=source.dump_journal(**inputs(tmp_path))
    assert result['bytes']==14 and reads
