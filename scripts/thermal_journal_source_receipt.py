"""Verify pinned original source-export bytes and their private transfer binding.

Pins must be supplied independently through the approved private handoff.
Integrity verification alone does not authenticate the exporter or qualify SQL
restoration, the cold environment, installation or production release.
"""
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
import json,re
from thermal_model.forcing_capture import _canonical,_private_directory
from thermal_model.origin_capture import _object
from thermal_model.runtime_bundle import _owned_bytes
from thermal_model.environment_bundle import _pacer
from thermal_model.graduation_policy import _sha,_utc
from thermal_journal_transfer import read_journal_transfer,_declarations

SCHEMA='earthship-thermal-journal-source-export/v1'
FLAGS={'source_export_authenticated','restored','installed','release_authorized','automatic_actuation'}
FIELDS={'schema','observed_at','prepared_at','source_schema_version','source_schema_fingerprint','runtime_role',
        'snapshot_identity','source_code_revision','configuration_binding_sha256','archive_sha256','archive_bytes',
        'table_proofs','transfer_sha256','source_snapshot_observed','source_receipt_sha256'}|FLAGS
MAX_RECEIPT_BYTES=16000


def read_source_export(generation,*,expected_receipt_sha256,expected_exporter_revision,now=None):
    expected=_sha(expected_receipt_sha256);revision=_sha(expected_exporter_revision)
    root=_private_directory(Path(generation))
    if root.name!=expected or {entry.name for entry in root.iterdir()}!={'source-receipt.json','transfer'}:
        raise ValueError('exact pinned source generation required')
    _pacer(1048576).reserve(MAX_RECEIPT_BYTES+1)
    def nonfinite(_):raise ValueError('nonfinite source receipt refused')
    record=json.loads(_owned_bytes(root/'source-receipt.json',MAX_RECEIPT_BYTES),object_pairs_hook=_object,parse_constant=nonfinite)
    if (not isinstance(record,dict) or set(record)!=FIELDS or record['schema']!=SCHEMA or
            record['source_snapshot_observed'] is not True or any(record[key] is not False for key in FLAGS)):
        raise ValueError('closed original source observation receipt required')
    body={key:value for key,value in record.items() if key!='source_receipt_sha256'}
    if record['source_receipt_sha256']!=expected or sha256(_canonical(body)).hexdigest()!=expected:
        raise ValueError('original source receipt pin differs')
    if record['source_code_revision']!=revision:raise ValueError('original exporter code pin differs')
    for field in ('configuration_binding_sha256','archive_sha256','transfer_sha256'):_sha(record[field])
    if (not isinstance(record['snapshot_identity'],str) or
            re.fullmatch('[0-9A-F]{8}-[0-9A-F]{8}-[1-9][0-9]{0,9}',record['snapshot_identity']) is None):
        raise ValueError('original exported snapshot identity required')
    observed,prepared=map(_utc,(record['observed_at'],record['prepared_at']))
    assessment=_utc(datetime.now(timezone.utc) if now is None else now)
    if not observed<=prepared<=assessment:raise ValueError('source observation clock order invalid')
    expected_fingerprint=_declarations(record['source_schema_version'],record['runtime_role'],record['table_proofs'],revision)
    if (record['source_schema_fingerprint']!=expected_fingerprint or type(record['archive_bytes']) is not int or
            not 5<=record['archive_bytes']<=32000000):raise ValueError('bounded exact source declaration required')
    transfers=_private_directory(root/'transfer')
    if {entry.name for entry in transfers.iterdir()}!={record['transfer_sha256']}:
        raise ValueError('one original source transfer required')
    transfer=read_journal_transfer(transfers/record['transfer_sha256'])
    for field in ('source_schema_version','source_schema_fingerprint','runtime_role','source_code_revision','archive_sha256','archive_bytes','table_proofs','transfer_sha256'):
        if transfer[field]!=record[field]:raise ValueError('original source and retained transfer differ')
    if _utc(transfer['exported_at'])!=observed or not observed<=_utc(transfer['prepared_at'])<=prepared:
        raise ValueError('original transfer clock binding differs')
    return record
