"""Render disabled registered monitoring units; staging grants no release authority."""
from pathlib import Path
import re
from hashlib import sha256
from .forcing_capture import _private_directory,_canonical
from .runtime_bundle import _write_private,_owned_bytes,_sync_directory

FIELDS={'sources','live_config','score_config','registration','release_reference','shared_lock'}


def _operands(values):
    if not isinstance(values,dict) or set(values)!=FIELDS:raise ValueError('closed reviewed scheduling operands required')
    for value in values.values():
        if (not isinstance(value,str) or not 1<=len(value)<=1024 or re.fullmatch(r'/[A-Za-z0-9_./-]+',value) is None or
                str(Path(value))!=value or '..' in Path(value).parts):
            raise ValueError('canonical literal absolute scheduling paths required')
    return values


def _service(template,command):
    lines=[line for line in template.splitlines() if not line.startswith('#')]
    if sum(line.startswith('ExecStart=') for line in lines)!=1:raise ValueError('one bounded worker command required')
    lines=[command if line.startswith('ExecStart=') else line for line in lines]
    if 'UMask=0077' not in lines:lines.insert(lines.index('Type=oneshot')+1,'UMask=0077')
    if any('@' in line or re.search(r'%[A-Za-z]',line) for line in lines):raise ValueError('unresolved scheduling operand')
    return '# Staged review artifact; not installed or enabled.\n'+'\n'.join(lines)+'\n'


def _timer(name,calendar):
    return f'[Unit]\nDescription=Staged registered thermal scheduling\n\n[Timer]\nOnCalendar={calendar}\nAccuracySec=1s\nRandomizedDelaySec=0\nPersistent=false\nUnit={name}.service\n\n[Install]\nWantedBy=timers.target\n'


def render_registered_monitoring_units(*,template_directory,operands):
    values=_operands(operands);root=Path(template_directory);units={}
    score=(root/'thermal-installed-compressed-score-queue.service').read_text()
    index=(root/'thermal-installed-release-index.service').read_text()
    forecast=(root/'thermal-installed-forecast.service').read_text()
    common=f"--contract-version 4 --config {values['score_config']} --shared-lock {values['shared_lock']} --score-registration {values['registration']}"
    for n,hours in enumerate((1,6,12,24)):
        for kind,template,minute in (('score',score,1+5*n),('index',index,2+5*n)):
            name=f'thermal-registered-{kind}-{hours}'
            intent='--batch' if kind=='score' else f"--update-release-index --release-reference {values['release_reference']}"
            command=f"ExecStart=/usr/bin/timeout 60s /usr/bin/python3 {values['sources']}/thermal_installed_score.py {common} --horizon {hours} {intent}"
            units[name+'.service']=_service(template,command)
            units[name+'.timer']=_timer(name,f'*-*-* *:{minute:02d}/20:00 UTC')
    name='thermal-registered-forecast'
    command=f"ExecStart=/usr/bin/python3 {values['sources']}/thermal_installed_intel.py --contract-version 3 --config {values['live_config']} --publish --shared-lock {values['shared_lock']} --score-registration {values['registration']}"
    units[name+'.service']=_service(forecast,command)
    units[name+'.timer']=_timer(name,'*-*-* *:04/5:15 UTC')
    return units


def stage_registered_monitoring_units(*,template_directory,operands,output_directory):
    units=render_registered_monitoring_units(template_directory=template_directory,operands=operands)
    root=_private_directory(Path(output_directory))
    if any(root.iterdir()):raise ValueError('new empty private review directory required')
    hashes={name:sha256(value.encode()).hexdigest() for name,value in units.items()}
    for name,value in units.items():_write_private(root/name,value.encode())
    for name,value in units.items():
        if _owned_bytes(root/name,16384)!=value.encode():raise ValueError('staged unit changed during retention')
    manifest=dict(schema='earthship-registered-monitoring-stage/v1',units=hashes,operands=operands,
        release_authorized=False,services_enabled_by_stage=False)
    _write_private(root/'manifest.json',_canonical(manifest));_sync_directory(root)
    return manifest
