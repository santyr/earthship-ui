"""Render the pinned vendor CoreCell profile without starting gateway software."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import re
import subprocess
import tempfile

IMAGE='xoseperez/basicstation@sha256:cb67945c657012c67145dccdd756baf9a16ba095142cd458db2a5ef9ba97ca10'


def render_station(profile, gateway_eui):
    if not re.fullmatch('[0-9a-f]{16}',gateway_eui):raise ValueError('commissioned lowercase gateway EUI required')
    if not isinstance(profile,dict) or set(profile)!={'SX1302_conf','station_conf'}:
        raise ValueError('vendor CoreCell station schema required')
    config=deepcopy(profile)
    if not all(key in config['SX1302_conf'] for key in ('radio_0','radio_1')):
        raise ValueError('preserve complete vendor radio profile')
    config['SX1302_conf'].update(device='usb:/dev/ttyACM0',pps=False)
    config['station_conf'].update(routerid=gateway_eui,log_level='INFO',gps='')
    return config


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--gateway-eui',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();output=Path(args.output).resolve();output.mkdir(parents=True,exist_ok=True,mode=0o700)
    if (output/'station.conf').exists():raise ValueError('refuse to overwrite commissioned station configuration')
    with tempfile.TemporaryDirectory(dir=output) as stage:
        container=subprocess.check_output(['docker','create','--network','none','--entrypoint','/bin/true',IMAGE],text=True).strip()
        try:
            original=Path(stage)/'corecell.json'
            subprocess.run(['docker','cp','-L',container+':/app/station.corecell.conf',str(original)],check=True)
            profile=json.loads(original.read_text())
        finally:subprocess.run(['docker','rm',container],check=True,stdout=subprocess.DEVNULL)
    path=output/'station.conf';path.write_text(json.dumps(render_station(profile,args.gateway_eui),indent=2)+'\n');path.chmod(0o600)
    print('Rendered private vendor profile; no forwarder started. RF/USB commissioning still required.')


if __name__=='__main__':main()
