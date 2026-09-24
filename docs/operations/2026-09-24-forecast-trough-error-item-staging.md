# Completed-trough error Item: file-provider staging

`Forecast_Trough_Error_7d` is an unlinked, observational Number Item written
by the completed-trough scorer during `forecast-intel.service`. Its live managed
definition is labeled `Trough Forecast Error (7d rolling)`, tagged
`forecast-intel`, and uses `%.0f` state formatting. The live state at the
September 24 preflight was `4.0`, numerically equal to the latest persisted
`4`; JDBC Item ID 584 had 67 rows. The disconnected OpenHAB 5.2.1 provider
test verified exact Item DTO parity, including state description.

The staged Git definition is
`openhab/file-config/items/forecast-trough-error.items`, SHA-256
`e7bf42f09f4fffaf7e4580d541203e0053c24fa2307c04ab9d881316a8ec2e49`.
An isolated OpenHAB/PostgreSQL rehearsal used one synthetic `4.0` state only
inside disposable containers and verified JDBC history, managed rollback,
forward transfer, hot reload and full restart. Both owned containers and the
temporary database were removed; production writes were zero. The existing
integrated-restore Number/UNDEF diagnostic uses REST state updates and does
not depend on this Item being managed. Its focused tests also pass.

The live adapter is read-only by default and has `RELEASE_READY=False`.
The file is **not installed**; the managed provider and forecast timer are
unchanged. Keep the gate off until after the natural 06:40 MDT forecast and
completed-trough assessment are verified. A later attended transfer must
repeat the live state/JDBC preflight, preserve a private rollback copy, and
exercise live rollback. A natural post-transfer scorer publication is a
separate gate; a held numeric state need not create a new change-only JDBC
row. This staging does not qualify a bandit reward or alter advisory thresholds.
