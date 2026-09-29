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
both matched their reviewed source/digest. The operator selected Sat's public
client key `5302cd2bfe2dcc76c5a9abcba74e6c5f1a07444b35c25e0cd74bac5b453fb5f6`
for the Earthship signer. It is recorded in `earthship-operator.env.example`.
The operator then staged that exact public allowlist, launcher and log-safe
service template as root-owned files. Independent readback found all three
byte-identical to this checkout. At 10:42:32 MDT on September 29 the operator
ran the credential verifier and started the exact Earthship instance. Read-only
systemd checks after more than two minutes found it `active/running` with the
same main PID, zero restarts and `UnitFileState=disabled`; the installed public
files still match source. This is an attended start, not boot enablement or a
successful NIP-46 client challenge.
No thermal listener or question should be enabled merely because this
template or credential exists.
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

The password-store key described as the old bunker pubkey,
`4bf9fcbda64b18e885ce04d593c37264d3561a1baf3adb8c3fe01b1a8bc7edde`,
is neither Sat's selected client key nor the verified operator user pubkey
`669ebbcccf409ee0467a33660ae88fd17e5379e646e41d7c236ff4963f3c36b6`.
NIP-46 permits a separate remote-signer transport identity, but this `nak`
template uses the credential supplied through `NOSTR_SECRET_KEY` for its
bunker identity. The operator explicitly chose the verified original operator
identity for both roles. The old `4bf9...edde` key must not be used as a
substitute. Sat's client still needs an end-to-end possession and signer trial.
The installed
`nak bunker --authorized-keys` option describes clients for which it will
always respond, not a narrow permission for inbox announcements. Treat a
selected client as able to request signing and decryption until a separate
permission boundary is qualified.

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

### What to run now: stage the Earthship instance, without starting it

Run these from the host as an administrator after reviewing the files in this
directory. They install only the public Sat-client allowlist, launcher and
service template; they neither start a bunker nor enable it at boot. The
original encrypted operator credential and qualified `nak` binary must
already be present. `sudo` may prompt for your password; do not send it here.
Coordinate with the Lightning Goats agent before running this shared-template
installation. An existing destination is accepted only when byte-identical;
the block stops instead of overwriting another project or an active service.

```sh
(
  set -e
  if systemctl is-active --quiet nostr-bunker@earthship-operator.service; then
    echo 'Earthship signer is already active; stop and review it first' >&2
    exit 1
  fi
  sudo /usr/local/libexec/nostr-bunker/verify-earthship-operator-credential
  sudo install -d -o root -g root -m 0755 /etc/nostr-bunker /usr/local/libexec/nostr-bunker
  if sudo test -e /usr/local/libexec/nostr-bunker/run-nak-bunker; then
    sudo cmp /home/sat/earthship-ui/deploy/nostr-bunker/run-nak-bunker /usr/local/libexec/nostr-bunker/run-nak-bunker
  else
    sudo install -o root -g root -m 0755 /home/sat/earthship-ui/deploy/nostr-bunker/run-nak-bunker /usr/local/libexec/nostr-bunker/run-nak-bunker
  fi
  if sudo test -e /etc/nostr-bunker/earthship-operator.env; then
    sudo cmp /home/sat/earthship-ui/deploy/nostr-bunker/earthship-operator.env.example /etc/nostr-bunker/earthship-operator.env
  else
    sudo install -o root -g root -m 0644 /home/sat/earthship-ui/deploy/nostr-bunker/earthship-operator.env.example /etc/nostr-bunker/earthship-operator.env
  fi
  if sudo test -e /etc/systemd/system/nostr-bunker@.service; then
    sudo cmp /home/sat/earthship-ui/deploy/nostr-bunker/nostr-bunker@.service /etc/systemd/system/nostr-bunker@.service
  else
    sudo install -o root -g root -m 0644 /home/sat/earthship-ui/deploy/nostr-bunker/nostr-bunker@.service /etc/systemd/system/nostr-bunker@.service
  fi
  sudo systemd-analyze verify /etc/systemd/system/nostr-bunker@.service
  sudo systemctl daemon-reload
  systemctl show -p UnitFileState -p ActiveState nostr-bunker@earthship-operator.service
)
```

