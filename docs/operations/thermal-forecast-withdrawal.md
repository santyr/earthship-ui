# Thermal forecast withdrawal

Use this procedure for baseline regression, calibration failure, incompatible
sensor epoch, artifact corruption, instability, or publication failure. Withdrawal
publishes an honest unavailable state and retains its reason and actual JDBC
receipt. It does not require a readable candidate, weather source, or model journal.

Before commissioning, retain the compatible shadow runtime and accepted artifact,
record the effective shadow service definition, and prepare a private withdrawal
configuration. The configuration must contain exactly these fields:

```json
{
  "schema": "earthship-installed-shade-withdraw-config/v1",
  "openhab_base": "http://127.0.0.1:8080/rest",
  "token_file": "/absolute/private/token-file",
  "evidence_directory": "/absolute/private/publisher-evidence-directory"
}
```

Use the approved existing token. Configuration and token files must be owned mode
600, with owned mode 700 parent directories. Paths must be absolute and resolved.
The evidence directory must be the publisher's existing evidence directory so
withdrawal and publication use the same lock. Never copy credentials into Git.
Record the installed, reviewed runtime path separately; do not run from a changing
checkout during a production incident.

1. Stop and disable the production forecast timer, then stop its service. Confirm
   both are inactive before withdrawing. A busy lock means withdrawal has not
   happened; inspect the running service before retrying.
2. Run the installed CLI using the prepared private configuration and a bounded
   private reason. The example below requires replacing the runtime path and config
   path with the commissioned paths:

```bash
systemd-run --user --scope --quiet \
  -p CPUQuota=20% -p MemoryMax=256M -p MemorySwapMax=0 \
  -p TasksMax=24 -p IOWeight=10 \
  nice -n 15 ionice -c 3 \
  env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  EARTHSHIP_QUALIFICATION_FIT=0 EARTHSHIP_REMOTE_QUALIFICATION_FIT=0 \
  timeout 90s /usr/bin/python3 /absolute/installed/runtime/thermal_installed_intel.py \
  --config /absolute/private/withdraw.json --withdraw --reason 'baseline regression'
```

3. Require `status=withdrawn` and `delivery_verified=true`. Inspect the private
   `receipt_path`: it must retain the reason and matching persisted unavailable
   publication. HTTP acceptance, `busy`, and `unverified_failure` do not establish
   withdrawal. A failure leaves the delivery state unverified and requires checking
   the actual main Item; do not claim success from the command exit alone.
4. Restore the recorded compatible shadow service/runtime and accepted artifact.
   Keep the production timer disabled. Start one bounded shadow cycle and verify
   its actual persisted main publication is explicitly shadow before enabling the
   shadow timer. Preserve the withdrawal record even after shadow publication
   replaces the unavailable state.
5. Confirm exactly one publisher timer owns the main thermal Item, then verify its
   next natural publication. Keep prospective evidence and baseline scoring intact.

Cutover reverses publisher ownership only after release gates pass: disable the
shadow timer and stop its worker before enabling the production timer. Shared
locks prevent simultaneous work but cannot prevent two alternating publishers
from overwriting each other's mode. Do not enable both timers.

This runbook documents the withdrawal interface and required operational checks.
It is not evidence that a production cutover or live return to shadow has occurred.
Host disaster recovery remains separate from this ML lifecycle procedure.
