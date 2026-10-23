# Current-time production retraining

The October 22 deployment instruction allows fresh historical-data fits for the
production replacement. It does not change the old experiments or make their
historical forecast-readiness assumptions into operational receipts.

`production_model_train.py` reads one retained, original population and its
measurement context. It fits one explicitly named family at the current cutoff.
Both forecast and observation must actually have arrived before that cutoff.
The fitting window, minimum distinct targets/dates, positive-target support,
date/target weighting and parameter bounds remain those of the frozen numerical
protocol. The largest predeclared ridge is fixed; no new outcome-driven search
is added. Old evaluation targets may now be available training data; their old
scores are not held-out evidence for the new weights. New production predictions
must be evaluated against later real observations after deployment.

The new production bundle retains the historical or recorded training basis,
original pair identities and actual fit-completion clock. Its serving descriptor
is separately identified. Transfer to a live forecast permits only the recorded
availability class with the same quantity, measurement policy/epoch, native
grid, timezone and lead domain. Contiguous lead partitions retain their exact
boundaries. Different sensor epochs or measurement targets cannot silently share
coefficients. Wind remains an hourly local-station mean; the solar proxy remains
a lux-derived proxy, not physical GHI.

The shared marginal formulas are factored into a pure numerical function. The
original prediction reader retains its original admission/cohort rules. A
normal-harness golden fixture from producer `a6a16d9` verifies the unchanged
fit parameters and forecast numerics for temperature normal, empirical,
nonnegative wind and nonnegative solar-proxy cases, with a declared 1e-8 absolute
tolerance. This fixture is synthetic and contains no household observations.

Retained production artifacts include lossless original training and source
capsules. The reader checks original identities, actual past availability,
complete fitted membership, support, numerical source and numerical environment.
Production artifacts and admissions count toward the existing shared storage
cap. Preview does not create the requested state directory or update selectors.
Applying a fit retains an artifact; it does not install a model or start a
parallel shadow pipeline. Production activation still requires the exact reviewed
release, selector readback and rollback described in Step 11.
