"""Observe the unchanged forecast cycle under its caller-owned lock.

This module is outside both producer source manifests. Original forecast inputs,
transport and numerical outputs are delegated unchanged; no model fitting or
device request is introduced by observation.
"""
from datetime import datetime,timedelta,timezone
import math,time
from household.codec import canonical,loads
from household.evidence import utc

MAX_SOURCE_BYTES=1048576
MAX_COLLECTION_SECONDS=6.
ISSUE_MARGIN=timedelta(seconds=3)


class ObservingBackend:
    def __init__(self,parent,*,collector,guard,clock=lambda:datetime.now(timezone.utc),monotonic=time.monotonic):
        self.parent=parent;self.collector=collector;self.guard=guard
        self.clock=clock;self.monotonic=monotonic
        self.collection=dict(status='unavailable',reason='not_collected')

    def __getattr__(self,name):
        return getattr(self.parent,name)

    def collect(self,*,issue,known_at):
        # Parent exceptions are authoritative forecast failures, not observer
        # failures. Do not catch or replace its exact original input object.
        inputs=self.parent.collect(issue=issue,known_at=known_at)
        issue=utc(issue);now=utc(self.clock())
        budget=min(MAX_COLLECTION_SECONDS,(issue-ISSUE_MARGIN-now).total_seconds())
        if not math.isfinite(budget) or budget<=0:
            self.collection=dict(status='unavailable',reason='insufficient_preissue_budget')
            return inputs
        deadline=self.monotonic()+budget
        def remaining():
            self.guard()
            value=min(deadline-self.monotonic(),(issue-ISSUE_MARGIN-utc(self.clock())).total_seconds())
            if not math.isfinite(value) or not 0<value<=MAX_COLLECTION_SECONDS:
                raise ValueError('household pre-issue budget elapsed')
            return value
        try:
            remaining()
            originals=self.collector(issue=issue,remaining=remaining,guard=self.guard)
            remaining()
            if not isinstance(originals,dict):raise ValueError('closed original source object required')
            raw=canonical(originals)
            if len(raw)>MAX_SOURCE_BYTES:raise ValueError('bounded household originals required')
            remaining()
            captured=utc(self.clock())
            if captured<now:raise ValueError('household collection clock moved backward')
            self.collection=dict(status='collected',reason=None,issue=issue.isoformat(),
                captured_at=captured.isoformat(),originals=loads(raw))
        except Exception:
            self.collection=dict(status='unavailable',reason='source_collection_failed')
        return inputs
