"""Explicit production caller; never generates or infers release qualification.

A private, externally reviewed release decision pins original gate reports.
Successful parsing authenticates that decision's bytes, not scientific skill.
The default operation checks admission and REST ownership without publishing.
"""
from datetime import datetime,timedelta,timezone
from hashlib import sha256
import json,os,re,stat,subprocess
from pathlib import Path
from urllib.error import URLError
from astro_forecast_context import ITEM as ASTRO_ITEM
from .archive import Archive
from .config import Site
from .contracts import digest,identity,instant
from .production_runtime import ProductionTransport,ITEM_TYPES,run_publication
from openhab_runtime_io import BASES,ReadBudget,SharedScoreLock
from weather_source_files import _directory,_read

CONFIG_SCHEMA='earthship-weather-production-config/v1'
RELEASE_SCHEMA='earthship-weather-reviewed-release/v1'
GATES=frozenset({'access','provenance','prospective_acquisition','temperature','solar',
    'precipitation','downstream','regression','rollback','operational_health'})
INCUMBENT_UNITS=tuple('forecast-'+name+suffix for name in ('intel','json','pre-dusk') for suffix in ('.service','.timer'))
PATH_FIELDS={'archive','evidence_directory','shared_lock','token_file','release_path','items_directory'}
FIELDS=PATH_FIELDS|{'schema','openhab_base','release_sha256','item_files','code_revision','runtime_manifest','items_directory_metadata'}
RELEASE_FIELDS={'schema','provider','decision','reviewed_at','reviewed_by','code_revision','runtime_sha256',
    'site','horizon_hours','weather_lineage','automatic_actuation','gates','item_ownership_sha256'}
SOURCE_FILES=tuple('openhab/scripts/weather_learning/'+name+'.py' for name in (
    '__init__','archive','config','contracts','evidence','features','normalize','provider',
    'weathernext_ee','transport','production_publish','production_runtime','production_worker',
    'refresh_runtime','refresh_queue','refresh_scoring','refresh_evaluation','near_term_correction',
    'historical_serving','site_calibration','historical_pairs','weather_response','weights','publish','shadow','training','provenance','worker'))+tuple(
    'openhab/scripts/'+name+'.py' for name in ('weather_publish','weather_source_files',
    'openhab_runtime_io','astro_forecast_context','hourly_temperature_runtime','daily_temperature_runtime',
    'weather_temperature_config','weather_temperature_history','weather_temperature_reader','weather_temperature_evidence','household_cycle_resources','household_job_run','household_job_launch',
    'household_job_start','household_job_pool','household_job_budget','thermal_model/__init__',
    'thermal_model/capture_guard'))+('scripts/run-household-job.py',
    'deploy/weathernext-publish.service','deploy/weathernext-publish.timer')
from .probabilistic_artifacts import NUMERICAL_FILES
SOURCE_FILES=tuple(sorted(set(SOURCE_FILES)|set(NUMERICAL_FILES)|{
    'openhab/scripts/weather_learning/'+name+'.py' for name in (
        'production_forecast','production_emissions','production_scoring','production_training','production_model_admission',
        'probabilistic_evaluation','marginal_outcomes','probabilistic_issue','wind_history','correction_monitor','solar_shadow')}|{
    'openhab/scripts/production_model_train.py','docs/operations/weathernext3-capabilities/deployment-policy.json',
    'docs/operations/weathernext3-capabilities/marginal-calibration-protocol.json'}))
ROOT=Path(__file__).resolve().parents[3]


def runtime_manifest():
    return {name:sha256(_read(ROOT/name,262144,source=True)).hexdigest() for name in SOURCE_FILES}


