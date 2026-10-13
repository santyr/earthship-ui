"""Offline deterministic extraction; this module does not train or install models."""
from .contract import instant, canonical, digest
from datetime import timedelta


def chronological_split(rows,*,cutoff,purge_seconds):
    cutoff=instant(cutoff)
    if type(purge_seconds) is not int or not 1<=purge_seconds<=604800:
        raise ValueError('explicit leakage-purge horizon required')
    if any(row.get('synthetic') is not False for row in rows):
        raise ValueError('synthetic or unspecified provenance refused for model evaluation')
    ordered=sorted(rows,key=lambda row:instant(row['observed_at']))
    train=[row for row in ordered if instant(row['observed_at'])<cutoff-timedelta(seconds=purge_seconds)]
    test=[row for row in ordered if instant(row['observed_at'])>=cutoff]
    return train,test


def replay(engine,events):
    decisions=[]
    for event in events:
        decisions.append(engine.ingest(event['raw'],event['topic'],received_at=instant(event['received_at']),retained=event.get('retained',False)))
    observations=[{k:v for k,v in row.items() if k not in ('raw_id','journal_sequence')} for row in engine.store.history(limit=50000)]
    return dict(schema='earthship-observation-replay/v1',decisions=decisions,
                decisions_sha256=digest(canonical(decisions)),observations_sha256=digest(canonical(observations)))
