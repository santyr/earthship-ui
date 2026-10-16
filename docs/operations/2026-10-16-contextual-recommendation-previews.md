# Contextual recommendation previews — 2026-10-16

Approved scope: show model-generated actuation suggestions beside the relevant UI content while keeping automatic actuation disabled. Display action, original time, rationale, confidence and blockers, and distinguish unavailable and expired evidence. No execution control is added.

Placements: greywater beside Earthship circulation; ventilation beside the thermal model; aggregate load suggestions on Energy; individual load/feeding suggestions with Household Loads on Controls and override/greywater suggestions with Water & Policy; feeding on the existing Home card; shade advice on Shades when actually published. Compact summaries open information-only native popovers containing complete source clocks and original reasons/blocks. These buttons only open or close details.

Public observation v4 adds the original validated intent parameters and creation/expiry clocks after the existing complete plan replay. The frontend accepts only the registered action types, fixed device names and ON/OFF commands. It keeps v1/v2/v3 readable, and never infers a command from a legacy intent type or reason. Original source, snapshot, receipt and qualification bindings remain unchanged. The new fields do not change planning, fitting, effects or qualification gates.

The observation panel and contextual previews share one fixed read-only GET poll and one display clock. The last subscriber aborts pending reads and stops polling; superseded or late responses cannot replace a newer subscription. Original expiry controls display status without waiting for another poll. Expired suggestions remain historical and do not become current recommendations through re-verification.

Climate presentation consumes the existing validated thermal publication. Forecast baselines, assumed vent states and withheld action advice do not become recommendations. A published ventilation candidate with both explicit endpoints can be shown with its actual timing and unqualified/expired state. Closed-vent candidates do not fabricate a timed window. Shade trajectory markers may describe baseline state and use rounded hourly buckets; they remain unavailable as advice until an explicit candidate action/timing contract exists. No per-shade state, recommendation, physical effect or control permission is invented. Existing motorized-shade preview controls are separate from these model displays.

All automatic-actuation and release flags remain false. No request translation, owner migration, model fitting, extra forecast, production resource-policy change or recovery work is included. The live Home AQI overlay is preserved because Home itself is not modified.

## Verification

Affected backend tests: 89 passed. Full frontend suite: 2,575 passed. The initial full run exposed four obsolete assertions forbidding all buttons or even the phrase “advice unavailable”; they now permit only information popovers while still rejecting execution inputs/buttons and fabricated advice. One intermediate rerun hit the existing HTTP fixture's random `bad port` allocation in `household-observation-server` permissions coverage; the final full run passed all 2,574 tests without a product change for that transient failure.

Private synthetic browser checks cover all five screens at laptop1280×800 and tablet1340×800, count shared observation requests and block every mutation request. A clipping regression was reproduced and corrected by preserving accessible inner scrolling for existing greywater and thermal details. Unavailable thermal output legitimately has no plot details. Final private geometry: ten cases passed with zero page errors, mutation requests or outer overflow. Every details popover fit the viewport; the shared observation endpoint was requested once per screen. Final build passed with the existing large-chunk warning. Single review and live deployment evidence follow below.

Full household qualification remains open. These previews do not establish statistical independence, model skill, physical safety or permission to actuate.

The single immutable feature review found two important presentation defects: ambiguous shade trajectory markers and null closed-vent endpoints. Both were reproduced by failing regressions and corrected in one pass. No actuation path was found. A minor expired-climate limitation remains: the existing strict thermal parser withholds expired publications entirely, so these display unavailable rather than historical action details; no freshness is renewed. Extending that parser is deferred. No re-review was requested.

After the review corrections, the full frontend suite passed 2,575 tests in 168 files and the production build passed. Backend numerical and receipt logic was unchanged by the correction.
