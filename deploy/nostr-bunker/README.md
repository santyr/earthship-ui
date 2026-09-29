# Local multi-project NIP-46 signer template (source only)

The retired Lightning Goats VPS unit is a useful precedent, but its key and
client were project-specific. This template gives **each signing identity** its
own systemd instance, encrypted credential, authorized-client list, relay list,
and private runtime directory. For example, `nostr-bunker@earthship-operator`
and `nostr-bunker@lightning-goats` must use different credentials. Do not infer
that the Lightning Goats key is the Earthship operator key.

This checkout does not install or start a bunker. On September 29 the operator
reported provisioning the original operator key as a mode-0600, root-owned
systemd-encrypted credential on this host. A root-run, offline check of the
installed verifier reported that the credential derives to the existing DM
recipient; the verifier's installed bytes and the qualified root-owned `nak`
both matched their reviewed source/digest. The authorized NIP-46 client key
is still not provisioned. No thermal listener or question should be enabled
because this template or credential exists.
The operator subsequently named `npub1v60thnx0gz0wq3n6xdnq46y069l9x70xgmjp6lprdl6fv0eux6mqgjj4rp`
as the intended DM recipient. A read-only public-key comparison confirmed
that this npub matches OpenHAB's current configured DM recipient. The later
root-run verifier result also matched the credential to this public identity.
The operator also identified Hex's sender as
`npub1qkjnsgk6zrszkmk2c7ywycvh46ylp3kw4kud8y8a20m93y5synvqewl0sq`.
A local public-key derivation confirmed that OpenHAB's current DM sender
matches it. This is a distinct identity from the operator/recipient; never
put Hex's sending key in the operator bunker credential or client allowlist.

The host reported that `/var/lib/systemd/credential.secret` is not on encrypted
media. A host-bound encrypted credential is not protection against an attacker
who obtains the entire unencrypted drive. Keep the original key's separate
offline backup and review full-disk encryption or hardware-backed credentials
before exposing this signer beyond the local household. Do not mistake mode
0600 for disk-at-rest encryption.

### Offline identity verification

After reviewing the source and its fixed digest, an administrator can install
the qualified `nak` binary and one-shot verifier as root-owned files:

```sh
sudo install -d -o root -g root -m 0755 /usr/local/libexec/nostr-bunker
sudo install -o root -g root -m 0755 /home/sat/.local/bin/nak /usr/local/libexec/nostr-bunker/nak
sudo install -o root -g root -m 0755 /home/sat/earthship-ui/deploy/nostr-bunker/verify-earthship-operator-credential /usr/local/libexec/nostr-bunker/verify-earthship-operator-credential
sudo /usr/local/libexec/nostr-bunker/verify-earthship-operator-credential
```

The verifier does not connect to a relay, start a service, print the secret or
authorize a NIP-46 client. It fails if the pinned binary changed, decryption
fails, or the derived public key differs from either the operator-approved npub
or OpenHAB's current DM recipient. The absolute source path works from any
working directory.

### Approved operator inbox announcement

The operator approved a single signed kind-10050 announcement listing
`wss://nos.lol`, `wss://relay.primal.net`, and `wss://relay.damus.io` for their
verified identity. `publish-earthship-operator-route` is a root-run, one-shot
path for this already-approved public event; it does not start the NIP-46
bunker, a thermal collector, or any OpenHAB control. It refuses to replace an
existing operator route and requires readback from all three relays. Its
private key exists only in the root process and signing child environment,
never in an argument or output. Install from an absolute source path so the
working directory cannot change what is installed:

```sh
sudo install -o root -g root -m 0755 /home/sat/earthship-ui/deploy/nostr-bunker/publish-earthship-operator-route /usr/local/libexec/nostr-bunker/publish-earthship-operator-route
sudo /usr/local/libexec/nostr-bunker/publish-earthship-operator-route
```

Do not blindly rerun after a partial publish: the signed event may already be
on some relays. First query the public event ID, compare its signature and
exact relay tags, then repair only missing relay copies. The announcement
alone does not qualify NIP-17 confirmation delivery or authorize a listener.

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