def _object(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('duplicate configuration field')
        result[key]=value
    return result


def _json(raw):
    def invalid(_):raise ValueError('nonfinite configuration refused')
    return json.loads(raw,object_pairs_hook=_object,parse_constant=invalid)


def _path(name):
    if not isinstance(name,str) or not 1<=len(name)<=1024:raise ValueError('bounded explicit path required')
    path=Path(name)
    if not path.is_absolute() or path.resolve()!=path:raise ValueError('resolved original path required')
    return path


def incumbent_units():
    raw=subprocess.check_output(['/usr/bin/systemctl','--user','show','--no-pager',
        '--property=Id,LoadState,ActiveState,UnitFileState',*INCUMBENT_UNITS],
        stdin=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=3)
    if len(raw)>16384:raise ValueError('bounded writer registry required')
    result={}
    for block in raw.decode('utf-8').strip().split('\n\n'):
        record=_object(line.split('=',1) for line in block.splitlines())
        name=record.get('Id')
        if name in result:raise ValueError('duplicate writer unit')
        result[name]=record
    return result


def _stopped(reader):
    values=reader()
    if not isinstance(values,dict) or set(values)!=set(INCUMBENT_UNITS):raise ValueError('complete incumbent writer registry required')
    for name,row in values.items():
        if not isinstance(row,dict) or row.get('Id')!=name:raise ValueError('exact incumbent unit required')
        if row.get('LoadState')=='not-found' and row.get('ActiveState')=='inactive':continue
        if (row.get('LoadState') not in ('loaded','masked') or row.get('ActiveState') not in ('inactive','failed') or
                row.get('UnitFileState') not in ('disabled','masked','static')):
            raise ValueError('incumbent writers must be stopped and disabled')
        if name.endswith('.timer') and row['UnitFileState']=='static':raise ValueError('incumbent timer must be disabled')


def _installed_item_bytes(path,directory_uid):
    # Installed files can belong to root, the publisher, or the separately
    # reviewed OpenHAB directory owner. Private config still uses _read.
    before=path.lstat()
    if (not stat.S_ISREG(before.st_mode) or before.st_uid not in (0,os.getuid(),directory_uid) or
            before.st_mode&0o022 or before.st_size>262144 or path.resolve()!=path):
        raise ValueError('owned immutable installed Item source required')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
    with os.fdopen(fd,'rb') as handle:
        opened=os.fstat(handle.fileno());raw=handle.read(262145);after=os.fstat(handle.fileno())
    if (len(raw)!=before.st_size or len(raw)>262144 or
            (before.st_dev,before.st_ino)!=(opened.st_dev,opened.st_ino) or
            (opened.st_size,opened.st_mtime_ns,opened.st_ctime_ns)!=(after.st_size,after.st_mtime_ns,after.st_ctime_ns)):
        raise ValueError('installed Item source changed during read')
    return raw


def _item_sources(settings):
    root=_path(settings['items_directory']);info=root.lstat()
    metadata=settings['items_directory_metadata']
    if (not isinstance(metadata,dict) or set(metadata)!={'uid','gid','mode'} or
            any(type(value) is not int or value<0 for value in metadata.values()) or
            not stat.S_ISDIR(info.st_mode) or info.st_mode&0o002 or
            metadata!=dict(uid=info.st_uid,gid=info.st_gid,mode=stat.S_IMODE(info.st_mode))):
        raise ValueError('reviewed installed Item directory identity required')
    pins=settings['item_files']
    if (not isinstance(pins,dict) or not 1<=len(pins)<=11 or
            any(not isinstance(name,str) or re.fullmatch(r'[A-Za-z0-9_-]+\.items',name) is None for name in pins)):
        raise ValueError('explicit installed Item file pins required')
    for value in pins.values():digest(value)
    seen={};total=0;files=sorted(root.glob('*.items'))
    if len(files)>1024:raise ValueError('bounded installed Item inventory required')
    for path in files:
        raw=_installed_item_bytes(path,info.st_uid);total+=len(raw)
        if total>8*1024*1024:raise ValueError('bounded installed Item bytes required')
        if path.name in pins and sha256(raw).hexdigest()!=pins[path.name]:raise ValueError('installed Item file changed')
        # Inspect declarations only; comments and labels cannot create owners.
        text=re.sub(r'"(?:\\.|[^"\\])*"|/\*.*?\*/|//[^\n]*',' ',raw.decode('utf-8'),flags=re.S)
        for match in re.finditer(r'\b([A-Za-z][A-Za-z0-9_:]*(?:\([^)]*\))?)\s+([A-Za-z0-9_]+)\b',text):
            if match[2] not in ITEM_TYPES:continue
            name=match[2]
            if name in seen or match[1]!=ITEM_TYPES[name] or path.name not in pins:
                raise ValueError('one exact file declaration per forecast Item required')
            seen[name]=path.name
    if set(seen)!=set(ITEM_TYPES) or not set(pins)<=set(path.name for path in files):
        raise ValueError('all retained forecast Item definitions required')


class Admission:
    def __init__(self,path,*,guard,unit_reader,clock):
        if not all(callable(value) for value in (guard,unit_reader,clock)):raise ValueError('explicit operational guards required')
        self.path=_path(str(path));_directory(self.path.parent)
        self.raw=_read(self.path,65536);self.settings=_json(self.raw)
        settings=self.settings
        if not isinstance(settings,dict) or set(settings)!=FIELDS or settings['schema']!=CONFIG_SCHEMA or settings['openhab_base'] not in BASES:
            raise ValueError('closed Google production configuration required')
        for field in PATH_FIELDS:_path(settings[field])
        if not isinstance(settings['code_revision'],str) or re.fullmatch('[a-f0-9]{40}',settings['code_revision']) is None:
            raise ValueError('original source revision required')
        digest(settings['release_sha256'])
        self.guard=guard;self.unit_reader=unit_reader;self.clock=clock
        self.release_raw=_read(_path(settings['release_path']),65536)
        self.release=_json(self.release_raw)
        self.token_raw=_read(_path(settings['token_file']),16384)
        tokens=[line.strip().removeprefix('export ').split('=',1)[1].strip().strip('"')
            for line in self.token_raw.decode('utf-8').splitlines()
            if line.strip().removeprefix('export ').startswith('OPENHAB_TOKEN=')]
        if len(tokens)!=1 or not 1<=len(tokens[0])<=4096 or any(ord(c)<32 for c in tokens[0]):raise ValueError('existing private OpenHAB token required')
        self.token=tokens[0]
        self.admission_sha256=identity(dict(config_sha256=sha256(self.raw).hexdigest(),release_sha256=settings['release_sha256']))
        self.verify()

    def verify(self,provider=None):
        self.guard();settings=self.settings;release=self.release;now=self.clock()
        if (_read(self.path,65536)!=self.raw or _read(_path(settings['release_path']),65536)!=self.release_raw or
                sha256(self.release_raw).hexdigest()!=settings['release_sha256'] or
                _read(_path(settings['token_file']),16384)!=self.token_raw):raise ValueError('original production admission changed')
        if settings['runtime_manifest']!=runtime_manifest():raise ValueError('executing production runtime changed')
        if (not isinstance(release,dict) or set(release)!=RELEASE_FIELDS or release['schema']!=RELEASE_SCHEMA or
                release['provider']!='weathernext3' or release['decision']!='APPROVED_FOR_CUTOVER' or
                release['code_revision']!=settings['code_revision'] or release['runtime_sha256']!=identity(settings['runtime_manifest']) or
                release['weather_lineage']!=['weathernext3','qualified_local_measurements'] or
                release['automatic_actuation'] is not False or type(release['horizon_hours']) is not int or release['horizon_hours']!=336 or
                not isinstance(release['reviewed_by'],str) or not 1<=len(release['reviewed_by'])<=128 or
                instant(release['reviewed_at'])>now):raise ValueError('externally reviewed Google-only release required')
        if not isinstance(release['site'],dict) or set(release['site'])!={'latitude','longitude','timezone'}:raise ValueError('reviewed authoritative site required')
        Site(**release['site'])
        gates=release['gates']
        if not isinstance(gates,dict) or set(gates)!=GATES:raise ValueError('all existing release gates required')
        for gate in gates.values():
            if not isinstance(gate,dict) or set(gate)!={'status','evidence_path','sha256'} or gate['status']!='PASS':
                raise ValueError('reviewed original gate report required')
            digest(gate['sha256'])
            if sha256(_read(_path(gate['evidence_path']),1024*1024)).hexdigest()!=gate['sha256']:
                raise ValueError('original gate report changed')
        ownership={key:settings[key] for key in ('items_directory','items_directory_metadata','item_files')}
        if release['item_ownership_sha256']!=identity(ownership):raise ValueError('reviewed Item ownership differs')
        _item_sources(settings);_stopped(self.unit_reader)
        if provider is not None:
            body=provider.to_dict()
            if body['timezone']!=release['site']['timezone'] or body['required_horizon_seconds']!=336*3600:
                raise ValueError('reviewed provider context differs')
            if 'near_term' in body:
                near=body['near_term']
                if (body['schema']!='earthship-weathernext-publication-provider/v2' or
                        near['required_horizon_seconds']!=24*3600 or near['decision_at']!=body['decision_at'] or
                        near['timezone']!=body['timezone'] or near['required_variables']!=body['required_variables']):
                    raise ValueError('reviewed short forecast context differs')
        return True


def run_worker(config_path,*,publish=False,guard=None,unit_reader=incumbent_units,
        transport=None,clock=lambda:datetime.now(timezone.utc),near_term_config_path=None):
    if type(publish) is not bool:raise ValueError('explicit publication mode required')
    if guard is None:
        from household_cycle_resources import publication_resource_preflight
        guard=publication_resource_preflight
    admission=Admission(config_path,guard=guard,unit_reader=unit_reader,clock=clock)
    settings=admission.settings
    if transport is None:
        transport=ProductionTransport(base=settings['openhab_base'],token_reader=lambda:admission.token,
            budget=ReadBudget(85,max_requests=96))
    if type(transport) is not ProductionTransport or transport.base!=settings['openhab_base']:
        raise ValueError('exact configured state-only transport required')
    archive=Archive.open_readonly(_path(settings['archive']));astro_source=None
    near_runtime=None;near_profile_status='NOT_REQUESTED'
    with SharedScoreLock(settings['shared_lock']):
        regional=_json(transport._request('/services/org.openhab.i18n/config',before_request=admission.verify))
        site=Site.from_openhab_config(regional)
        if site.__dict__!=admission.release['site']:raise ValueError('reviewed site differs from authoritative OpenHAB configuration')
        if not publish:
            ownership=transport.preflight(before_request=admission.verify)
            return dict(status='PREFLIGHT_PASSED',admission_sha256=admission.admission_sha256,
                ownership_sha256=ownership,production_writes=False,release_authorized=False,automatic_actuation=False)
        # Only this fixed local Item is optional. Admission/resource failures stay
        # fatal; unavailable network data or invalid metadata cannot invent sun.
        try:
            astro_raw=transport._request('/items/'+ASTRO_ITEM,before_request=admission.verify)
        except (URLError,TimeoutError,ConnectionError):
            astro_raw=None
        if astro_raw is not None:
            try:
                item=_json(astro_raw);available=clock()
                if (isinstance(item,dict) and item.get('name')==ASTRO_ITEM and item.get('type')=='String' and
                        isinstance(item.get('state'),str) and type(item.get('lastStateUpdate')) is int and
                        0<=item['lastStateUpdate']<=available.timestamp()*1000):
                    astro_source=dict(raw=item['state'],available_at=available)
            except (ValueError,TypeError,OverflowError):
                pass
        admission.verify()
        if near_term_config_path is not None:
            try:
                from .refresh_runtime import from_config
                near_runtime=from_config(near_term_config_path,archive=archive,site=site,clock=clock,guard=admission.verify)
                near_profile_status='CONFIGURED'
            except Exception:near_profile_status='UNAVAILABLE'
    optional={} if near_runtime is None else dict(near_term_preparer=near_runtime.prepare,refresh_retainer=near_runtime.retain)
    result=run_publication(archive=archive,site=site,evidence_directory=settings['evidence_directory'],
        shared_lock=settings['shared_lock'],code_revision=settings['code_revision'],transport=transport,
        authorize=admission.verify,guard=guard,clock=clock,astro_source=astro_source,admission_sha256=admission.admission_sha256,**optional)
    if near_term_config_path is not None:result['near_term_profile_status']=near_profile_status
    return result
