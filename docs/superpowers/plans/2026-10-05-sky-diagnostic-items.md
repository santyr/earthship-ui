# Sky diagnostic Item migration plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

Migrate only `SkyCondition_Diagnostic` (String, JDBC541) and
`SkyCondition_LastEval` (DateTime, JDBC540), preserving labels, metadata,
`gWeatherHealth` membership and the existing file rule as sole publisher.
Both are unlinked. `SkyCondition`, health status and outdoor age remain managed.
Existing age Items/metadata/links remain file-owned. No source state, command,
rule-execution or service RPC is authorized by this plan.

- [x] Trace the actual rule and prove that absent diagnostics cannot change its
  primary condition/icon decisions. Add descriptor/metadata/operation guards
  and canonical definitions, with failing tests before implementation.
- [x] Rehearse managed/file/cold-restart/managed-rollback/final-file Item phases
  in owned networkless containers, preserving six history prefixes and current
  age providers. Use existing Group/JDBC fixtures and inert age channels.
- [x] Keep the Group candidate compatible with its resulting four file members;
  qualify that exact mix in isolation before any production Group cold transfer.
- [x] Review, prepare current private recovery, perform the attended two-Item hot
  handoff, verify natural publisher/JDBC rows and preserved protected registry,
  refresh restart evidence, commit and fast-forward local main. Production cold
  restart/Group transfer still require host authentication. Do not push.
