# OpenHAB credential reuse decision

On October 4, 2026, the operator instructed the agent to reuse the existing
`Hex` token and then remove credential rotation from the requirements and plan.
Continue using the private credential in `/home/sat/.config/hex/openhab.env`.
Keep credential values outside Git, reports and chat.

The rotation requirement has been removed from the canonical UI audit matrix
and its required-ID contract. The former replacement, private staging, service
restart and token-revocation procedure has been removed from the active plan.
No replacement token or account-login input is required for credential reuse.

The last authenticated reuse check returned HTTP 200 with `Hex` present at
empty scope, and Earthship UI was active/running with MainPID 419027. This is
an authentication receipt; credential rotation was not performed. This scope
update changes documentation and the audit contract only.
