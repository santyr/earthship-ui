"""Read the completed household cycle named by its observation publication."""
from pathlib import Path
import os
from household.codec import loads,canonical
from household_observation import _private_file
from household_solar_score import read_forecast,unchanged
from household_profiled_score import read_forecast as read_profile,unchanged as profile_unchanged
from weather_learning.contracts import digest,identity

ENERGY='.household-energy-forecast-v1.json'
PROFILE='.household-profiled-energy-v1.json'


def read_current_originals(stage,observation_path,*,guard=lambda:None):
    guard();observation_path=Path(observation_path)
    try:observed=_private_file(observation_path,32768)
    except FileNotFoundError:
        # Existing owner temporarily displaces its old cache before linking
        # the verified replacement. No completed observation means no source.
        guard();return None
    view=loads(observed[0])
    if view.get('schema') not in ('earthship-household-observation/v1','earthship-household-observation/v2','earthship-household-observation/v3','earthship-household-observation/v4') or view.get('automatic_actuation') is not False:
        raise ValueError('original read-only household observation required')
    pin=digest(view['receipt_sha256']);energies=[];profiles=[]
    with os.scandir(Path(stage)/'evidence') as entries:
        for i,entry in enumerate(entries):
            if i%100==0:guard()
            if i>=20000:raise ValueError('bounded completed household original inventory required')
            if not entry.name.endswith((ENERGY,PROFILE)):continue
            if not entry.is_file(follow_symlinks=False):raise ValueError('regular original household forecast required')
            row=(entry.stat(follow_symlinks=False).st_mtime_ns,Path(entry.path))
            (energies if entry.name.endswith(ENERGY) else profiles).append(row)
    for _,path in sorted(energies,reverse=True)[:64]:
        guard();candidate=loads(_private_file(path,262144)[0])
        if candidate['inputs']['plan_receipt_sha256']!=pin:continue
        energy,plan,originals=read_forecast(path)
        if plan['receipt_sha256']!=pin:raise ValueError('original household observation/plan binding differs')
        profiled=None;profile_original=None;profile_path=None
        for _,p in sorted(profiles,reverse=True)[:64]:
            guard();value=loads(_private_file(p,262144)[0])
            if value['inputs']['original_energy_document_sha256']!=identity(energy):continue
            profiled,e,other_plan,profile_original=read_profile(p)
            if canonical(e)!=canonical(energy) or canonical(other_plan)!=canonical(plan):raise ValueError('same completed original household profile required')
            profile_path=p;break
        value=dict(energy=energy,plan=plan,profiled=profiled,energy_path=path,profiled_path=profile_path,originals=originals,
            profile_original=profile_original,observation_path=observation_path,observation_original=observed)
        unchanged_current(value);guard();return value
    if _private_file(observation_path,32768)!=observed:raise ValueError('current household observation changed')
    guard();return None


def unchanged_current(value):
    unchanged(value['originals'])
    if value['profile_original'] is not None:profile_unchanged(value['profile_original'])
    if _private_file(value['observation_path'],32768)!=value['observation_original']:raise ValueError('current household observation changed')
