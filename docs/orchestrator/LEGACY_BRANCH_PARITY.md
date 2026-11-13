# Legacy Orchestrator Branch Parity Manifest

- Baseline commit: `6f0f35f9a5907fba707128913c2a06513f358e2f`
- Baseline blob: `28bafb091cd27b682ef83ef77c27a108e864eb02`
- Current branch: `work/FRIENDLY-DIALOGUE-REPAIR-01`
- Legacy route branch keys extracted from the baseline: **69**
- Current explicit handler registry keys: **69**
- Missing legacy keys: **0**
- Unexpected current keys: **0**

## Coverage result

**Exact key parity: 69/69.**

The baseline extraction includes every top-level `if/elif intent` branch in the original `lab_v4_dev/core/orchestrator.py`, plus the literal `show_last_result` branch. Duplicate occurrences such as the two `FILE_IMPACT` modes are represented by one key and separately documented below.

## Branch-to-handler mapping

| Legacy intent value | Current handler |
|---|---|
| `analyze_code` | `code_authoring.handle_analyze_code` |
| `analyze_release` | `releases.handle_analyze_release` |
| `audit_log` | `system_inspection.handle_audit_log` |
| `capabilities` | `knowledge.handle_capabilities` |
| `clean` | `maintenance.handle_clean` |
| `clean_device` | `maintenance.handle_clean_device` |
| `cleanup_code` | `planning.handle_cleanup_code` |
| `compare_files` | `project_analysis.handle_compare_files` |
| `compare_versions` | `releases.handle_compare_versions` |
| `context_report` | `reports.handle_context_report` |
| `criticality_query` | `project_analysis.handle_criticality_query` |
| `current_version` | `releases.handle_current_version` |
| `cyber_explain` | `knowledge.handle_cyber_explain` |
| `delete_file` | `maintenance.handle_delete_file` |
| `dependencies` | `project_analysis.handle_dependencies` |
| `dependency_map` | `project_analysis.handle_dependency_map` |
| `dependents_query` | `project_analysis.handle_dependents_query` |
| `dry_run` | `execution.handle_dry_run` |
| `entry_point_query` | `project_analysis.handle_entry_point_query` |
| `error_report` | `execution.handle_error_report` |
| `file_impact` | `project_analysis.handle_file_impact` |
| `full_diagnose` | `system_inspection.handle_diagnostics` |
| `generate_code` | `code_authoring.handle_generate_code` |
| `health` | `system_inspection.handle_health` |
| `history` | `reports.handle_history` |
| `impact_analysis` | `project_analysis.handle_impact_analysis` |
| `impact_chain_query` | `project_analysis.handle_impact_chain_query` |
| `last_project` | `releases.handle_last_project` |
| `list_scripts` | `execution.handle_list_scripts` |
| `memory_status` | `system_inspection.handle_memory_status` |
| `modify_code` | `code_authoring.handle_modify_code` |
| `next_task` | `reports.handle_work_tracking` |
| `pending_fixes` | `repair.handle_pending_fixes` |
| `plan_change` | `planning.handle_plan_change` |
| `progress_report` | `reports.handle_project_reports` |
| `project_index` | `project_inspection.handle_project_index` |
| `project_report` | `reports.handle_project_reports` |
| `project_scan` | `project_inspection.handle_project_scan` |
| `project_timeline` | `releases.handle_project_timeline` |
| `read_external_project` | `project_inspection.handle_read_external_project` |
| `read_file` | `project_inspection.handle_read_file` |
| `release_index` | `releases.handle_release_index` |
| `remaining_tasks` | `reports.handle_work_tracking` |
| `remaining_work` | `reports.handle_project_reports` |
| `repair_analyze` | `repair.handle_repair_analyze` |
| `repair_approve` | `repair.handle_repair_approve` |
| `repair_reject` | `repair.handle_repair_reject` |
| `report` | `reports.handle_session_report` |
| `resume` | `sessions.handle_session_restore` |
| `return_base_project` | `releases.handle_switch_project` |
| `run_history` | `execution.handle_run_history` |
| `run_script` | `execution.handle_run_script` |
| `save_kb` | `knowledge.handle_save_kb` |
| `search` | `project_inspection.handle_search` |
| `search_code` | `project_inspection.handle_search_code` |
| `security_log` | `system_inspection.handle_security_log` |
| `self_diagnose` | `system_inspection.handle_diagnostics` |
| `session_report` | `reports.handle_session_report` |
| `session_restore` | `sessions.handle_session_restore` |
| `session_save` | `sessions.handle_session_save` |
| `show_changes` | `reports.handle_show_changes` |
| `show_last_result` | `reports.handle_show_last_result` |
| `skip_kb` | `knowledge.handle_skip_kb` |
| `space` | `system_inspection.handle_space` |
| `status` | `system_inspection.handle_status` |
| `switch_project` | `releases.handle_switch_project` |
| `system_status` | `system_inspection.handle_system_status` |
| `work_context` | `reports.handle_work_context` |
| `work_status` | `reports.handle_work_tracking` |

## Ordering and special-case parity

1. **Response Cache:** the current `Orchestrator._route()` checks the legacy response-cache gate before invoking `dispatch()`.
2. **Registered handlers:** the immutable registry gets first refusal for all 69 baseline keys.
3. **FILE_IMPACT specialized mode:** `handle_file_impact()` checks dependency-language markers first (reverse dependency lookup); only otherwise does it run the general impact analysis. This preserves both original modes and their priority.
4. **needs_llm:** the baseline's explicit fallback remains after registry dispatch. The current `GROQ_INTENTS` set contains 19 values; 6 are already explicitly registered, leaving 13 unregistered values for the dedicated provider fallback.
5. **show_last_result:** preserved as a literal registry key and mapped to `reports.handle_show_last_result`; `Orchestrator.handle()` continues to avoid mutating active context for this read-only result.
6. **Unsupported:** the explicit unsupported response remains after the registered-handler and `needs_llm` gates. No catch-all handler was added.

This manifest verifies branch-key coverage and handler ownership. It does not, by itself, prove behavioral parity; effectful behavior is covered separately by `tests/test_orchestrator_effect_parity.py`, while route/provider boundaries are covered by their authorization tests.
