# Deployment readback requirements

A clean source checkout does not include the ignored live public/config.json.
Retain the exact reviewed local configuration in the permanent UI release before
starting it. The household deployment uses an empty openhabUrl and empty client
token so requests use the authenticated same-origin proxy. Do not copy server
credentials into the browser configuration.

Check /config.json as JSON, the authenticated proxy and the browser's actual
loaded Item count. Rendering the application shell or a successful direct REST
request alone does not demonstrate that its data store connected. Verify Home,
Weather, Energy and Household at both console sizes, including rainfall inches
and roof gallons. Preserve both failed and corrected readback evidence.

The October 23 initial UI cutover omitted that ignored configuration. Restoring
the original bytes recovered all 460 live Items. Actual browser checks then
passed on both console sizes, and the Home screenshot showed 0.03 inches and
52 gallons today, 0.38 inches and 663 gallons this week, and a falling three-hour
pressure trend. These are observations at the verification time, not fixed
expected future weather values.

The first new physical forecast published successfully, but its household
reader still assumed the legacy conditioning admission structure. The new
confirmed-production context has a direct runtime manifest. The follow-up
reader binds its separate closed source set during preparation and frozen
replay, keeps legacy context verification unchanged, and rejects changed source
hashes. Replaying the actual issued origin demonstrated the original failure
and corrected household preparation without changing the forecast or original
files. The physical fitted source closure is unchanged; no refit or renewal
of the original fit clocks is justified for this reader repair.

A complete release still requires effective source/selector readback and fresh
household originals from the corrected producer's natural cycles. Do not count
a successful physical forecast exit as proof that its optional observation,
energy, storage and scoring sidecars succeeded. Each has its own original
receipt and publication status.
