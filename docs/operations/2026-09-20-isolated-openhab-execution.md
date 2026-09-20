# Isolated OpenHAB execution qualification

Operator approved proceeding with isolated execution and requested cleanup.
Production OpenHAB remained active with MainPID4060018 throughout this test.

## Execution denial resolved without host-policy changes

Kernel audit records identify the earlier failure: Snap Docker's
`snap.docker.dockerd` AppArmor transition to `docker-default` was denied with
`info="no new privs"`. Even Ubuntu `/bin/true` failed with the extra
`--security-opt no-new-privileges` flag. Omitting that optional flag allowed
the official image's Java21 runtime to execute as UID/GID9001 with all Linux
capabilities dropped. No AppArmor/seccomp profile or host security setting was
disabled or edited; no privileged mode was used.

## Verified isolation and boot

Pinned image: `openhab/openhab@sha256:bfd4a60e90da18cf917a9004bbc22354fc818825f3c6f0351e471a2e938d6c3c`.
The test used `--network none --read-only --user 9001:9001 --cap-drop ALL`,
default `docker-default` AppArmor/seccomp, one CPU,1536MiB memory and256PIDs.
No ports, host mounts, devices or Docker socket were attached. Writable paths
were disposable tmpfs only: `/tmp`64MiB, conf64MiB, userdata512MiB, addons32MiB,
all owned by9001 with nosuid/nodev. Image-declared volume paths were covered by
tmpfs rather than leaving anonymous disk volumes.

The non-root bootstrap copied image `dist/conf` and `dist/userdata` into their
empty tmpfs destinations and ran `/openhab/start.sh server`, bypassing the
root-only entrypoint's chown/user-management work. Java heap was512MiB, timezone
America/Denver and user.home pointed at the disposable userdata directory.
Internal loopback `/rest/` returned200 and runtimeInfo reported5.2.1 Release Build.
Logs included hostname-resolution failures in this network-none environment;
this does not establish every optional service healthy. Admin registry endpoints
required authentication. No production credentials were copied or used in the
test instance; read-only Item verification did not require an admin account.

## Narrow file recovery verified

Git-owned `energy-analytics.items` and `bitcoin-change.items` were copied into
the isolated provider, along with the live Bitcoin parent Group declaration.
All three Items registered as file-owned with stateNULL. The Bitcoin label was
`BTC 24h Change`, its pattern `%.2f %%`, and its group membership unchanged.
Installed Item-file hashes exactly matched their Git source hashes.
No production history, telemetry values, rules, Things, credentials or learned
models were copied. This proves a clean runtime and these Item definitions can
load, NOT full backup restoration, history recovery, protected-rule restart
safety, external-service integration or complete file-first migration.

## Cleanup

The temporary Group staging file/directory was removed immediately after copying.
The owned container was stopped and automatically removed; its tmpfs data vanished.
A label-filtered container check found no remaining test instance. The approved
downloaded image is retained for subsequent restoration work. No new persistent
volume, host configuration copy, test account or daemon is retained.
