# Thermal airflow observation: windows and skylights

The operator chose **separate window and skylight states** on September 29.
The reported windows-open/skylights-closed configuration is diagnostic context
only, not a signed action label. Do not transcribe that chat report into the
append-only journal or infer an exact opening time from it.

The current `vent: open|closed` action, signed confirmation prompt, journal
check constraint and `vent_open` model forcing are all binary. A combined
`vent: open` record cannot distinguish windows-only from skylights-only or
both-open airflow. Do not issue a new `vent` prompt for a partly open house,
map one opening to both openings, or train a new model using such a mapping.
Existing historical `vent` records (if any) retain their original legacy
meaning and provenance; they are not retrospectively recoded as window or
skylight states.

The source-only implementation sequence is:

1. Add separate `window` and `skylight` `open|closed` action names and clear
   human-facing prompt labels. The source-only v2 policy now prepares and
   renders distinct state questions, refuses new v1-vent questions, and
   refuses v2 ingestion until storage is qualified. Existing v1 replay remains
   compatible. The journal/migration and genuine v2 confirmation tests remain
   open; do not send a v2 question yet.
2. Rehearse a constrained journal migration on an isolated full restore. The
   production `action_events` check constraint enumerates the old action
   names, and schema/ACL fingerprinting is strict. Preserve all old rows,
   foreign keys and correction semantics; prove rollback and backup readback.
3. Keep windows and skylights as separate as-of-origin observations. For a
   fresh model revision, qualify their physical forcing through measured
   changes and outcomes, including windows-only, skylights-only and both-open
   periods. Until that evidence exists, do not assume additive or equivalent
   airflow. Do not silently feed either new observation into legacy
   `vent_open` or graduate the current shadow model on it.
4. Only after the migrated journal, private prompt policy and authenticated
   Nostr route are qualified, perform an attended genuine question/reply and
   verify acknowledgement after durable storage. An operator's later signed
   confirmation, not this chat, supplies a training label.

This decision changes no live collector, control, model, or database schema.
