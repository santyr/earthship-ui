#!/usr/bin/env python3
"""Refresh a separate daily PV view; no weather writes, fitting or actuation."""
from datetime import datetime,time,timedelta,timezone
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo
import argparse,json,os,sys,stat,shutil,time as timing
from household.codec import canonical,loads,identity
from household_native_training import directory,save
from household_observation import _private_file
from daily_pv_potential import project_days
from weather_learning.pv_calibration_policy import POLICY,POLICY_SHA256
from weather_learning.contracts import instant


def component_capacity(state,receipt_bytes,*,guard):
    """Bound the existing daily namespace; reserve both originals before cache.

    Existing legacy receipts and geometry count too. Nothing is pruned or
    relabeled; a full archive withholds the new public cache.
    """
    remaining=receipt_bytes+8192;count=0;used=0;pending=[Path(state)]
    while pending:
        directory=pending.pop()
        if directory.resolve()!=directory:raise ValueError('original daily capacity path changed')
        with os.scandir(directory) as entries:
            for entry in entries:
                count+=1
                if count+2>10000:raise ValueError('original daily capacity exhausted')
                if count%100==0:guard()
                info=entry.stat(follow_symlinks=False)
                if info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)&0o077:
                    raise ValueError('private owned original daily capacity required')
                if stat.S_ISDIR(info.st_mode):
                    if directory!=Path(state) or entry.name!='geometry':raise ValueError('fixed original daily capacity directories required')
                    pending.append(Path(entry.path))
                elif stat.S_ISREG(info.st_mode) and info.st_nlink==1:used+=info.st_size
                else:raise ValueError('regular original daily capacity files required')
                if used+remaining>2*1024**3:raise ValueError('original daily capacity exhausted')
    if shutil.disk_usage(state).free<remaining+32*1024**2:raise ValueError('original daily capacity headroom exhausted')
    guard()


def day_geometry(root,day,*,site,native_runtime,libraries,guard,clock,capture=None):
    """Reuse exact deterministic geometry; never renew cached source clocks."""
    import astro_geometry as geometry
    from astro_geometry_series import build_series_request,split_series_request,build_series,replay_series
    from astro_geometry_worker import capture_batch
    capture=capture or capture_batch
    zone=ZoneInfo(site.timezone);local=datetime.fromisoformat(day)
    start=local.replace(tzinfo=zone).astimezone(timezone.utc)
    end=(local+timedelta(days=1)).replace(tzinfo=zone).astimezone(timezone.utc)
    points=[];at=start
    while at<end:at+=timedelta(minutes=5);points.append(at)
    key=identity(dict(day=day,site=site.__dict__,native_runtime=native_runtime))
    path=root/(key+'.geometry.json')
    guard()
    if path.exists():
        raw=_private_file(path,524288)[0];value=loads(raw)
        request=build_series_request(points,requested_at=value['request']['requested_at'],latitude=site.latitude,
            longitude=site.longitude,timezone_name=site.timezone)
        return replay_series(raw,request=request,expected_series_sha256=value['series_sha256'],expected_native_runtime=native_runtime)
    request=build_series_request(points,requested_at=clock(),latitude=site.latitude,longitude=site.longitude,timezone_name=site.timezone)
    caches=[]
    for chunk in split_series_request(request):
        guard();source=geometry.build_source(chunk,observed_at=clock(),native_runtime=native_runtime,source_status='ONLINE',
            latitude=site.latitude,longitude=site.longitude,timezone_name=site.timezone,altitude_m=None)
        from household_cycle_resources import publication_geometry_policy
        with publication_geometry_policy():
            caches.append(capture(chunk,source,library_paths=libraries,scratch=root,guard=guard,clock=clock))
    result=build_series(request,caches,expected_native_runtime=native_runtime)
    guard();save(path,result.to_dict());return result


