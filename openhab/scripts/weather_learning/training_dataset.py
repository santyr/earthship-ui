"""Bounded private training datasets; source rows are never downsampled."""
from pathlib import Path
import gzip,os
from .contracts import canonical,identity


def retain_dataset(root,*,metadata,pairs,maximum=32*1024**2):
    from household_native_training import save
    if not isinstance(pairs,list) or not 1<=len(pairs)<=50000 or not 1024<=maximum<=32*1024**2:
        raise ValueError('bounded training pairs required')
    if set(metadata)&{'schema','pairs','pair_count','chunks','dataset_sha256'}:raise ValueError('separate dataset metadata required')
    root=Path(root);parts=[];rows=[];size=512
    def flush():
        value=dict(schema='earthship-historical-learning-pair-chunk/v1',pairs=list(rows));value['chunk_sha256']=identity(value);raw=canonical(value)
        if len(raw)>maximum:raise ValueError('bounded training chunk required')
        path=root/(value['chunk_sha256']+'.pairs.json.gz');encoded=gzip.compress(raw,compresslevel=3,mtime=0)
        try:fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        except FileExistsError:
            from weather_source_files import _read
            if _read(path,maximum)!=encoded:raise ValueError('original training chunk differs')
        else:
            with os.fdopen(fd,'wb') as stream:stream.write(encoded);stream.flush();os.fsync(stream.fileno())
        parts.append(dict(sha256=value['chunk_sha256'],pair_count=len(rows),uncompressed_bytes=len(raw)))
    for pair in pairs:
        length=len(canonical(pair))+1
        if length+512>maximum:raise ValueError('single training pair exceeds bound')
        if rows and size+length>maximum:flush();rows=[];size=512
        rows.append(pair);size+=length
    if rows:flush()
    result=dict(schema='earthship-historical-learning-dataset/v2',**metadata,pair_count=len(pairs),chunks=parts)
    result['dataset_sha256']=identity(result)
    if len(canonical(result))>maximum:raise ValueError('bounded training dataset manifest required')
    save(root/(result['dataset_sha256']+'.dataset.json'),result);return result
