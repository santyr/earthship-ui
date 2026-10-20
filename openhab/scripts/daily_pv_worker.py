#!/usr/bin/env python3
"""Refresh a separate daily PV view; no weather writes, fitting or actuation."""
from datetime import datetime,time,timedelta,timezone
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo
import argparse,json,os,sys,time as timing
from household.codec import canonical,loads,identity
from household_native_training import directory,save
from household_observation import _private_file
from daily_pv_potential import project_days
from weather_learning.pv_calibration_policy import POLICY,POLICY_SHA256
from weather_learning.contracts import instant


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


def run(*,archive_path,state_path,output_path,libraries_path,calibration_path=None,clock=lambda:datetime.now(timezone.utc)):
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
    args=parser.parse_args(argv);os.umask(0o077)
    try:
        print(json.dumps(run(archive_path=args.archive,state_path=args.state,output_path=args.output,libraries_path=args.libraries,calibration_path=args.calibration)),flush=True);return 0
    except Exception as error:
        print(json.dumps(dict(status='daily_pv_withheld',reason=type(error).__name__,automatic_actuation=False)),flush=True);return 1

if __name__=='__main__':raise SystemExit(main())
