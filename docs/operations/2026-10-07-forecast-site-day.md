# Forecast learning day and site timezone

The forecast command now derives its current timestamp and calendar day from the
configured site timezone. A host using UTC can otherwise enter the next calendar
day before the site's current day has closed. This misselects the day for learning
evidence and disagrees with the site-based day-completion and hourly-target rules.

The change uses one aware site timestamp and its date. It preserves the qualified
rain/PV/temperature/SoC source guards, completion windows and prediction equations.
A timezone-boundary regression covers sites on either side of UTC midnight. The
existing fixture suite now uses one deterministic, coherent site/UTC clock for
scoring dates, snapshots and source assessments.

This is a source change and has not been deployed to installed services. Household
safety/control rules are unaffected.
