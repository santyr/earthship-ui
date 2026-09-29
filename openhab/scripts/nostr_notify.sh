#!/bin/bash
# Legacy OpenHAB NIP-04 DM sender. Keep in repo until sender-key migration.
# Success means one or more relay ACKs, not operator receipt.
set -uo pipefail
set +x
umask 077
ulimit -c 0

MSG="${1:?usage: nostr_notify.sh <message>}"
source /etc/openhab/misc/nostr_notify.env
NAK=/etc/openhab/scripts/nak
export XDG_CONFIG_HOME="$(mktemp -d)"
trap 'rm -rf "$XDG_CONFIG_HOME"' EXIT

# nak accepts NOSTR_SECRET_KEY from the environment. Never put the sender key
# in argv, where process-list readers can see it. Keep it out of publish too.
export NOSTR_SECRET_KEY="$NOSTR_SECRET_KEY_HEX"
unset NOSTR_SECRET_KEY_HEX
CT="$(timeout -k 2 10 "$NAK" -q encrypt --nip04 -p "$NOTIFY_PUBKEY_HEX" "$MSG")" || {
  unset NOSTR_SECRET_KEY
  echo 'encrypt failed/timeout' >&2
  exit 1
}
TPL="$(python3 -c "import json,sys; print(json.dumps({'kind':4,'tags':[['p',sys.argv[1]]],'content':sys.argv[2]}))" "$NOTIFY_PUBKEY_HEX" "$CT")"
EV="$(printf '%s' "$TPL" | timeout -k 2 10 "$NAK" -q event 2>/dev/null)" || {
  unset NOSTR_SECRET_KEY
  echo 'sign failed/timeout' >&2
  exit 1
}
unset NOSTR_SECRET_KEY

OUT="$(printf '%s' "$EV" | timeout -k 2 20 "$NAK" event $RELAYS 2>&1 >/dev/null || true)"
OKS=$(printf '%s\n' "$OUT" | grep -c 'success')
if [ "$OKS" -ge 1 ]; then
  echo "DM sent ($OKS/3 relays)"
  exit 0
fi
echo "DM publish failed: $(printf '%s' "$OUT" | tr '\n' ' ' | tail -c 300)" >&2
exit 1
