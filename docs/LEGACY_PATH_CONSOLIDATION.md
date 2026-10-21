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
