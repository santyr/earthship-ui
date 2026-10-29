"""Bootstrap auth for only the disposable OpenHAB sensor browser fixture.

The token stays in the private fixture directory and Vite's server process.
No production endpoint, registry, credential or browser configuration is used.
"""
import base64
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import secrets
import urllib.error
import urllib.parse
import urllib.request

from services.lorawan.runtime import private_config
from services.lorawan.tests.stack_ownership import assert_owned_stack, owned_urlopen

OPENHAB = 'http://127.0.0.1:18084'
PRIVATE = Path('.superpowers/lorawan-private')


class Inputs(HTMLParser):
    def __init__(self, body):
        super().__init__(); self.fields = {}; self.feed(body)

    def handle_starttag(self, tag, attrs):
        row = dict(attrs)
        if tag == 'input' and row.get('name'):
            self.fields[row['name']] = row


def request(path, data=None, headers=None):
    payload = None if data is None else urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(OPENHAB + path, data=payload, headers=headers or {})
    with owned_urlopen(req, timeout=5) as response:
        body = response.read(65537)
        if len(body) > 65536:raise ValueError('bounded disposable auth response required')
        return body.decode()


def prepare_browser_auth():
    if (os.environ.get('SENSOR_INTEGRATION') != '1' or
        private_config(PRIVATE / 'ingest.json')['environment'] != 'simulation'):
        raise ValueError('explicit disposable simulation fixture required')
    assert_owned_stack()
    path = PRIVATE / 'browser-auth.json'
    if path.exists():
        token = private_config_token(path)
    else:
        client = OPENHAB
        params = dict(response_type='code',client_id=client,redirect_uri=client,scope='admin')
        form = Inputs(request('/auth?' + urllib.parse.urlencode(params))).fields
        if form.get('password_repeat',{}).get('type') != 'password':
            raise ValueError('refuse creating accounts in an initialized OpenHAB instance')
        password = secrets.token_hex(24)
        params.update(csrf_token=form['csrf_token']['value'],username='sensorqualification',
                      password=password,password_repeat=password)
        request('/auth',params)
        form = Inputs(request('/createApiToken')).fields
        body = request('/createApiToken',dict(csrf_token=form['csrf_token']['value'],
            username='sensorqualification',password=password,token_name='sensorqualification',token_scope='admin'))
        matches = re.findall(r'<code>(oh\.[A-Za-z0-9.]+)</code>',body)
        if len(matches) != 1:raise ValueError('disposable API token creation failed')
        token = matches[0]
        path.write_text(json.dumps(dict(token=token)));path.chmod(0o600)
    authorization = 'Basic ' + base64.b64encode((token + ':').encode()).decode()
    things = json.loads(request('/rest/things?summary=true',headers={'Authorization':authorization}))
    if not isinstance(things,list):raise ValueError('authenticated disposable Thing collection required')
    return path


def private_config_token(path):
    if path.stat().st_mode & 0o077:raise ValueError('private fixture token permissions required')
    value = json.loads(path.read_bytes())
    if set(value) != {'token'} or not isinstance(value['token'],str):raise ValueError('fixture token required')
    return value['token']


if __name__ == '__main__':
    prepare_browser_auth()
    print('Prepared authenticated disposable OpenHAB proxy fixture')
