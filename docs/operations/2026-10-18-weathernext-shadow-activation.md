**Later update:** [Comparison publication and first candidate](2026-10-18-weathernext-comparison-activation.md) supersede this initial local-only publication setting. The initial deployment evidence below remains historical.

# WeatherNext private shadow activation

Observed 2026-10-18. Initial deployment source was reviewed commit `f0680630bbdab3beaf5d6270c1dbb87c7e7143ee` on PR #35; the current private backend source is tested commit `f5775f8132a35b177ba503d6fc605e1b9d94df47`, as recorded in the rain-candidate upgrade below. The [API compatibility correction](2026-10-18-weathernext-api-compatibility.md) fixed the missing read-only backing-storage OAuth scope and retained source initialization clock separately from forecast target time.

## Installed state

The isolated source is `/home/sat/.local/share/earthship-weather/releases/f0680630bbdab3beaf5d6270c1dbb87c7e7143ee`. All 1,102 packaged source files were checked against the recorded SHA256 manifest and made read-only. The existing tested isolated Python environment is reused; its path and the exact source revision are in private `/home/sat/.config/earthship-weather/runtime.env`. Credentials remain at their existing private location and were not copied into the release.

The source-bound archive is `/home/sat/.local/state/earthship-weather/archive`; original issue/model state is `/home/sat/.local/state/earthship-weather/shadow`. Directories are mode 700. The initial original snapshot and the original f068063 shadow issue were transferred through their typed immutable stores with their original clocks and identities preserved. Existing qualified v2 sensor policy and restricted temperature-reader configuration are reused; no database grants were changed.

Three new user timers are enabled and active:

| Timer | Schedule | Effect |
|---|---|---|
| `weathernext-ingest.timer` | Hourly at :35, up to 120 seconds jitter | Retains a bounded 360-hour Google snapshot |
| `local-forecast-shadow.timer` | Hourly at :40, up to 60 seconds jitter | Retains the original private shadow decision; no Item publication |
| `local-forecast-train.timer` | Sunday 06:50, up to 120 seconds jitter | Fits/installs only a separate shadow candidate when eligible Google/local pairs exist |

Installed unit bytes match the reviewed templates. The sole service override, `local-forecast-shadow.service.d/local-recording.conf`, removes `--publish` from the shadow worker. Its SHA256 is `0f36168ea33be548eef7bef6d2f1798e2e7af3246c9b17b71ef2779afaec83a3`. The optional incumbent comparison remains an isolated as-observed control, excluded from fitting and to be removed at cutover. The three shadow OpenHAB Items and comparison UI are not activated by this deployment. All existing production forecast services and provider selection remain unchanged.

## Actual installed-run verification

- Collector service completed successfully and added snapshot `c00ebfd541921f7fc4576b29bcb962fc6c55772c55361719d37afe722cd2c7ca`, completed **18:28:00.580681Z**. It retained **3,600 points**, used **8.213 seconds**, **1,255,580 bytes / 7 requests**, and **72,652 KiB peak RSS**, with live noncommercial verification.
- Shadow service completed successfully, retained generation `dd9d7d3d84ebe876909685b52cb45826d2d4940bf3776e49d098a99320977800` and reported `READY`, `published=false`, `automatic_actuation=false`. Private state then held two original issues for October 18.
- Separate candidate training completed successfully with `NO_ELIGIBLE_PAIRS`, `pairs=0`, `applied=false`. No forecast target had elapsed yet; no candidate pointer was created. This is the expected untrained state, not proof of a fitted model or forecast skill.
- The real 337-target shadow payload also passed the actual frontend parser. The inactive six-variable provider returned `AVAILABLE` for 337 hourly targets / 15 local dates, with `release_authorized=false` and `automatic_actuation=false`.
- Independent review found no Critical, Important or Minor issue in the live-API correction; the reviewer reran all 123 pinned tests and checked source-clock variants through downstream features. Exact-increment default Gitleaks scan and GitGuardian both pass.

The first natural collector trigger fired at **12:35:11 MDT (18:35:11Z)** and added snapshot `580fa8cb9f5dd0d5fc5328a4745abe2b303014992bfde01b993fcdddaf35aad2`, completed **18:35:19.439478Z**. It retained **3,600 points** in **8.008 seconds**, transferred **1,255,580 bytes / 7 requests**, and peaked at **73,144 KiB RSS**. The service succeeded and the active timer advanced to its next trigger; the live archive held three immutable snapshots. The first natural shadow trigger also ran at **12:40:24 MDT (18:40:24Z)** and retained `READY` generation `980bb52b9461e7f0f42e81f9e856ba47c05ba3d5b9b3bb3b1a33e11d57c25fe3`, with `published=false` and `automatic_actuation=false`. Natural weekly training remains pending its next Sunday trigger; its manual installed run passes. Local source/install receipts and live timer observations are retained privately in the execution evidence directory.

## Remaining qualification

This is the beginning of prospective acquisition, not production cutover. The plan's acquisition interval, qualified training/holdout data, local-model shadow duration, solar/rain/PV/thermal qualification, finished production integration, shadow Item/UI rollout, complete Open-Meteo removal and post-cutover outcomes remain incomplete. No weather-dependent legacy fitted state is imported into Google/local training. No model or forecast grants actuator authority, and no new notification path is enabled.

To stop these additions while retaining their original evidence, disable only the three new timers and stop any currently active matching services. This does not change the incumbent production units. Backup/recovery finishing work remains deferred.

## Rain-candidate source upgrade (18:47Z)

The active private code root is now `/home/sat/.local/share/earthship-weather/releases/f5775f8132a35b177ba503d6fc605e1b9d94df47`. Its 1,102 packaged files match their Git blob identities and are read-only. Existing credential/state paths, all unit definitions and active timers, the publication-free override and resource bounds are unchanged. The [rain-candidate report](2026-10-18-weathernext-rain-candidates.md) records the successful installed 4,320-point capture and matching shadow issue. The older release and its original observations remain preserved; qualification and full production cutover are still incomplete.
