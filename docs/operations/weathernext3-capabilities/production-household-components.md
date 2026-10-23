# Household component PV/storage - integration in progress

The new original-input adapter runs inside the retained native producer. It
replays the original household energy and learned-load receipts, preserves
their raw weather and geometry, and extracts qualified initial battery/bank
state, the instantaneous-load exclusion reason and the original AC-load curve.
It verifies the actual producer source and numerical environment against the
original capture. A matching value produced in a different environment is
insufficient.

The v2 process protocol is distinct from the old v1 scenario protocol. An
explicit v2 producer reference binds its Python executable bytes, so a new
supported native stage can use its own environment. Old references keep their
original interpreter. The new input-only child blocks sockets and additional
processes; it does not acquire HTTP/SQL data, fit a model or issue a forecast.

Two actual natural-cycle input previews passed. The final source/environment
check at 2026-10-23 04:46:14 UTC retained original issue 04:45:15, 288 native
positions and the existing projected learned-load model. It used 3.354 seconds
and 124,508 KiB peak RSS. The original producer used NumPy 1.26.4/SciPy 1.11.4;
that environment is isolated from the new component model's supported
NumPy 2.5.4/SciPy 1.18.1 process. No environment is substituted for an old fit.

The final input proof is
0903711a30738c628ce2eb1034a9c55f6982d3745d15d2ee46bb2ad1cdaa075e.
Its complete input context and literal adapter/producer source packages remain
retained, as does the preceding source generation and proof. No selector,
original, cache or Item was changed.

Those real inputs excluded the instantaneous load for source skew, while the
battery state and learned-load curve remained qualified. The new projection
therefore treats PV, constant-load storage and learned-load storage separately.
The shared ComponentOwner supplies the same fitted native-component gain and
kernel used by daily PV. Both conditional storage hypotheses use the existing
nominal-capacity integrators; native-only gains do not adjust total-only
fallback segments.

Six input/transport/environment cases pass, and the broader retained-scenario
boundary passed 23 cases before the final explicit environment check. Nineteen
projection/owner/profiled-storage cases pass, including missing instantaneous
load, missing initial battery state and unadjusted total-only fallback.
These overlapping focused checks do not establish physical accuracy or
deployment.

The measured full input context is about 3.3 MiB, mostly retained source and
parent documents. The publication implementation must retain source packages
once per source generation and reference the already immutable parent
originals, rather than duplicating that context every five minutes. Keep
original metadata and clocks unchanged. Enforce explicit byte/object/disk
headroom and retain confirmed actual publication separately from preparation.

The complete natural-cycle projection passed at 2026-10-23 05:15:43 UTC
against original issue 05:15:15. It uses the same calibration1b294e90... as
daily PV: raw18.0864924035 kWh and selected11.7331593239 kWh, with12 native
source hours and13 explicitly named fallback source hours. Both constant-load
and original learned-load nominal storage were available. Active preparation
took3.837 seconds at131,372 KiB RSS; the remainder of34.836 seconds was waiting
for a fresh natural cycle. No cache, Item, cloud, SQL or selector was written.

The exact original proof is
27631d9be815f2967971e3904d4443f8a88fa4d2876b06de60caa5e3b3a216ea;
[public metadata](production-household-preview.json) preserves its identities.
An earlier private preview selected an energy file1.275 seconds before its
matching profile arrived. Inspection confirmed that the existing observer
commits its public plan after attempting both originals. The new reader
therefore follows that committed plan receipt, instead of taking a newer
in-progress energy file. It supports the existing observation schemasv1-v4,
preserves named missing-profile behavior, and refuses a changed observation
before commit. Four reader cases pass, including the actual currentv4 shape.

Still required: wire
the existing calibrated worker, outcome actor and compatible UI through new
schemas; preserve all legacy producer replay; complete normal CI, final
whole-capability review, permanent export, exact rollback and authorized
installation/readback/UI checks. No new household component output is
installed.