Any executed `cmp` should exit successfully without output; the last command
should show `UnitFileState=disabled` and `ActiveState=inactive`. Stop and report any
different result. The operator has confirmed that Sat's client expects the
verified operator remote-signer pubkey
`669ebbcccf409ee0467a33660ae88fd17e5379e646e41d7c236ff4963f3c36b6`,
not the old password-store bunker pubkey `4bf9...edde`.

The revised unit sends both `nak bunker` output streams to `/dev/null`:
upstream may print a one-time bunker connection secret and request/response
bodies. Never start an older unit that journals either stream, and do not
capture bunker output in tmux, a shell transcript or a support log. Rely on
systemd state and an actual client challenge for verification; discarded
output is intentional.

### Attended start after the identity choice

The operator has selected the verified original operator identity for both
NIP-46 transport and signing. The following starts this instance only; it
does **not** enable it at boot, start the thermal collector, publish a question
or change OpenHAB controls. Run it while present, after checking the service
is still inactive and the three installed files above still match source.
This assistant's shell cannot satisfy `sudo`'s password prompt.

```sh
sudo /usr/local/libexec/nostr-bunker/verify-earthship-operator-credential
sudo systemctl start nostr-bunker@earthship-operator.service
systemctl show -p ActiveState -p SubState -p MainPID -p NRestarts -p UnitFileState nostr-bunker@earthship-operator.service
```

Report only those state fields, not `journalctl`, a QR code or a bunker URL.
Check the same state again after a minute: it should remain `active/running`
with no restart increase. If it fails, flaps, or presents an unexpected
identity, stop it immediately with
`sudo systemctl stop nostr-bunker@earthship-operator.service` and report the
status fields. A healthy service is not proof that Sat's client possesses
`5302...b5f6`; perform a separate NIP-46 `get_public_key`/signed challenge
through the approved client before considering a persistent enable or any
thermal confirmation release. Do not inspect or share `nak`'s suppressed
request/response output.

The September 29 attended start passed the service-liveness check, but the
approved Sat client has not yet completed that challenge. The host user's
default `nak` identity derives to a **different** public key, so running a
client command with default credentials would not test the allowlisted client.
Do not use Hex's sender key as a substitute. Keep this instance disabled at
boot until the holder of Sat's approved client key completes an authenticated
round trip and the returned operator public key matches the verified DM
recipient. If the service fails or restarts unexpectedly, stop the instance;
do not expose a bunker URL or credential to diagnose it in chat or logs.

### Approved operator inbox announcement

The operator approved a single signed kind-10050 announcement listing
`wss://nos.lol`, `wss://relay.primal.net`, and `wss://relay.damus.io` for their
verified identity. `publish-earthship-operator-route` is a root-run, one-shot
path for this already-approved public event; it does not start the NIP-46
bunker, a thermal collector, or any OpenHAB control. It refuses to replace an
existing operator route and requires readback from all three relays. Its
private key exists only in the root process and signing child environment,
never in an argument or output. The operator ran its root-owned installed copy
on September 29; independent readback verified event
`defe6a8571ae87261278bcae968f88d821e304930e7fad5e7e486f46e1fb20d2`
on all three relays. **Do not rerun** the one-shot publisher: it refuses an
existing route, and a future route change needs its own review. The Hex
collector's prior announcement was readable on only one of three relays at
the next checkpoint. The operator chose to retain the current Hex identity;
the exact signed Hex event was republished without a private key and then
read back on all three relays. Both public announcements are now available,
but relay retention can change and the complete private policy/route inventory,
backup, and end-to-end trial are still not qualified. The announcements alone
do not authorize a listener.

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
