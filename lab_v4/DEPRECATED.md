# Deprecated: `lab_v4/`

This directory is an inactive legacy compatibility path. The canonical runtime is
`run.py -> lab_v4_dev.core.agent.Agent`.

- Do not add new imports from `lab_v4`.
- Use the corresponding maintained implementation under `lab_v4_dev/`.
- Keep this directory until the external-dependency audit, archival, and stabilization steps are complete.
- Do not copy legacy files over `lab_v4_dev`.

The directory is a candidate for archival; it is not being deleted in this change.