def run(*,archive_path,state_path,output_path,libraries_path,calibration_path=None,component_profile_path=None,component_profile_sha256=None,component_publish=False,clock=lambda:datetime.now(timezone.utc)):
    if (component_profile_path is None)!=(component_profile_sha256 is None) or component_profile_path is not None and calibration_path is not None or type(component_publish) is not bool or component_publish and component_profile_path is None:
        raise ValueError('one explicit calibration mode and paired component profile/pin required')
    from weather_learning.archive import Archive
    from weather_learning.config import Site
    from weather_learning.openhab import oh_get
    from weather_learning.provider import load_publication_forecast,forecast_payloads,_presentation
    from weather_learning.worker import collector_lock
    from household_pv_model import prepare_system_source,system_configuration
    from household_solar_horizon import prepare_horizon_source,horizon_configuration
    from astro_geometry_worker import runtime_identity
    from household_native_geometry_prepare import _library_paths
    from household_cycle_pressure import PublicationHeadroom
    state=directory(state_path);root=Path(__file__).resolve().parents[2]
    started=timing.monotonic();pressure=PublicationHeadroom()
    def guard():
        pressure.check()
        if timing.monotonic()-started>550:raise TimeoutError('daily PV refresh deadline elapsed')
    component=None
    if component_profile_path is not None:
        from weather_learning.production_pv_runtime import ComponentOwner
        component=ComponentOwner(component_profile_path,expected_sha256=component_profile_sha256,clock=clock,guard=guard)
    with collector_lock(state/'worker.lock'):
        site=Site.from_openhab_config(oh_get('/services/org.openhab.i18n/config'))
        thing=oh_get('/things/astro:sun:local');addon=oh_get('/addons/binding-astro')
        coordinates=tuple(map(float,thing['configuration']['geolocation'].split(',')))
        if (thing['statusInfo']['status']!='ONLINE' or addon.get('installed') is not True or
            coordinates[:2]!=(site.latitude,site.longitude)):raise ValueError('native Astro/site unavailable')
        library_raw=_private_file(Path(libraries_path),8192)[0];libraries=_library_paths(library_raw)
        runtime=runtime_identity(libraries,binding_version=addon['version'],guard=guard)
        archive=Archive.open_readonly(str(archive_path));decision=clock()
        provider=load_publication_forecast(archive,decision_at=decision,site=site)
        if provider.to_dict()['status']!='AVAILABLE':raise ValueError('Google daily weather unavailable')
        _,_,detail=forecast_payloads(provider,now=decision)
        dates=[row['date'] for row in detail['days']]
        geometry_root=directory(state/'geometry');geometries=[];positions=[]
        for day in dates:
            value=day_geometry(geometry_root,day,site=site,native_runtime=runtime,libraries=libraries,guard=guard,clock=clock)
            geometries.append(value.sha256)
            positions.extend(row for cache in value.to_dict()['caches'] for row in cache['positions'])
            print(json.dumps(dict(status='daily_pv_geometry',day=day,cached_days=len(geometries))),flush=True)
        generated=clock()
        # Reselect after a cold geometry build, so expiry/near-term selection
        # reflects the actual projection time rather than job start.
        provider=load_publication_forecast(archive,decision_at=generated,site=site)
        if provider.to_dict()['status']!='AVAILABLE':raise ValueError('Google weather expired during geometry preparation')
        _,_,detail=forecast_payloads(provider,now=generated)
        if [r['date'] for r in detail['days']]!=dates:raise ValueError('local forecast dates changed during geometry build')
        system_raw=(root/'openhab/household-pv-system.json').read_bytes()
        horizon_raw=(root/'openhab/household-solar-horizon.json').read_bytes()
        system_source=prepare_system_source(system_raw,available_at=generated)
        horizon_source=prepare_horizon_source(horizon_raw,available_at=generated)
        system,reason=system_configuration(system_source,generated)
        horizon,horizon_reason=horizon_configuration(horizon_source,origin=generated,site=dict(latitude=site.latitude,longitude=site.longitude),timezone_name=site.timezone)
        if reason is not None or horizon_reason is not None:raise ValueError('array/terrain configuration unavailable')
        # A midnight endpoint belongs to the preceding energy day. The
        # provider's complete hours, rather than a ten-day visual slice,
        # include that last necessary interval.
        hours=[dict(at=h['at'],radiationWm2=h['radiation_wm2'],tempF=h['temp_f'],windMph=h['wind_mph']) for h in _presentation(provider.to_dict())[0]['hours']]
        calibration=None;calibration_reason=None
        if component is not None:
            from weather_learning.native_solar_forecast import load_component_forecast
            import math
            last=datetime.combine(datetime.fromisoformat(dates[-1]).date()+timedelta(days=1),datetime.min.time(),ZoneInfo(site.timezone)).astimezone(timezone.utc)
            native=load_component_forecast(archive,origin=generated,available_by=generated,horizon_hours=math.ceil((last-generated).total_seconds()/3600),site=site)
            if native is None:raise ValueError('native component forecast unavailable for requested daily horizon')
            days,windows=component.project_days(dates=dates,forecast=native,positions=positions)
            view=component.daily_view(days=days,forecast=native,geometry_sha256=identity(geometries))
            if component.configurations['system_path'][1]!=system_raw or component.configurations['horizon_path'][1]!=horizon_raw:
                raise ValueError('same declared daily/household component geometry required')
            guard();component.verify()
            if (_private_file(Path(libraries_path),8192)[0]!=library_raw or runtime_identity(libraries,binding_version=addon['version'],guard=guard)!=runtime or
                oh_get('/things/astro:sun:local')['statusInfo']['status']!='ONLINE' or oh_get('/addons/binding-astro')['version']!=addon['version']):
                raise ValueError('native Astro/geometry changed during component projection')
            receipt=dict(schema='earthship-daily-pv-potential-receipt/v2',issued=False,view=view,provider=provider.to_dict(),native_forecast=native,
                geometry_series_sha256s=geometries,geometry_positions=positions,system_source=system_source,horizon_source=horizon_source,
                calibration_original=component.model.to_dict(),calibration_policy=__import__('weather_learning.production_pv',fromlist=['_policy'])._policy(),component_windows=windows,owner_profile_sha256=sha256(component.raw).hexdigest(),
                owner_runtime_manifest=__import__('weather_learning.production_pv_runtime',fromlist=['runtime_manifest']).runtime_manifest(),automatic_actuation=False)
            receipt['receipt_sha256']=identity(receipt)
            if len(canonical(receipt))>8*1024**2:raise ValueError('bounded original component daily receipt required')
            component_capacity(state,len(canonical(receipt)),guard=guard)
            save(state/(receipt['receipt_sha256']+'.receipt.json'),receipt)
            component.verify();guard()
            result=dict(status='component_pv_prepared',receipt_sha256=receipt['receipt_sha256'],available_days=sum(d['status']=='available' for d in days),days=len(days),
                calibration_sha256=component.body['calibration_sha256'],production_states_written=False,automatic_actuation=False)
            if not component_publish:return dict(result,view=view)
            output=Path(output_path)
            if not output.is_absolute() or output.resolve()!=output:raise ValueError('resolved explicit component publication path required')
            directory(output.parent);component.verify();guard();published=False
            try:
                save(output,view)
                if _private_file(output,32768)[0]!=canonical(view):raise ValueError('original component view readback differs')
                published=True;completed=clock()
                if completed>generated+timedelta(seconds=85):raise ValueError('component daily publication lifetime exceeded')
                emission=dict(schema='earthship-confirmed-component-daily-emission/v1',receipt_sha256=receipt['receipt_sha256'],view_bytes_sha256=sha256(canonical(view)).hexdigest(),
                    published_at=completed.isoformat(),calibration_sha256=component.body['calibration_sha256'],issued=True,
                    score_days=[d['date'] for d in days if d['status']=='available' and datetime.fromisoformat(d['fromAt'])>=completed],
                    source_population='actual_published_daily_totals_and_original_constituent_power',score_basis='constituent_five_minute_power_of_published_daily_totals',score_from_at=completed.isoformat(),automatic_actuation=False)
                emission['emission_sha256']=identity(emission)
                save(state/(emission['emission_sha256']+'.emission.json'),emission)
            except Exception as error:
                return dict(result,status='PUBLISHED' if published else 'PUBLICATION_UNCERTAIN',production_states_written=True if published else None,
                    production_retention_status='FAILED_AFTER_PUBLICATION' if published else 'UNKNOWN_PARTIAL',reason=type(error).__name__)
            return dict(result,status='component_daily_pv_published',production_states_written=True,production_retention_status='CONFIRMED',
                emission_sha256=emission['emission_sha256'],seconds=round(timing.monotonic()-started,3))
        if calibration_path is not None:
            from weather_learning.pv_calibration_source import load_calibration
            try:calibration=load_calibration(calibration_path,origin=generated,system_raw=system_raw,horizon_raw=horizon_raw)
            except (ValueError,FileNotFoundError) as error:calibration_reason=type(error).__name__
        projection_steps=[]
        days=project_days(dates=dates,hours=hours,positions=positions,array=system['array'],horizon_profile=horizon['profile'],timezone_name=site.timezone,issued_at=generated,calibration=None if calibration is None else calibration['model'],steps_out=projection_steps)
        view=dict(schema='earthship-daily-pv-potential/v1',provider='weathernext3',generatedAt=generated.isoformat(),
            validUntil=(generated+timedelta(minutes=90)).isoformat(),timezone=site.timezone,
            weatherSha256=provider.to_dict()['provider_snapshot_sha256'],geometrySha256=identity(geometries),
            systemSha256=sha256(system_raw).hexdigest(),horizonSha256=sha256(horizon_raw).hexdigest(),
            confidence='provisional_uncalibrated',automatic_actuation=False,physical_calibration_qualified=False,days=days)
        if calibration is not None:
            model=calibration['model'];report=calibration['report']
            view.update(schema='earthship-daily-pv-potential/v3',confidence='provisional_empirical_supported_horizon',calibration=dict(
                modelSha256=model['model_sha256'],policySha256=POLICY_SHA256,trainingThrough=model['cutoff'],assessedThrough=report['holdout_end'],
                applyThroughAt=(generated+timedelta(hours=POLICY['maximum_lead_hours'])).isoformat(),independentTargetDays=report['independent_target_days'],
                baselineMaeW=report['baseline_mae_w'],candidateMaeW=report['candidate_mae_w'],
                qualification='retrospective_development_assessment_not_prospective_or_metrology'))
        guard()
        if _private_file(Path(libraries_path),8192)[0]!=library_raw or runtime_identity(libraries,binding_version=addon['version'],guard=guard)!=runtime:
            raise ValueError('native runtime changed during daily PV projection')
        if oh_get('/things/astro:sun:local')['statusInfo']['status']!='ONLINE' or oh_get('/addons/binding-astro')['version']!=addon['version']:
            raise ValueError('native Astro metadata changed during daily PV projection')
        output=Path(output_path);directory(output.parent)
        receipt=dict(schema='earthship-daily-pv-potential-receipt/v1',view=view,provider=provider.to_dict(),geometry_series_sha256s=geometries,
            system_source=system_source,horizon_source=horizon_source,calibration_source=calibration,calibration_reason=calibration_reason,calibration_policy=POLICY,projection_steps=projection_steps,model_assumptions=dict(__import__('household_pv_model').ASSUMPTIONS))
        receipt['runtime_manifest']={name:sha256((root/name).read_bytes()).hexdigest() for name in ('openhab/scripts/daily_pv_worker.py','openhab/scripts/daily_pv_potential.py','openhab/scripts/household_pv_model.py','openhab/scripts/household_solar_horizon.py','openhab/scripts/weather_learning/pv_calibration_source.py','openhab/scripts/weather_learning/pv_directional_calibration.py','openhab/scripts/weather_learning/pv_calibration_policy.py','openhab/scripts/weather_learning/pv_calibration.py')}
        receipt['receipt_sha256']=identity(receipt);save(state/(receipt['receipt_sha256']+'.receipt.json'),receipt)
        if (root/'openhab/household-pv-system.json').read_bytes()!=system_raw or (root/'openhab/household-solar-horizon.json').read_bytes()!=horizon_raw:
            raise ValueError('array/terrain bytes changed during projection')
        if calibration is not None and sha256(_private_file(Path(calibration_path),262144)[0]).hexdigest()!=calibration['original_file_sha256']:raise ValueError('selected PV calibration source changed')
        guard();save(output,view)
        return dict(status='daily_pv_published',available_days=sum(d['status']=='available' for d in days),days=len(days),
            seconds=round(timing.monotonic()-started,3),automatic_actuation=False)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',type=Path,required=True);parser.add_argument('--state',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--libraries',type=Path,required=True)
    parser.add_argument('--calibration',type=Path)
    parser.add_argument('--component-profile',type=Path);parser.add_argument('--component-profile-sha256')
    parser.add_argument('--component-publish',action='store_true')
    args=parser.parse_args(argv);os.umask(0o077)
    try:
        result=run(archive_path=args.archive,state_path=args.state,output_path=args.output,libraries_path=args.libraries,calibration_path=args.calibration,
            component_profile_path=args.component_profile,component_profile_sha256=args.component_profile_sha256,component_publish=args.component_publish)
        print(json.dumps(result),flush=True);return 1 if result['status'] in ('PUBLISHED','PUBLICATION_UNCERTAIN') else 0
    except Exception as error:
        print(json.dumps(dict(status='daily_pv_withheld',reason=type(error).__name__,automatic_actuation=False)),flush=True);return 1

if __name__=='__main__':raise SystemExit(main())
