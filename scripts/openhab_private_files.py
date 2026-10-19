"""Provider-neutral private preimages for existing attended configuration tools.

Importing this module performs no host read, network operation or mutation.
"""
import os
from pathlib import Path

BACKUP_ROOT = Path('/home/sat/.local/state/openhab-config-migration')
THING_DB = Path('/var/lib/openhab/jsondb/org.openhab.core.thing.Thing.json')
LINK_DB = Path('/var/lib/openhab/jsondb/org.openhab.core.thing.link.ItemChannelLink.json')


def private_file(directory, name, body):
    path = directory / name
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600)
    with os.fdopen(descriptor, 'wb') as output:
        output.write(body)
        output.flush()
        os.fsync(output.fileno())
    return path
