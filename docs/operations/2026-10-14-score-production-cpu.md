# Production scoring CPU admission

The current model's normal 20:21 UTC score failed at 20:22:44 with `deadline`
at `thermal_model/capture_readers.py:36`: its 50-second acquisition budget had
expired. The worker used 20.245 CPU seconds and peaked at 83.8 MiB, with no swap.
A previous historical run was throttled in 897/904 periods for 71.69 seconds,
with zero memory PSI and memory-limit/OOM events. Its exact 32 retained packets
rebuilt a valid original source score offline in 3.834 seconds at one core,
without networking, fitting, or live writes.

Under the user's approval to increase production resources while protecting the
host, scoring now opts into the existing one-core publication profile. The
worker retains 256 MiB RAM, zero swap, 24 tasks, one numerical thread, low I/O
priority, host RAM/pressure admission, the shared consumer lock, and its existing
120-second work/130-second service deadlines. This is a bounded production fix;
a dynamic host-wide resource coordinator is not implemented by this change.

Current scoring invokes the pinned publication resource helper. Retained legacy
and native scoring invokes its original numerical code and evidence validation
under an explicit scoped admission-policy adapter. That adapter temporarily
replaces only the installed/native resource-preflight entry points and the
publication admission helper, restoring them on exit. The current policy helper
is checked against its pinned source digest before use. Archived source files,
model identities, receipts, data validation and physical-control authority are
unchanged. Existing archived service-family definitions retain their original
quota when verified; new opted-in families require exactly one core in effective
unit readback. Preparation remains at its existing quota.

Validation: 129 affected scoring, dispatch, admission, effective-unit and handoff
tests passed in 15.93 seconds. An offline check accepted the new policy against
the actual legacy archive and all ten retained native archives, denying network
access and executing no scores or fitting. Deployment and production scoring
outcomes remain pending.
