import gzip,json
from weather_learning.contracts import identity


def test_large_training_dataset_retains_all_ordered_pairs_in_bounded_files(tmp_path):
 from weather_learning.training_dataset import retain_dataset
 pairs=[{'n':i,'source':'x'*350} for i in range(30)]
 result=retain_dataset(tmp_path,metadata={'kind':'irradiance_w_m2','automatic_actuation':False},pairs=pairs,maximum=2048)
 assert result['pair_count']==len(pairs)
 assert len(result['chunks'])>1
 replay=[]
 for part in result['chunks']:
  raw=gzip.decompress((tmp_path/(part['sha256']+'.pairs.json.gz')).read_bytes())
  assert len(raw)<=2048
  value=json.loads(raw);assert value['chunk_sha256']==identity({k:v for k,v in value.items() if k!='chunk_sha256'})==part['sha256']
  replay.extend(value['pairs'])
 assert replay==pairs
 assert result['dataset_sha256']==identity({k:v for k,v in result.items() if k!='dataset_sha256'})
 assert json.loads((tmp_path/(result['dataset_sha256']+'.dataset.json')).read_bytes())==result


def test_single_oversize_pair_is_refused(tmp_path):
 import pytest
 from weather_learning.training_dataset import retain_dataset
 with pytest.raises(ValueError,match='single'):
  retain_dataset(tmp_path,metadata={'kind':'test'},pairs=[{'raw':'x'*3000}],maximum=2048)
