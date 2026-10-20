import pytest
from weather_learning.contracts import canonical,identity

def raw(days):
 v=dict(schema='retained-test/v1',days=[dict(date=d,source_sha256=s) for d,s in days],automatic_actuation=False)
 v['index_sha256']=identity(v);return canonical(v)

def api():
 from weather_learning.history_index import verify_retained_selection
 return verify_retained_selection

def test_new_immutable_days_do_not_invalidate_an_offline_dataset_snapshot():
 old=raw([('2026-09-20','a'*64)])
 newer=raw([('2026-09-19','b'*64),('2026-09-20','a'*64),('2026-09-21','c'*64)])
 api()(old,newer)

@pytest.mark.parametrize('days',[[('2026-09-20','b'*64)],[],[('2026-09-20','a'*64),('2026-09-20','b'*64)]])
def test_changed_removed_or_ambiguous_original_references_are_refused(days):
 with pytest.raises(ValueError):api()(raw([('2026-09-20','a'*64)]),raw(days))
