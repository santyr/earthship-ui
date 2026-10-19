"""Provider-neutral regional reads and Item state updates using the existing identity.

No forecast acquisition, legacy learning state, site fallback or command endpoint.
"""
import json
import os
import urllib.request

BASE = "http://127.0.0.1:8080/rest"
ENV_FILE = os.path.expanduser("~/.config/hex/openhab.env")
I18N_CONFIG_PATH = "/services/org.openhab.i18n/config"
_TOKEN = None


def token():
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip().removeprefix("export ")
            if line.startswith("OPENHAB_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"')
    raise RuntimeError("no token")


def auth_token():
    global _TOKEN
    if _TOKEN is None:
        _TOKEN = token()
    return _TOKEN


def oh_get(path):
    req = urllib.request.Request(BASE + path, headers={"Authorization": "Bearer " + auth_token()})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def oh_put_state(item, value):
    req = urllib.request.Request(f"{BASE}/items/{item}/state", data=str(value).encode(),
                                 headers={"Authorization": "Bearer " + auth_token(),
                                          "Content-Type": "text/plain"}, method="PUT")
    with urllib.request.urlopen(req, timeout=15):
        pass
