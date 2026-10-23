# Selected temperature conditioning - implemented, not installed

The new v2 thermal selection consumes temperature points already published
by the selected production weather models. It reads their immutable issue,
successful per-Item emission and view receipt. It checks actual detail-state
temperature values, published target membership, source site, outdoor sensor
phase, method identity and original publication time. It neither compiles
another weather forecast nor calls the weather models again.

Current-source inspection found the same outdoor sensor epoch in the active
physical model and the prepared temperature model's original measurement
context: fc02157a-7666-4127-9f04-a5be035e16b1. The adapter verifies this match
for every new context rather than assuming it from that inspection.

The physical forecast keeps its original raw weather rows. For selected
conditioning it interpolates from the qualified measured initial outdoor
state to the first future emitted temperature, then between the original
hourly points. Native ending-hour horizontal radiation and origin actions
remain unchanged. The old separate ridge-temperature and irradiance
conditioner is not applied in this new mode. One physical rollout consumes
the resulting forcings.

An absent, expired, incomplete or wrong-phase production input produces a
named native-raw fallback context. A changed immutable confirmation invalidates
a frozen context. A later latest-view update does not erase the original
forecast: replay checks the retained original confirmation, not today's cache
or selector. Both original v1 conditioning and old capture replay remain
separate from the new v2 meaning. The context stays within 32 KiB.

The native numerical source manifest now binds the temperature adapter and
its reader. The three serving entry points retain their existing literal
serving-helper pin requirements. Other conditioning sources are included in
the numerical manifest as a complete group, without giving them serving
helper authority. The source change requires a genuine fresh physical
response fit under the supported numerical environment before deployment;
an old candidate is not repinned.

Nine new temperature-adapter cases and the existing conditioning, native
artifact, forecast, publication, scoring and serving-admission cases passed
together: 140 tests in 42.52 seconds. These are focused checks, not deployment
or physical qualification. The staged handoff separately waits for a safe
preparation window under the existing resource/deadline guards.

The fresh response fit has now replayed the complete retained measured
dataset exactly under the new source. Training covers October 15 at 06:00 UTC
through October 23 at 00:00 UTC, with 33 supported horizon endpoint instances.
Original dataset and source clocks are preserved. The actual new fit ran
from 2026-10-23 04:05:29.332102 to 04:05:31.042232 UTC under NumPy 2.5.4 and
SciPy 1.18.1: 1.710 seconds fitting, 9.810 seconds total, 185,404 KiB peak RSS.
It used no cloud or SQL requests and changed no serving unit files.

The new artifact is
5219dffe4d4784a58a05b11c7bd935305561703f5c03a5027fde14b8db2673a3,
with original proof
e8ba5305aab3a68f560394c7c9843e334d804052fe4ae720ceeed2967eb263f7.
Its source package, byte-identical retained inputs, old superseded candidate
and new original fit evidence are stored in a permanent private artifact
directory outside the plan workspace. [Fit metadata](production-thermal-fit.json)
records the exact source/environment changes; the old artifact was not retagged.

The genuine candidate has now passed full admission replay in the permanently
retained supported environment. The numerical runtime is identical and the
candidate bytes are unchanged. Admission completed at 06:08:49 UTC in 8.205
seconds at 161,388 KiB RSS, with no acquisition or production state changes.
[Admission metadata](production-thermal-admission.json) and
[environment verification](production-environment.md) preserve the evidence.

Still required: package the admitted response, exercise the complete staged
rollout with confirmed production weather, connect household component
PV/storage, finish all normal CI and whole-capability review, export every
original/source generation, then perform the authorized reversible
deployment and actual service/UI readback.
