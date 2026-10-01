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
through the approved client before any thermal confirmation release. Do not
inspect or share `nak`'s suppressed
request/response output.

The September 29 attended start passed the service-liveness check. The Sat
client subsequently completed the challenge: the helper reported a signed
operator test note, and independent read-only signature/author/content/event-ID
checks found event `fac909b6c4bf8dbbdc30e551f410c717a0bcd1d94c25f5eb96bfb3b976c94cf6`
on nos.lol and relay.primal.net, but not relay.damus.io (2/3). The bunker
remained active/running with zero restarts and boot enablement on. This proves
the attended Sat-client signing path, **not** NIP-17 confirmation ingress,
journal storage/recovery, or unattended thermal-collector readiness. The host user's
default `nak` identity derives to a **different** public key, so running a
client command with default credentials would not test the allowlisted client.
The `nostr-bunker@earthship-operator` unit stores only the operator signing
credential; its environment file stores Sat's **public** client key as an
allowlist entry. Installing or starting this unit does not create, import, or
store Sat's client private key. A filename-only check of the local password
store, systemd units, and Lightning Goats checkout found no matching local
client-key entry or client service. The client-key holder must identify the
original key location privately. If it is lost, choose and authorize a new
dedicated client identity before changing the allowlist; never substitute the
operator or Hex sending credential.

To check a candidate **Sat client** nsec locally, run the following in a
trusted interactive Bash shell as `sat`. Paste the nsec only at the hidden
prompt, never into a command, chat, log, or shell-history line. This uses the
installed pinned `nak` and reports only a public-key match result:

```bash
set +x
IFS= read -r -s -p 'Sat client nsec: ' sat_client_nsec; printf '\n'
if sat_client_pub=$(NOSTR_SECRET_KEY="$sat_client_nsec" /usr/local/libexec/nostr-bunker/nak key public); then
  unset -v sat_client_nsec
  if [ "$sat_client_pub" = '5302cd2bfe2dcc76c5a9abcba74e6c5f1a07444b35c25e0cd74bac5b453fb5f6' ]; then
    printf 'Sat client key matches the bunker allowlist\n'
  else
    printf 'Mismatch: this is not the approved Sat client key\n'
  fi
  unset -v sat_client_pub
else
  unset -v sat_client_nsec sat_client_pub
  printf 'Could not derive the client public key\n' >&2
fi
```

The secret is briefly in this shell and `nak`'s process environment, so use a
trusted local session and close it afterward. A matching public key proves
only the local key pair; it does not prove the client can authenticate to the
running bunker, obtain its operator public key, or safely sign a request.
To complete the attended round trip from a private terminal as `sat`, run:

```bash
python3 /home/sat/earthship-ui/deploy/nostr-bunker/challenge-earthship-operator
```

Enter the same Sat client nsec at its hidden prompt. The helper checks the
root-owned pinned `nak`, running service, client allowlist identity, remote
operator identity, and an actual remote signature. It then publishes **one**
short, explicitly labelled kind-1 test note (the same signed event) to the
three approved relays and requires at least one exact event-ID readback.
It prints only a pass/fail summary and the public test event ID; it neither
stores the key nor runs a thermal question or control. A local key match alone
or an active service does not count as challenge completion. Keep the terminal
private; the nsec is briefly present in the client process environment.
Do not use Hex's sender key as a substitute. The operator enabled this service
at boot before completing the challenge. Do not treat boot
enablement as an authentication or thermal release gate. If the service fails,
restarts unexpectedly, or presents another identity, stop the instance; do
not expose a bunker URL or credential to diagnose it in chat or logs.

The operator has already enabled the instance at boot. To inspect that
configuration after the challenge (or re-enable it if intentionally disabled):

```bash
sudo systemctl enable nostr-bunker@earthship-operator.service
systemctl is-enabled nostr-bunker@earthship-operator.service
systemctl show -p ActiveState -p SubState -p NRestarts nostr-bunker@earthship-operator.service
```

The expected enablement result is `enabled`; the service should remain
`active/running` with no new restart. `enable` changes boot policy only and
does not restart the current process. To undo boot enablement without stopping
the running instance, use
`sudo systemctl disable nostr-bunker@earthship-operator.service`.

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

### Primal compatibility sender (collector not activated)

The [October 1 Primal candidate](../../docs/operations/2026-10-01-primal-compatibility-candidate.md)
documents a bounded NIP-04 stdin patch, disposable-key tests, and the remaining
delivery/recovery gates. Neither the installed bunker binary nor its pin is
changed. Do not replace this running signer with the qualification build or
use the candidate to publish a live thermal question. NIP-04 compatibility is
an explicit transport choice, not fallback for existing NIP-17 intents.

The separate `openhab/scripts/thermal_primal.py` command now has source-only
`--check-config` and `--check-keyer` modes. Both require an explicit private v2
policy, signed routes, signer path, SHA-256 and exact version; the latter also
requires the **Hex collector** identity for local self-roundtrips, not the
operator recipient's key. The installed stock signer fails the required
NIP-04 stdin encoding check. Do not repurpose the operator's bunker credentials
or replace its binary to get that check to pass. The candidate user units at
`deploy/thermal-primal.service` and `.timer` are not installed or enabled.
Their private environment template is `deploy/thermal-primal.env.example`.
Exact sender qualification, full recovery, configuration review and an attended
Primal receipt trial remain necessary; see the linked operations document.

The separately built sender candidate is now distinctly versioned as
`nak version v0.20.7-earthship-nip04-stdin.1`, pinned to SHA-256
`2620c86f7a2b466a41977ae7e318d1810c727503deaf53ea1c76a5ac24e6f927`.
Its actual stdin crypto, NIP-17 regressions, loopback NIP-42 authentication and
configured Hex local-key self-roundtrips pass. The existing Hex sending key is
local, not a NIP-46 connection; no candidate remote-bunker compatibility is
claimed. The operator bunker and both installed stock binaries remain unchanged.
Any approved installation uses a separate versioned Hex executable path;
it must not replace `/usr/local/libexec/nostr-bunker/nak` or enable collection.

The operator has now approved that additive installation. Its installed path is
`/home/sat/.local/libexec/earthship-thermal/nak-v0.20.7-earthship-nip04-stdin.1`,
owned `sat:sat` mode 0755 under private mode-0700 directories. Exact installed
byte/version checks and all 59 focused crypto/command tests pass. There is no
default alias change or collector unit installation. The actual runtime/private
configuration and full recovery gates remain open; see the operations document
for the credential-free installed-path qualification command. Do not reinstall
the operator bunker or replace any existing `nak` to continue this work.

The subsequently approved **inactive** Primal collector is staged separately at
`/home/sat/.local/libexec/earthship-thermal/primal-v1`, with frozen code, a private
virtual environment and retained hash-pinned dependency wheels. Its new private
configuration at `/home/sat/.config/hex/thermal-primal/` has **zero questions**;
the mode-0600 environment file supplies only the existing Hex/restricted journal
identity. Actual temporary user-unit configuration, signer and read-only journal
checks pass. No permanent collector unit/timer or live state is created, and no
question is sent. Full exact-bundle recovery and the attended signed-reply trial
remain release prerequisites. The operator bunker still needs no change.

### Qualified installation requirements

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
