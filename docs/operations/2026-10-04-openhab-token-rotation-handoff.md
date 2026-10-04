# OpenHAB credential: existing Hex retained, rotation deferred

## Scope and current state

This records preparation and the subsequent explicit approval for
`SECURITY-TOKEN-ROTATION` in `docs/qa/ui-audit-matrix.csv`. No token has been
created, replaced or revoked, and no service has been restarted by this
transaction. The separate approved sky handoff is already complete.

The operator explicitly approved credentials and private staging on October 4,
following the scoped transaction below. Approval is received for replacement,
UI-only restart, conditional UI-only recovery restart and final named revocation.
The operator subsequently instructed: "Reuse the hex token." This supersedes
execution of the rotation plan: retain and reuse the existing private `Hex`
credential. Replacement and revocation are deferred; the security item stays open.

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

## Deferred rotation procedure

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

## Earlier approval and rotation preflight

At 18:08:54 UTC on October 4, authenticated metadata still contained exactly
`Hex`, `lightning` and `solar`, all with empty scope. An unauthenticated request
to `/rest/auth/apitokens` returned 401, confirming this endpoint can distinguish
successful authentication from anonymous Item access.

Privileged read-only accounting examined 46 UID-1000 processes with no existing
unreadable processes. Three environment holders matched the current credential;
all belonged to the UI family (419027, 419043 and 419044). This closes the earlier
owner-process visibility gap for this instant, not arbitrary external consumers.
Fresh checks are still required at replacement and revocation. Sanitized evidence:
`/tmp/earthship-token-rotation-approved-preflight.json` (0600, UID 1000).

Private storage is ready: `/home/sat/.config/hex` is 0700 and `openhab.env`
is a regular non-symlink 0600 file, both owned by UID 1000. The UI remains active
with MainPID 419027 and its original environment-file configuration. The proposed
`openhab.next.env` staging file is absent.

The installed OpenHAB 5.2.1 console also supports
`openhab:users addApiToken <userId> <tokenName> <scope>` through the normal user
registry; its matching official `UserConsoleCommandExtension` source was checked.
A bounded read-only console connection failed with
`No more authentication methods available`. The configured console account has
a hashed password; no configured public-key login or SSH-agent key is available.
No password was guessed, reset or extracted, and no registry file was modified.

The earlier request for a privately staged replacement was superseded by the
operator's instruction to reuse `Hex`. No replacement staging or account-login
input is required for continuing work with that existing credential. Resume
rotation only if the operator directs that task again. Production OpenHAB
restart, physical action, notifications, helper schedule changes and broader
credential migration remain outside this transaction. Rotation remains
incomplete; `Hex` is still valid.

## Existing credential reuse verification

At 2026-10-04 19:48:57 UTC, authenticated `GET /rest/auth/apitokens` using
the existing private environment credential returned 200 and three tokens,
including `Hex` with empty scope. Earthship UI remained active/running with
MainPID 419027. No credential file was changed, token created or revoked, or
service restarted. The QA row is deferred by operator request, not verified
rotation. The earlier replacement-staging request is no longer pending.
