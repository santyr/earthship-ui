"""Private archive transfer inputs do not claim restore or consumer qualification."""
from pathlib import Path
from datetime import datetime,timezone
import json
from hashlib import sha256
from thermal_model.forcing_capture import _canonical
import pytest

NOW=datetime(2026,10,8,tzinfo=timezone.utc)


def module():
    import thermal_journal_transfer
    return thermal_journal_transfer


def inputs(tmp_path):
    archive=tmp_path/'export.dump';archive.write_bytes(b'PGDMP synthetic archive; not SQL qualification');archive.chmod(0o600)
    destination=tmp_path/'packages';destination.mkdir(mode=0o700)
    return dict(archive=archive,directory=destination,source_schema='v2',runtime_role='fixture_reader',
        table_proofs={name:dict(rows=0,sha256='a'*64) for name in ('action_events','message_receipts','mode_events')},
        exported_at=NOW,source_code_revision='b'*64,clock=lambda:NOW)


def test_transfer_roundtrip_retains_exact_archive_and_closed_flags(tmp_path):
    source=module();data=inputs(tmp_path);path=source.prepare_journal_transfer(**data)
    record=source.read_journal_transfer(path)
    assert (path/'journal.dump').read_bytes()==data['archive'].read_bytes()
    assert record['source_schema_version']=='v2'
    assert record['table_proofs']==data['table_proofs']
    assert path.name==record['transfer_sha256']
    for flag in ('disposable_restore_qualified','consumer_qualified','installed','release_authorized'):assert record[flag] is False
    assert (path/'journal.dump').stat().st_mode&0o777==0o600
    assert (path/'manifest.json').stat().st_mode&0o777==0o600


@pytest.mark.parametrize('damage',['archive','manifest','extra','address','flag'])
def test_changed_transfer_refuses_before_use(tmp_path,damage):
    source=module();path=source.prepare_journal_transfer(**inputs(tmp_path))
    if damage=='archive':(path/'journal.dump').write_bytes(b'PGDMP altered')
    elif damage=='extra':(path/'extra').write_bytes(b'extra')
    elif damage=='address':target=path.parent/('c'*64);path.rename(target);path=target
    else:
        record=json.loads((path/'manifest.json').read_text())
        record['release_authorized']=True if damage=='flag' else False
        if damage=='manifest':record['source_code_revision']='c'*64
        else:
            record['transfer_sha256']=sha256(_canonical({key:value for key,value in record.items() if key!='transfer_sha256'})).hexdigest()
            changed=path.parent/record['transfer_sha256'];path.rename(changed);path=changed
        (path/'manifest.json').write_text(json.dumps(record))
    with pytest.raises(ValueError):source.read_journal_transfer(path)


@pytest.mark.parametrize('damage',['public_archive','source_schema','role','tables','future','oversize'])
def test_invalid_source_refuses_before_copy(tmp_path,monkeypatch,damage):
    source=module();data=inputs(tmp_path)
    if damage=='public_archive':data['archive'].chmod(0o644)
    elif damage=='source_schema':data['source_schema']='auto'
    elif damage=='role':data['runtime_role']='postgres'
    elif damage=='tables':data['table_proofs'].pop('mode_events')
    elif damage=='future':data['exported_at']=NOW.replace(year=2027)
    else:monkeypatch.setattr(source,'MAX_ARCHIVE_BYTES',1)
    with pytest.raises(ValueError):source.prepare_journal_transfer(**data)
    assert list(data['directory'].iterdir())==[]


def test_growing_source_during_pacing_wait_never_reads_unreserved_bytes(tmp_path,monkeypatch):
    source=module();data=inputs(tmp_path);original=data['archive'].stat().st_size;amounts=[]
    class Pace:
        changed=False
        def reserve(self,amount):
            if not self.changed:
                self.changed=True;data['archive'].write_bytes(b'PGDMP'+b'x'*1000)
    monkeypatch.setattr(source,'_pacer',lambda rate:Pace())
    read=source.os.read
    def measured(fd,amount):amounts.append(amount);return read(fd,amount)
    monkeypatch.setattr(source.os,'read',measured)
    with pytest.raises(ValueError):source.prepare_journal_transfer(**data)
    assert amounts==[original+1]
    assert list(data['directory'].iterdir())==[]


def test_partial_manifest_failure_cleans_unpublished_generation(tmp_path,monkeypatch):
    source=module();data=inputs(tmp_path)
    def interrupted(path,raw):path.write_bytes(b'partial');raise OSError('controlled persistence failure')
    monkeypatch.setattr(source,'_write_private',interrupted)
    with pytest.raises(OSError):source.prepare_journal_transfer(**data)
    assert list(data['directory'].iterdir())==[]


def test_existing_transfer_is_never_replaced(tmp_path):
    source=module();data=inputs(tmp_path);path=source.prepare_journal_transfer(**data)
    original=(path/'manifest.json').read_bytes()
    with pytest.raises(ValueError):source.prepare_journal_transfer(**data)
    assert (path/'manifest.json').read_bytes()==original
    assert list(data['directory'].iterdir())==[path]


@pytest.mark.parametrize('rate',[None,False,0,1048577])
def test_transfer_pacing_cannot_be_disabled_or_increased(tmp_path,rate):
    source=module();data=inputs(tmp_path)
    with pytest.raises(ValueError):source.prepare_journal_transfer(**data,max_read_bytes_per_second=rate)
    assert list(data['directory'].iterdir())==[]


def test_source_replaced_between_initial_inspection_and_copy_refuses(tmp_path,monkeypatch):
    source=module();data=inputs(tmp_path);stream=source._stream
    def changed(path,pace,output=None,**kwargs):
        if output is not None:data['archive'].write_bytes(b'PGDMP replacement within byte limit')
        return stream(path,pace,output,**kwargs)
    monkeypatch.setattr(source,'_stream',changed)
    with pytest.raises(ValueError):source.prepare_journal_transfer(**data)
    assert list(data['directory'].iterdir())==[]


def test_manifest_read_requires_reserved_budget_before_io(tmp_path,monkeypatch):
    source=module();path=source.prepare_journal_transfer(**inputs(tmp_path))
    class Pace:
        available=0
        def reserve(self,amount):self.available+=amount
    pace=Pace();monkeypatch.setattr(source,'_pacer',lambda rate:pace)
    owned=source._owned_bytes
    def bounded_read(path,maximum):
        assert pace.available>=maximum+1,'manifest read exceeds reserved byte allowance'
        pace.available-=maximum+1
        return owned(path,maximum)
    monkeypatch.setattr(source,'_owned_bytes',bounded_read)
    assert source.read_journal_transfer(path)['release_authorized'] is False
