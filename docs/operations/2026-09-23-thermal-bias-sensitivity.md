# Thermal air-bias sensitivity — September 23

This is a read-only diagnostic, not a model update. The installed v4 shadow
runtime was invoked in memory with four exact private forcing captures from
September 23. It used accepted model SHA256
`c3e7f7b14abe4ccdf687f07f814407fac12fb1d0ff2ddefc160ba722d4083e60`.
Before any variation, the replay reproduced each persisted publication's
current state, forecast and schedule exactly. No registry save, OpenHAB write,
notification, journal write or action command occurred.

The accepted air-bias term is **−0.063314°F per five-minute step**. An
in-memory copy of the artifact was replayed with only that coefficient set to
−0.03°F, 0°F or +0.03°F per step. A variant was scored only where its selected
schedule still equaled the published schedule. Four captured one-hour targets
and one six-hour target had qualified indoor outcomes:

| Target | Published model error | Bias −0.03°F | Bias 0°F | Bias +0.03°F |
| --- | ---: | ---: | ---: | ---: |
| 15:50Z issue, 1h | −1.541°F | −1.133°F | −0.765°F | −0.397°F |
| 17:51Z issue, 1h | −2.801°F | −2.393°F | −2.025°F | −1.658°F |
| 19:51Z issue, 1h | −2.144°F | −1.736°F | −1.368°F | −1.000°F |
| 21:51Z issue, 1h | −1.599°F | −1.191°F | excluded | excluded |
| 15:50Z issue, 6h | −6.529°F | −5.227°F | −4.054°F | −2.881°F |

The excluded variants selected a different schedule, so they cannot be read
as a coefficient-only comparison. All published one-hour errors were low;
reducing the negative bias improved these few points but did not eliminate the
miss. The first six-hour point also improved, but one target cannot establish a
transferable correction. The captured outdoor forecast error changed sign
across the four one-hour cases, so these observations do not isolate weather
error as the cause either.

This does not justify editing the accepted artifact, loosening the 24-hour
gate, or graduating advice. A legitimate fit experiment needs a frozen
chronological train/validation split, an untouched later test set, exact
origin-time forcing, action-state provenance and seasonal coverage. The
current captured operational set is warm-season and too small for that claim.
The disposable replay workspace was removed after this audit.
