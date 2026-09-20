# Pump operating-window check — September 20

Historical pre-change observation. The operator subsequently approved the
[timer-driven daylight schedule](2026-09-20-greywater-daylight-activation.md),
which supersedes the fixed operating window described below.

Read-only check at approximately07:20MDT. No rule, trigger, threshold, command,
timer or persistence setting was changed.

The enabled live `hex_southoutlet_cycle` is IDLE/NONE and retains exact repaired
script SHA256f045608ba43d08f6bcaa53d70d5c1851df0f3c0410ef480ac6cef4ca98b969f6.
Both pumps are OFF. Its outer `core.TimeOfDayCondition` permits execution only
08:00–20:00. Triggers remain voltage/SoC changes and manual request commands;
there is no cron or sunrise trigger.

At the check, voltage was53.07V, SoC85%, BMS communicationsOK and sun elevation
5.377918degrees. The event log shows voltage changing at07:20:12and07:20:17,
so unchanged input values are not the explanation for the old display. The outer
time condition prevents execution before08:00, explaining why AutoStatus still
reports yesterday's `after_dark,sunElev=-11.1,soc=96.0`.

Do not treat this retained status as a current solar measurement or evidence of
a broken rule. Actual natural cycle proof remains outstanding and requires the
permitted operating window plus all internal safety and SoC gates. SoC85% is
also below both automatic eligibility thresholds (90/98); the24-hour fallback
mode does not bypass that eligibility check. Preserve those policies.

Observe a naturally eligible ON-to-OFF cycle and all intervening interruption
events. Do not force a run or infer a successful full cycle from LastCycle alone.
