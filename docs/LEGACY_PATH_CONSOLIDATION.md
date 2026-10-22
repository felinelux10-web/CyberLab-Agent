# Legacy path consolidation: `lab_v4/` -> `lab_v4_dev/`

## Canonical runtime

The supported entry point is `run.py -> lab_v4_dev.core.agent.Agent`. New code and tests must use `lab_v4_dev/`; the legacy tree is not a second supported runtime.

## Completed repository changes

- Marked `lab_v4/` as deprecated in `lab_v4_dev/legacy_manifest.py`.
- Added `lab_v4/DEPRECATED.md` with the migration rule and an explicit no-delete-yet statement.
- Strengthened `tests/test_p8_legacy_manifest.py` to verify the deprecation metadata.
- Added `tests/test_legacy_runtime_boundary.py` to reject direct Python imports from `lab_v4` in `run.py` and `lab_v4_dev/`.
- Source scans found no direct `import lab_v4` or `from lab_v4...` statements in the 230 Python files under `lab_v4_dev/`, the `run.py` entry point, or the 79 Python test files. These scans do not cover dynamic imports, every non-Python path reference, external callers, or test execution.
- Fixed active CLI path leaks in `lab_v4_dev/cli/commands.py`: the `ls` shortcut and help use `lab_v4_dev`, search walks the active tree, and report/draft output goes to `lab_v4_dev/cache/`.
- Added `tests/test_legacy_cli_paths.py` to prevent those CLI path leaks from returning.

## Archive gate — not yet cleared

Do not move or delete `lab_v4/` until all of the following are complete:

1. Run the focused boundary, CLI-path, and manifest tests on the target Termux checkout.
2. Run the project's relevant targeted regression suites and record the exact results.
3. Audit non-Python references, scripts, configuration, persisted state paths, and any callers outside this repository.
4. Confirm the replacement mapping for every legacy manifest entry; do not assume same-name files are behaviorally equivalent.
5. Inspect whether legacy database files or snapshots exist in the user's working copy; preserve or migrate them only with an explicit data decision.
6. Archive the legacy tree in a separate reviewed change, preserving history and a documented recovery path.
7. Repeat the focused tests after archival and verify the canonical boot path.

The current change deliberately does not merge file contents, copy legacy implementations over maintained files, or remove `lab_v4/`. The audit must establish safe removal before that destructive step.

## Evidence-based audit snapshot (2026-10-21, initial baseline commit 43f8083)

The recursive Git tree for the baseline commit was complete (GitHub reported `truncated=false`) and contained 459 tracked file entries. Of these, 85 paths were under `lab_v4/`; 21 were non-Python files including `lab_v4/DEPRECATED.md`, legacy cache snapshots, `lab_v4/configs/MASTER_REF.yaml`, and `lab_v4/memory/schema.sql`. These files are not all disposable source: snapshot artifacts and the SQL schema require separate retention/migration decisions.

Spot checks of `run.py`, `lab_v4_dev/configs/MASTER_REF.yaml`, `lab_v4_dev/config/llm_provider.json`, `runtime_snapshot.json`, `docs/roadmap.md`, and `VOCAB_MAP.md` found no textual `lab_v4` reference in those files except canonical `lab_v4_dev` imports and state path in `run.py`. This was a limited sample, not an exhaustive scan of every non-Python file.

## Follow-up audit (branch `work/FRIENDLY-DIALOGUE-REPAIR-01`, commit 05f8bc0)

### Verified findings

- `run.py` imports `Agent` from `lab_v4_dev.core.agent`.
- `lab_v4_dev.core.agent.Agent.boot()` imports `Database` from `lab_v4_dev.memory.db` and `check_health` from `lab_v4_dev.monitor.health_check`.
- The active database implementation uses `lab_v4_dev/memory/agent.db` and loads `lab_v4_dev/memory/schema.sql` relative to its own module first. Its fallback is the active-tree schema path, not `lab_v4/memory/schema.sql`.
- The active health check uses `lab_v4_dev/memory/agent.db` and `lab_v4_dev/logs/agent.log`.
- The legacy `lab_v4/memory/db.py` and `lab_v4/monitor/health_check.py` still contain legacy paths and imports, but the inspected canonical boot path imports the active implementations instead. This is evidence about the inspected boot path, not proof that no external script imports legacy modules.
- The inspected legacy and active `memory/schema.sql` files have matching table definitions for `tasks`, `mutations`, `lessons`, `project_map`, and `sessions`. Schema equivalence does not establish that any existing legacy database is empty, unused, or safely disposable.
- The CLI boundary suite passed on Termux after fast-forwarding to commit `05f8bc028bf9bdd9f6bae238b58fd111438d17da`: 6 passed in 2.72s. `git diff --check` also passed in that run. The working tree still contained user-local `M execution_audit.json` and untracked `lab_v4_dev/archives/`; these were not changed.

### Remaining evidence gaps

- The presence, size, and contents of any local `lab_v4/memory/agent.db` or legacy cache/archive snapshots have not been inspected in Termux.
- External scripts, other local repositories, scheduled jobs, or user commands that may import `lab_v4` have not been ruled out.
- The full tracked-text scan, constructed-path scan, and dynamic-loading audit have not yet been demonstrated as exhaustive for the current branch.
- No migration or deletion of legacy database contents has been performed.

### Gate status

- **Passed:** direct-import boundary and focused CLI/manifest tests on Termux at `05f8bc0`.
- **Partially inspected:** active boot, active database/schema loading, active health-check paths, and the legacy counterparts.
- **Not established:** legacy persisted-data ownership/retention, all external callers, complete dynamic/path reference coverage, replacement equivalence for every manifest entry, and post-archive boot/regression tests.

**Decision: archive gate remains blocked.** Do not delete or move `lab_v4/` based on this snapshot. Next, inspect local legacy database/archive existence without modifying anything, and finish a current-branch tracked-path audit. Any archival proposal must list retained artifacts and map each manifest entry to a verified replacement before a separate change is prepared.
