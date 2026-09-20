#!/usr/bin/env python3
"""Legacy CoinMarketCap helper; not the live OpenHAB Strike feed.

Preserves legacy argument/output behavior. Credentials are never stored here.
"""
import json
import os
from pathlib import Path
import stat
import sys

from requests import Session
from requests.exceptions import ConnectionError, Timeout, TooManyRedirects


def load_api_key(path=None):
    value = os.environ.get('CMC_PRO_API_KEY')
    if value is None:
        path = path or Path.home() / '.config/hex/coinmarketcap_api_key'
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd) as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) != 0o600):
                raise ValueError('CoinMarketCap key file must be owned by this user and mode 0600')
            value = stream.read(4097).strip()
    if not value or len(value) > 4096 or any(c.isspace() for c in value):
        raise ValueError('Invalid CoinMarketCap credential configuration')
    return value


def main():
    # Deliberately retain legacy quote selection and formatting in this cleanup.
    parameters = {'id': sys.argv[1], 'convert': 'USD'}
    session = Session()
    session.headers.update({'Accepts': 'application/json', 'X-CMC_PRO_API_KEY': load_api_key()})
    try:
        response = session.get('https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest', params=parameters)
        data = json.loads(response.text)
        if sys.argv[1] == '1':
            quote = round(data.get('data', {}).get('1', {}).get('quote', {}).get('USD', {}).get('price', {}))
            print('%g' % quote)
        if sys.argv[1] == '2':
            print(data.get('data', {}).get('1', {}).get('quote', {}).get('USD', {}).get('percent_change_24h', {}))
    except (ConnectionError, Timeout, TooManyRedirects) as error:
        print(error)


if __name__ == '__main__':
    main()
