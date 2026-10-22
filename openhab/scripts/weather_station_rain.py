"""Receipt-clock rain products; gaps never become measured dry intervals.

Calendar products are to the last accepted receipt. Boundary brackets expose
depth uncertainty. These are local reconstructions, not console counters.
"""
from bisect import bisect_left
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from weather_station_counter import CounterTracker

UTC = timezone.utc
MAX_POINTS = 20000


class RainProducts:
    def __init__(self, *, timezone_name, validity_seconds, maximum_counter_in):
        self.zone = ZoneInfo(timezone_name)
        self.counter = CounterTracker(validity_seconds=validity_seconds,
                                      maximum_counter_in=maximum_counter_in)
        self.validity = validity_seconds
        self.points = []
        self.anchors = {}
        self.last_at = self.last_tick = None
        self.broken = False
        self.event = None
        self.phase = None

    def _starts(self, at):
        local = at.astimezone(self.zone)
        day = local.replace(hour=0, minute=0, second=0, microsecond=0)
        return {'day': day.astimezone(UTC),
                'week': (day-timedelta(days=(day.weekday()+1) % 7)).astimezone(UTC),
                'month': day.replace(day=1).astimezone(UTC)}

    def _bracket(self, at):
        if not self.points or at < self.points[0][0] or at > self.points[-1][0]:
            return None
        i = bisect_left(self.points, (at, -float('inf')))
        if self.points[i][0] == at:
            return (self.points[i][1],)*2
        return self.points[i-1][1], self.points[i][1]

    def invalidate(self):
        self.counter.break_sequence()
        self.broken = True
        self.anchors.clear()
        self.event = None

    def observe(self, counter_in, *, at, tick):
        try:
            transition = self.counter.observe(counter_in, at=at, tick=tick)
        except ValueError:
            self.invalidate()
            return
        at = at.astimezone(UTC)
        if transition.status == 'withheld':
            self.invalidate()
            return
        reset = self.broken or transition.new_phase or not self.points
        if reset:
            self.points = []
            self.anchors.clear()
            self.event = None
            self.phase = (at, float(counter_in))
        self.broken = False
        # Repeated receipt clocks cannot create a zero-duration increment.
        if self.points and at <= self.points[-1][0]:
            self.invalidate()
            return
        self.points.append((at, float(counter_in)))
        self.last_at, self.last_tick = at, float(tick)
        for name, start in self._starts(at).items():
            old = self.anchors.get(name)
            if old is None or old[0] != start:
                self.anchors[name] = (start, self._bracket(start))
        quiet_start = at-timedelta(hours=24)
        quiet = self._bracket(quiet_start)
        quiet_known = quiet is not None and counter_in-quiet[0] < 1/25.4
        if self.event is None:
            if quiet_known:
                self.event = (at, float(counter_in), False)
        else:
            start, baseline, active = self.event
            if not active and counter_in > baseline:
                self.event = (at, baseline, True)
            elif active and (at-start).total_seconds() >= 86400 and quiet_known:
                self.event = (at, float(counter_in), False)
        # Keep one boundary carry point. Calendar anchors survive pruning.
        cut = bisect_left(self.points, (at-timedelta(hours=25), -float('inf')))
        if cut > 1:
            del self.points[:cut-1]
        if len(self.points) > MAX_POINTS:
            self.invalidate()
            self.points = [(at, float(counter_in))]

    def snapshot(self, *, at, tick):
        fresh = (self.last_at is not None and not self.broken and
                 0 <= (at-self.last_at).total_seconds() <= self.validity and
                 0 <= tick-self.last_tick <= self.validity)
        end = self.last_at
        current = self.points[-1][1] if self.points else None

        def product(start, bracket, factor=1.):
            known = fresh and bracket is not None
            lower = max(0., current-bracket[1])*factor if known else None
            upper = max(0., current-bracket[0])*factor if known else None
            partial = (max(0., current-self.phase[1])*factor
                       if fresh and self.phase and start <= self.phase[0] else 0.)
            return dict(value=(lower+upper)/2 if known else None,
                        lower=lower, upper=upper, partial_lower_bound=partial if fresh else None,
                        unit='in/h' if factor == 6 else 'in',
                        start=start.isoformat() if start else None,
                        end=end.isoformat() if end else None,
                        method='receipt_counter_boundary_brackets/v1')

        reference = end or at.astimezone(UTC)
        products = {}
        for name, seconds, factor in (('rate_10min', 600, 6.), ('rolling_hour', 3600, 1.)):
            start = reference-timedelta(seconds=seconds)
            products[name] = product(start, self._bracket(start), factor)
        for name, start in self._starts(reference).items():
            anchor = self.anchors.get(name)
            products[name] = product(start, anchor[1] if anchor and anchor[0] == start else None)
        event = self.event
        products['event'] = product(event[0] if event else reference,
                                    (event[1], event[1]) if event else None)
        products['event']['method'] = 'local_event_24h_under_1mm_reset/v1'
        return dict(schema='earthship-station-rain-products/v2',
                    status='fresh' if fresh else 'stale' if end else 'unavailable',
                    products=products)
