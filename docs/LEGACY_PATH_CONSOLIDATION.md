# Legacy path consolidation: `lab_v4/` -> `lab_v4_dev/`

## Canonical runtime

The supported entry point is `run.py -> lab_v4_dev.core.agent.Agent`. New code and tests must use `lab_v4_dev/`; the legacy tree is not a second supported runtime.

## Completed repository changes

- Marked `lab_v4/` as deprecated in `lab_v4_dev/legacy_manifest.py`.
- Added `lab_v4/DEPRECATED.md` with the migration rule and an explicit no-delete-yet statement.
- Strengthened `tests/test_p8_legacy_manifest.py` to verify the deprecation metadata.
- Added `tests/test_legacy_runtime_boundary.py` to reject direct Python imports from `lab_v4` in `run.py` and `lab_v4_dev/`.
- Source scans found no direct `import lab_v4` or `from lab_v4...` statements in the 230 Python files under `lab_v4_dev/`, the `run.py` entry point, or the 79 Python test files. These scans do not cover dynamic imports, every non-Python path reference, external callers, or test execution.

## Archive gate — not yet cleared

Do not move or delete `lab_v4/` until all of the following are complete:

1. Run the focused boundary and manifest tests on the target Termux checkout.
2. Run the project's relevant targeted regression suites and record the exact results.
3. Audit non-Python references, scripts, configuration, persisted state paths, and any callers outside this repository.
4. Confirm the replacement mapping for every legacy manifest entry; do not assume same-name files are behaviorally equivalent.
5. Archive the legacy tree in a separate reviewed change, preserving history and a documented recovery path.
6. Repeat the focused tests after archival and verify the canonical boot path.

The current change deliberately does not merge file contents, copy legacy implementations over maintained files, or remove `lab_v4/`. The audit must establish safe removal before that destructive step.

## Evidence-based audit snapshot (2026-10-21, commit 43f8083)

The recursive Git tree for this commit is complete (GitHub reported `truncated=false`) and contains 459 tracked file entries. Of these, 85 paths are under `lab_v4/`; 21 are non-Python files, including `lab_v4/DEPRECATED.md`, legacy cache snapshots, `lab_v4/configs/MASTER_REF.yaml`, and `lab_v4/memory/schema.sql`. These files are not all disposable source: snapshot artifacts and the SQL schema require separate retention/migration decisions.

Spot checks of `run.py`, `lab_v4_dev/configs/MASTER_REF.yaml`, `lab_v4_dev/config/llm_provider.json`, `runtime_snapshot.json`, `docs/roadmap.md`, and `VOCAB_MAP.md` found no textual `lab_v4` reference in those files except the canonical `lab_v4_dev` imports and state path in `run.py`. This is a limited sample, not an exhaustive scan of every non-Python file. The active entry point imports `lab_v4_dev.core.agent.Agent` and writes its state under `lab_v4_dev/cache/state.json`.

### Gate status

- **Passed:** AST guard for direct imports from `lab_v4` in `run.py` and Python files under `lab_v4_dev/`; its targeted tests passed on Termux at commit `43f8083`.
- **Partially inspected:** repository-tracked configuration/documentation references; the spot checks above found no additional legacy references.
- **Not established:** exhaustive dynamic-import/string-path scan across all tracked files; whether external scripts or consumers import `lab_v4`; equivalence/migration of every manifest entry; preservation requirements for legacy snapshots and `schema.sql`; post-archive boot and regression tests.

**Decision: archive gate remains blocked.** Do not delete or move `lab_v4/` based on this snapshot. Next audit must scan all tracked text files for literal and constructed references, inspect runtime path construction and dynamic imports, identify whether any persisted data/schema is still read, and establish external-caller ownership. Any archival proposal should list retained artifacts and map each manifest entry to a verified replacement before a separate change is prepared.
