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

Hosted verification of the corrected revision is still required. This is a CI
environment correction, not completion of the remaining PR #3 architecture.
