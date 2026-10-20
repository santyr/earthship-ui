"""Retain exact production Python bytes used by a historical experiment."""
from pathlib import Path
from hashlib import sha256
import os


def capture_sources(root):
    root=Path(root);result={}
    for path in sorted((root/'openhab/scripts').rglob('*.py')):
        if path.name.startswith('test_') or any(p in ('tests','__pycache__','.venv') for p in path.relative_to(root).parts):continue
        raw=path.read_bytes()
        if len(raw)>1024**2:raise ValueError('bounded training source required')
        result[str(path.relative_to(root))]=raw
    if not result or len(result)>1000 or sum(map(len,result.values()))>16*1024**2:raise ValueError('bounded production source closure required')
    return result


def verify_sources(root,sources):
    if capture_sources(root)!=sources:raise ValueError('training runtime source changed during experiment')


def retain_sources(output,sources):
    output=Path(output);manifest={}
    for name,raw in sources.items():
        path=output/'sources'/name;path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as stream:stream.write(raw)
        manifest[name]=sha256(raw).hexdigest()
    return manifest
