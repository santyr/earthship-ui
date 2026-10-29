# Active receiver compatibility repair, October25,2026

The OS upgrade replaced the locally built rtl_43325.02-17-g8e813dda seen in the October22 service journal with packaged25.12. The package database alone incorrectly suggested the former executable was23.11. The SDR library also changed2.0.1->2.0.2.

An indoor WH32B235 update gap of180seconds exceeded the unchanged120-second freshness policy. Receiver and OpenHAB timestamps agreed; the UI correctly withheld expired data. A185-second signal capture decoded only one indoor burst. Older/default demodulation settings did not recover missing packets from that recording, so blindly changing defaults was rejected.

The same verified upstream8e813 source was built with threads enabled against each SDR library. Both candidates and installed25.12 reproduced identical CRC-valid recorded packets. During the live comparison, the25.02 decoder with the current2.0.2 library received four indoor updates in four minutes, with no expired samples across any temperature stream. This points to the upgraded decoder/runtime path; a short comparison does not prove long-term RF reliability or identify one specific upstream code change.

## Active dependency

Release: /home/sat/system-repair-20261024/rtl-weather-dropouts/release-25.02-8e813-currentlib-3502425d8215-v2

BinarySHA256: 3502425d82158e42efe4a7a77a285d12ad5af80eea1dc0e9954e2f2b031a4184

Root-owned drop-in: /etc/systemd/system/rtl_weather.service.d/92-post-upgrade-decoder-compat.conf

Drop-inSHA256: 30530c257e6598c3f1a80318a616852fc0dd711bc9b63d6108d6d230facd4bdb

The drop-in prepends the immutable release bin directory to rtl_weather.service PATH. The receiver Python script, current OS library, installed OS decoder, frequency914980000Hz, sample rate250000, automatic gain, tested level=-18, all sensor identities and120-second validity remain unchanged. The release is an ACTIVE SYSTEM DEPENDENCY, not disposable diagnostic output; retain it while the drop-in refers to it.

## Evidence and rollback

Canonical deployment/actual-process proof: /home/sat/earthship-ui/artifacts/post-upgrade-repairs-20261024.local/rtl-decoder-compatibility-deployment.json

Ten-minute receiver/OpenHAB observation: /home/sat/earthship-ui/artifacts/post-upgrade-repairs-20261024.local/radio-after-compat-10min.json (read its final status).

Actual browser indoor render proof: /home/sat/earthship-ui/artifacts/post-upgrade-repairs-20261024.local/final-readonly-ui/after-compat-indoor-result.json

Full normalized packet parity: /home/sat/earthship-ui/artifacts/post-upgrade-repairs-20261024.local/compat-normalized-payload-parity.json

To roll back, first verify the exact owned drop-in SHA above, remove only that file, then run sudo systemctl daemon-reload and sudo systemctl restart rtl_weather.service. This selects the installed OS decoder; it does not alter packages or remove the compatibility release. Before retiring the compatibility path after a later upgrade, repeat recorded-packet parity and live reception/display checks for all four streams.

The earlier unthreaded driver-comparison-25.02 build was an offline-only diagnostic and cannot receive live SDR data. Its failed60-second trial automatically restored the normal receiver. Use only the active thread-enabled release named above. All temporary diagnostic91drop-ins were removed;92is the intended persistent repair.
