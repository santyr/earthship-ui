# OpenHAB token rotation: prepared, awaiting operator action and approval

## Scope and current state

This is a read-only preparation receipt for `SECURITY-TOKEN-ROTATION` in
`docs/qa/ui-audit-matrix.csv`. No token was created, replaced or revoked, and
no service was restarted. The approved sky handoff is already complete;
its approval does not authorize this separate credential transaction.

The QA matrix requires fresh explicit approval to rotate the token and
restart only Earthship UI. The local home-automation assignment also requires
task-specific authority for service restarts and live changes.

On October 4, authenticated `GET /rest/auth/apitokens` returned three metadata
records containing only name, scope and creation time. The private environment
credential uniquely matched the token named `Hex`; its scope is the empty
string. Credential values, account passwords and raw authentication responses
must remain outside Git, reports and chat.

`earthship-ui.service` reads `/home/sat/.config/hex/openhab.env`, currently a
0600 file owned by UID 1000. Its working directory is this repository, port
5190, and release mode `safe-compat`. Readback showed MainPID 419027 and the
last activation at October 2, 10:55:25 MDT. `vite.config.js` constructs and
caches the proxy authorization header at startup, so file replacement alone
would leave the running UI using the old token.

The same environment file is read by forecast, thermal training/shadow and
maintenance helpers. The owner-process census examined 40 processes: three
readable matching holders belonged to the UI process family; seven processes
were unreadable or exited. This is not proof that the UI is the only consumer.
The sanitized receipt is `/tmp/earthship-ui-token-consumers.json` (0600).
Fresh consumer checks are required before any revocation.

## Installed creation and revocation contract

The deployed authentication bundle is OpenHAB 5.2.1:

- HTTP-auth bundle SHA-256:
  `a6bfa308ab12b68edae74bc0160564c7a4ba6062faedca8f335f561c8adafcfb`.
- `CreateAPITokenPageServlet.class` SHA-256:
  `c713cd67c32606a96617299c2a682ab0dffabf68e9648e8ec94d0757b970b008`.

Installed class constants confirm `/createApiToken`, username/password,
`csrf_token`, `token_name`, `token_scope`, login and token registration.
The [matching official 5.2.1 creation source](https://github.com/openhab/openhab-core/blob/5.2.1/bundles/org.openhab.core.io.http.auth/src/main/java/org/openhab/core/io/http/auth/internal/CreateAPITokenPageServlet.java)
requires account authentication and a valid CSRF token. Names accept letters
and digits only. Creation returns the secret in HTML; it must not be captured
in public logs. The existing API credential does not replace account login.

The [matching REST source](https://github.com/openhab/openhab-core/blob/5.2.1/bundles/org.openhab.core.io.rest.auth/src/main/java/org/openhab/core/io/rest/auth/internal/TokenResource.java)
provides metadata readback and named revocation with
`DELETE /rest/auth/apitokens/{name}` for the authenticated user's token.
Revocation is the final step, after replacement verification.

## Exact proposed transaction

1. The operator creates a token in OpenHAB's normal authenticated interface
   for the same account that owns `Hex`, named `Earthship20261004` (or another unused alphanumeric name), with an
   empty scope matching `Hex`. Do not enter account credentials or the new
   secret in chat. Privately save only `OPENHAB_TOKEN=<new value>` in
   `/home/sat/.config/hex/openhab.next.env`, owned by UID 1000, mode 0600,
   regular file with no symlink. This is a proposed staging path; it has not
   been created by this preparation.
2. After explicit approval, freshly verify installed service configuration,
   private file ownership/modes and token metadata; verify the new credential
   using authenticated read-only REST calls. Stop if the token scope differs,
   a consumer cannot be accounted for, or another job caches the old token.
   Do not start scheduled helpers, stop unrelated services, or change timers.
3. Keep a private owner-only recovery copy of the old environment. Atomically
   replace only the `OPENHAB_TOKEN` assignment in `openhab.env`, preserving
   all other assignments, ownership and mode. Do not log either secret.
4. Restart only the user unit `earthship-ui.service`. Verify active state, a
   changed process identity, port 5190, normal UI read responses, and the UI
   process environment matching the new private credential. The OpenHAB JVM,
   PostgreSQL, forecast and thermal units are not restarted by this plan.
5. Verify one-shot helper authentication with bounded read-only requests using
   their credential loading conventions. Recheck consumers and the private
   file immediately before revocation. Do not invoke helpers that send
   notifications, publish shadow cycles, train models or command Items.
6. Authenticate with the replacement credential and revoke only `Hex`.
   Confirm metadata contains the replacement with matching scope and the two
   unrelated tokens, and excludes `Hex`. Independently confirm replacement
   authentication still works and the old credential is rejected by an
   authentication-required endpoint; HTTP success on an anonymously readable
   endpoint does not prove credential validity.
7. Remove the staging file and recovery copy after verified completion.
   Record only sanitized receipts, changed service identity and token names.
   Close the QA row only after both consumer and revocation checks pass.

Before revocation, a UI failure permits restoration of the private old file
and a second UI-only restart within the approved transaction. If revocation
fails, retain the working replacement and report the remaining exposed token;
do not revert a healthy UI to the old credential. After successful revocation,
the old secret cannot be restored as a usable rollback credential.

## Approval and remaining inputs

Execution requires explicit approval for the environment replacement, UI-only
restart, conditional UI-only recovery restart and final named revocation.
Token creation additionally requires the operator's authenticated interface
step and private staging file. Preparation is complete; rotation remains
pending. No production OpenHAB restart, physical action, notification,
helper schedule change or broader credential migration is authorized here.
