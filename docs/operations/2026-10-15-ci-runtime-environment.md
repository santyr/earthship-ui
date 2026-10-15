# Hosted Python runtime and resource test environment

The previous hosted run `38764782402` failed 67 Python cases while 5,949 passed.
Retained traces identify two independent environment assumptions. No production
model or resource safeguard is changed by this correction.

* Runtime binding correctly refuses group/world-writable executable bytes.
  GitHub setup-python selected its tool-cache interpreter, whose permissions
  did not meet that contract. The disposable CI runner now removes group/world
  write permission from its selected resolved executable before binding tests.
  The original interpreter bytes and the production admission policy are kept.
* Four resource adapter/inventory cases used the current worker's real cgroup
  even though they test adapter restoration, final memory-event checks or source
  read inventories. They now use deterministic kernel-metadata fixtures while
  retaining real policy, monitor and pinned source-read paths as appropriate.
  The dedicated real-cgroup smoke test is explicitly selected with
  `EARTHSHIP_RESOURCE_SMOKE=1` inside a capped publication/shared-pool scope.
  An unbounded hosted runner skips that one smoke test rather than claiming to
  have qualified the production scope.

Verification: the unscoped adapter file passes 11 cases and explicitly skips
one real-resource smoke. With the opt-in enabled under the existing shared job
launcher, all 144 adapter, resource-policy, pressure and original-runtime cases
pass, including the actual worker's cgroup check and writable-source/executable
refusal cases. A disposable exact-byte interpreter copy is refused at mode775
and accepted after `chmod go-w`, with its bytes unchanged; the actual production
interpreter is untouched. The exact workflow shell block passes `bash -n`.

The next hosted run `38773847822` passed the interpreter-permission step and
6,027 Python cases, leaving 13 failures. Its retained traces exposed the same
permission issue on the selected Java launcher and remaining old test fixtures
that invoked real runner admission. CI now tightens both disposable launchers.
The source-location test supplies deterministic kernel metadata through the real
verifier's declared arguments, keeping its actual code location and source hash
checks. Report-reuse tests retain real original-file replay and mutation checks
with deterministic resource/pressure inputs. The coordinator fixture now patches
its current operational admission seam. The additional actual-cgroup/no-process-
spawn smoke is explicitly opt-in alongside the existing cgroup smoke.

The five affected files pass 38 cases with two explicit cgroup smoke skips;
scoped opt-in verification is retained separately. Hosted verification of the
final correction is still required. This is a CI
environment correction, not completion of the remaining PR #3 architecture.

The final environment correction in `5c74c0a` passed all 6,039 OpenHAB Python
cases (24 explicit skips and 91 subtests), all 2,439 frontend tests, the frontend
build, all 571 completion cases and real isolated nak authentication in hosted
run `38778917509`. The OpenHAB step took 27m02s. The job then reached its existing
30-minute overall timeout during operational-tooling tests, which were cancelled
without a reported assertion failure. The hosted job allowance is increased to
45 minutes so the existing full checks can finish; no check is removed and no
production resource policy changes. The next feature push will verify that final
workflow. No unchanged CI rerun was triggered after the cancellation.
