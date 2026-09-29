# Local multi-project NIP-46 signer template (source only)

The retired Lightning Goats VPS unit is a useful precedent, but its key and
client were project-specific. This template gives **each signing identity** its
own systemd instance, encrypted credential, authorized-client list, relay list,
and private runtime directory. For example, `nostr-bunker@earthship-operator`
and `nostr-bunker@lightning-goats` must use different credentials. Do not infer
that the Lightning Goats key is the Earthship operator key.

This checkout does not install or start a bunker. The operator key and its
authorized NIP-46 client key have not been located or provisioned on this host.
No thermal listener or question should be enabled because this template exists.

## Installation boundary

An attended administrator must review the instance name and its public key,
then install the launcher and a qualified `nak` binary into a root-owned,
non-group-writable `/usr/local/libexec/nostr-bunker/` directory. The launcher
requires that exact binary path to be regular, non-symlink, root-owned,
non-group/other-writable, and equal to the instance's pinned SHA-256. Do not
use this host's currently group-writable `/usr/local/bin/nak` for the bunker.
Install the unit as `/etc/systemd/system/nostr-bunker@.service`.

For each identity `<name>`, create a non-secret
`/etc/nostr-bunker/<name>.env` from `instance.env.example` with only that
identity's approved client **public** keys, selected `wss://` relays, and the
binary digest. Use a separate systemd-encrypted key credential at
`/etc/credstore.encrypted/nostr-bunker-<name>.key`; the credential must be
named `nostr-key` inside the service. Keep the unencrypted key out of argv,
shell history, repository files and chat. Use a private input path when
encrypting it, and remove any transient plaintext after readback validation.
The service never persists its client allowlist: all clients must be explicitly
listed in the instance environment file.

Before enabling an instance, verify its signing public key against the
intended project identity, its exact client allowlist and relay set, and that
the encrypted credential decrypts only in that instance. A NIP-46 authorized
client can request signing operations; never add the Hex collector/client just
to make the operator's kind-10050 announcement. The operator should publish
that announcement with their own approved NIP-46 client. Independently verify
the signed event and all chosen relay endpoints before starting the thermal
confirmation collector. No cross-project signer fallback is allowed.

The same unit and launcher can be shared by projects, but `earthship-ui` only
contains this source template until a reviewed common deployment location is
chosen. Moving the template does not transfer or select an identity.
