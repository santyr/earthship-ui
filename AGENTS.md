# Project workflow

Use OpenSpec for planning and tracking changes in this project. The active repair
change is `openspec/changes/complete-post-upgrade-repairs/`.

Do not invoke Superpowers skills or use its workflow. Existing `.superpowers/`
files are historical evidence, not current workflow instructions. This reflects
the user's explicit instruction of 2026-10-28.

The project has dirty live checkouts and separate runtime worktrees. Preserve
unrelated changes, private configuration, retained evidence, and immutable release
artifacts. Read `openspec/config.yaml` and the active change before editing.

Record implementation, test results, deployment, and live observations separately.
Do not claim completion from source tests alone. Normal functional checks and
existing resource and equipment-control limits still apply; do not introduce
security-scan or hardening work into these repairs.
