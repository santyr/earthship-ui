"""Tiny synthetic source-receipt binding checks; no SQL, dump or restore."""
from datetime import datetime,timedelta,timezone
from hashlib import sha256
from pathlib import Path
import json
import pytest
from thermal_model.forcing_capture import _canonical
from thermal_journal_transfer import prepare_journal_transfer,read_journal_transfer

NOW=datetime(2026,10,1,12,tzinfo=timezone.utc)


def module():
    import thermal_journal_source_receipt
    return thermal_journal_source_receipt


def generation(tmp_path):
    stage=tmp_path/'stage';stage.mkdir(mode=0o700)
    archive=stage/'journal.dump';archive.write_bytes(b'PGDMPsynthetic');archive.chmod(0o600)
    transfers=stage/'transfer';transfers.mkdir(mode=0o700)
    package=prepare_journal_transfer(archive=archive,directory=transfers,source_schema='v2',runtime_role='fixture_reader',
        table_proofs={name:{'rows':1,'sha256':'a'*64} for name in ('message_receipts','action_events','mode_events')},
        exported_at=NOW-timedelta(seconds=1),source_code_revision='c'*64,clock=lambda:NOW)
    transfer=read_journal_transfer(package);archive.unlink()
    record=dict(schema='earthship-thermal-journal-source-export/v1',observed_at=(NOW-timedelta(seconds=1)).isoformat(),prepared_at=NOW.isoformat(),
        source_schema_version='v2',source_schema_fingerprint=transfer['source_schema_fingerprint'],runtime_role='fixture_reader',
        snapshot_identity='00000003-0000001B-1',source_code_revision='c'*64,configuration_binding_sha256='d'*64,
        archive_sha256=transfer['archive_sha256'],archive_bytes=transfer['archive_bytes'],table_proofs=transfer['table_proofs'],
        transfer_sha256=transfer['transfer_sha256'],source_snapshot_observed=True,source_export_authenticated=False,
        restored=False,installed=False,release_authorized=False,automatic_actuation=False)
    record['source_receipt_sha256']=sha256(_canonical(record)).hexdigest()
    path=stage/'source-receipt.json';path.write_bytes(_canonical(record));path.chmod(0o600)
    root=tmp_path/record['source_receipt_sha256'];stage.rename(root)
    return root,record


def read(root,record):
    return module().read_source_export(root,expected_receipt_sha256=record['source_receipt_sha256'],expected_exporter_revision='c'*64,now=NOW)


def rewrite(root,record):
    record['source_receipt_sha256']=sha256(_canonical({key:value for key,value in record.items() if key!='source_receipt_sha256'})).hexdigest()
    target=root.parent/record['source_receipt_sha256'];root.rename(target)
    (target/'source-receipt.json').write_bytes(_canonical(record))
    return target


def test_original_receipt_binds_one_exact_private_transfer(tmp_path):
    root,record=generation(tmp_path)
    assert read(root,record)==record
    assert read(root,record)['source_export_authenticated'] is False


@pytest.mark.parametrize('damage',['pin','code_pin','archive','extra','public','duplicate'])
def test_changed_original_refuses_before_use(tmp_path,damage):
    root,record=generation(tmp_path)
    if damage=='pin':record['source_receipt_sha256']='f'*64
    elif damage=='code_pin':
        with pytest.raises(ValueError):module().read_source_export(root,expected_receipt_sha256=record['source_receipt_sha256'],expected_exporter_revision='f'*64,now=NOW)
        return
    elif damage=='archive':(root/'transfer'/record['transfer_sha256']/'journal.dump').write_bytes(b'PGDMPchanged')
    elif damage=='extra':(root/'extra').write_bytes(b'unexpected')
    elif damage=='public':(root/'source-receipt.json').chmod(0o644)
    else:
        raw=(root/'source-receipt.json').read_bytes();(root/'source-receipt.json').write_bytes(raw[:-1]+b',"source_snapshot_observed":true}')
    with pytest.raises(ValueError):read(root,record)


@pytest.mark.parametrize('damage',['authority','restored','installed','release_authorized','automatic_actuation','rows','role','schema','observed','prepared','snapshot'])
def test_rehashed_receipt_cannot_relabel_transfer_or_claim_authority(tmp_path,damage):
    root,record=generation(tmp_path)
    if damage=='authority':record['source_export_authenticated']=True
    elif damage in ('restored','installed','release_authorized','automatic_actuation'):record[damage]=True
    elif damage=='rows':record['table_proofs']['action_events']['rows']=2
    elif damage=='role':record['runtime_role']='other_reader'
    elif damage=='schema':record['source_schema_version']='v1'
    elif damage=='observed':record['observed_at']=(NOW+timedelta(seconds=1)).isoformat()
    elif damage=='prepared':record['prepared_at']=(NOW+timedelta(seconds=1)).isoformat()
    else:record['snapshot_identity']='invalid snapshot'
    root=rewrite(root,record)
    with pytest.raises(ValueError):read(root,record)
