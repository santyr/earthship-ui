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

Still required: replay retained measured training inputs, genuinely refit
and admit the current physical response, exercise the complete staged
rollout with confirmed production weather, connect household component
PV/storage, finish all normal CI and whole-capability review, export every
original/source generation, then perform the authorized reversible
deployment and actual service/UI readback.
