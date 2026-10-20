"""Admit added immutable days without changing an experiment's selected refs."""
from datetime import date
import json
from .contracts import canonical,identity


def _index(raw):
    if not isinstance(raw,bytes) or len(raw)>262144:raise ValueError('bounded history index required')
    value=json.loads(raw)
    if (not isinstance(value,dict) or canonical(value)!=raw or
        value.get('index_sha256')!=identity({k:v for k,v in value.items() if k!='index_sha256'}) or
        not isinstance(value.get('days'),list) or len(value['days'])>366):raise ValueError('unchanged original history index required')
    dates=[r['date'] for r in value['days']]
    if dates!=sorted(set(dates)) or any(date.fromisoformat(d).isoformat()!=d for d in dates):raise ValueError('unique ordered historical dates required')
    return value


def verify_retained_selection(original,current):
    before,after=map(_index,(original,current))
    context=lambda v:{k:row for k,row in v.items() if k not in ('days','index_sha256')}
    if context(before)!=context(after):raise ValueError('historical index context changed')
    newer={r['date']:r for r in after['days']}
    if any(newer.get(r['date'])!=r for r in before['days']):raise ValueError('original selected historical references changed')
