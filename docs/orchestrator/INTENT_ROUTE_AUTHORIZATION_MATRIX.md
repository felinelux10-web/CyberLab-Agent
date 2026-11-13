# Intent → Route / Evidence / Provider Authorization Matrix

- Repository: `felinelux10-web/CyberLab-Agent`
- Branch: `work/FRIENDLY-DIALOGUE-REPAIR-01`
- Source files: `lab_v4_dev/intent/intents.py`, `conversation/conversation_manager.py`, `core/orchestrator_handlers/dispatch.py`, `llm/router.py`
- Declared Intent values: **166 unique values** (168 declarations, including aliases)
- Registered dispatch keys: **69** (includes the literal `show_last_result`)
- `needs_llm` values: **19 total; 13 remain unregistered and reach the explicit fallback**
- Purpose: explicit inventory of the route policy currently implemented; this is not a replacement dispatcher.

## Route-level authorization contract

| Final route | Owner | Evidence scope | Provider permission |
|---|---|---|---|
| `L-SOCIAL` | local social responder | `none` | denied |
| `L-LIVE` | live dialogue responder | `live_exchanges` only when live-history evidence is requested; otherwise `none` | allowed only by RouteDecision |
| `L-SESSION` | saved-session handler | `saved_session` for one exact SessionRef; `saved_sessions` for an explicit collection/list | only summary/report/topic-summary synthesis, and only when session synthesis is enabled |
| `L-FACT` | local project/agent-fact responder | `project_state` | allowed only by RouteDecision; local evidence remains primary |
| `L-EXEC` | Orchestrator registered handler or explicit provider fallback | `work_state` | allowed only by RouteDecision and capped by parent authorization |
| `P-TOOL` | technical knowledge/tool responder | `none` in the current finalizer | allowed only by RouteDecision |
| `CLARIFY` | ConversationManager clarification | `none` | denied |
| `DENY` | policy denial | `none` | denied |

**Global overrides:** an explicit saved-session selection may change the selected owner to `L-SESSION`; a live history request may select `L-LIVE`; the selected session/evidence reference must be validated before dispatch. A route grant is not proof that a handler actually calls a provider. Every provider call must pass the gateway capability. Parent execution permission may only reduce a child grant, never widen it.

## Per-intent inventory

The route is intentionally context-sensitive. The table records the current default owner/route and the explicit dynamic cases, not a claim that every text containing the same intent must take one fixed route.

| Intent value | Owner | Route rule | Evidence scope | Provider |
|---|---|---|---|---|
| `add_class` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `add_function` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `add_task` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `agent_architecture` | ConversationManager agent-fact responder | L-FACT | project_state | Yes, after local evidence retrieval |
| `agent_capabilities` | ConversationManager agent-fact responder | L-FACT | project_state | Yes, after local evidence retrieval |
| `agent_execution_flow` | ConversationManager agent-fact responder | L-FACT | project_state | Yes, after local evidence retrieval |
| `agent_identity` | ConversationManager agent-fact responder | L-FACT | project_state | Yes, after local evidence retrieval |
| `agent_limits` | ConversationManager agent-fact responder | L-FACT | project_state | Yes, after local evidence retrieval |
| `analyze_code` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `analyze_release` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `architecture` | Knowledge responder / knowledge handler | L-FACT for project domain; P-TOOL for technical domain | project_state for L-FACT; otherwise none | Yes, only when RouteDecision grants |
| `architecture_check` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `audit_log` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `auto_fix` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `cancel` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `capabilities` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `clean` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `clean_device` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `cleanup_code` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `compare_files` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `compare_reference` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `compare_snapshots` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `compare_versions` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `complete_task` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `constraints` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `context_report` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `create_file` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `create_lab` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `critical_files` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `criticality_query` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `current_task` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `current_version` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `cyber_explain` | Knowledge responder / knowledge handler | L-FACT for project domain; P-TOOL for technical domain | project_state for L-FACT; otherwise none | Yes, only when RouteDecision grants |
| `decompose` | Explicit needs_llm fallback | L-EXEC | work_state | Yes only through authorized_ask |
| `delete_file` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `delete_snapshot` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `dependencies` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `dependency_map` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `dependents_query` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `diagnose` | Explicit needs_llm fallback | L-EXEC | work_state | Yes only through authorized_ask |
| `draft` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `drift_check` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `dry_run` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `entry_point_query` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `entrypoint` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `error_report` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `execution_flow` | Explicit needs_llm fallback | L-EXEC | work_state | Yes only through authorized_ask |
| `failure_reason` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `file_impact` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `find_callers` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `find_class` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `find_file` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `find_function` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `find_references` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `find_usages` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `forget` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `full_diagnose` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `generate_code` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `generate_test` | Explicit needs_llm fallback | L-EXEC | work_state | Yes only through authorized_ask |
| `health` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `help` | ConversationManager dialogue owner | L-SOCIAL / L-LIVE / L-FACT / P-TOOL according to semantic domain and act | none / live_exchanges / project_state | Route-dependent; L-SOCIAL denies |
| `history` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `impact_analysis` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `impact_chain_query` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `integrity_check` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `last_project` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `list_scripts` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `list_snapshots` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `load_reference` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `logs` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `memory_dump` | ConversationManager memory owner | L-SESSION / L-LIVE | saved_sessions / saved_session / live_exchanges | Conditional by final route |
| `memory_status` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `modify_class` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `modify_code` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `modify_file` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `modify_function` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `modules` | Explicit needs_llm fallback | L-EXEC | work_state | Yes only through authorized_ask |
| `move_file` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `next_task` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `note` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `optimize_code` | Explicit needs_llm fallback | L-EXEC | work_state | Yes only through authorized_ask |
| `pending_fixes` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `personal_chat` | ConversationManager dialogue owner | L-SOCIAL / L-LIVE / L-FACT / P-TOOL according to semantic domain and act | none / live_exchanges / project_state | Route-dependent; L-SOCIAL denies |
| `plan` | ConversationManager / Orchestrator fallback | L-LIVE, L-SOCIAL, L-EXEC or P-TOOL according to domain and target | live_exchanges, work_state or none | Yes only when final route grants |
| `plan_change` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `progress_report` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `project_index` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `project_map` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `project_purpose` | Explicit needs_llm fallback | L-EXEC | work_state | Yes only through authorized_ask |
| `project_report` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `project_scan` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `project_timeline` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `propose_fix` | Explicit needs_llm fallback | L-EXEC | work_state | Yes only through authorized_ask |
| `propose_solution` | ConversationManager / Orchestrator fallback | L-LIVE, L-SOCIAL, L-EXEC or P-TOOL according to domain and target | live_exchanges, work_state or none | Yes only when final route grants |
| `read_class` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `read_external_project` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `read_file` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `read_function` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `recovery` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `refactor_file` | Explicit needs_llm fallback | L-EXEC | work_state | Yes only through authorized_ask |
| `refactor_project` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `related_files` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `release_index` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `remaining_tasks` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `remaining_work` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `remember` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `remove_class` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `remove_function` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `rename_file` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `repair_analyze` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `repair_approve` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `repair_reject` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `replace_body` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `report` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `restart` | ConversationManager control | L-SOCIAL | none | No |
| `restore_snapshot` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `restore_stable` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `resume` | Sessions handler | L-SESSION for saved selection; otherwise L-EXEC compatibility/work path | saved_session or work_state | Conditional by final route; session synthesis is separately gated |
| `return_base_project` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `risk_analysis` | Explicit needs_llm fallback | L-EXEC | work_state | Yes only through authorized_ask |
| `rollback` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `root_cause` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `run` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `run_file` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `run_history` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `run_project` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `run_script` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `run_tests` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `save_kb` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `schedule` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `search` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `search_code` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `security_log` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `self_diagnose` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `session_report` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `session_restore` | Sessions handler | L-SESSION for saved selection; otherwise L-EXEC compatibility/work path | saved_session or work_state | Conditional by final route; session synthesis is separately gated |
| `session_save` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `show_changes` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `show_error` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `show_last_result` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `skip_kb` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `snapshot` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `space` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `stable_snapshot` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `status` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `stop` | ConversationManager control | L-SOCIAL | none | No |
| `stop_execution` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `switch_project` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `system_status` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `test_file` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `test_function` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `test_project` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `test_report` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `todo_add` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `todo_complete` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `todo_list` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `todo_pending` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `todo_remove` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `unclear` | ConversationManager dialogue owner | L-SOCIAL / L-LIVE / L-FACT / P-TOOL according to semantic domain and act | none / live_exchanges / project_state | Route-dependent; L-SOCIAL denies |
| `unknown` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `unsupported` | ConversationManager dialogue owner | L-SOCIAL / L-LIVE / L-FACT / P-TOOL according to semantic domain and act | none / live_exchanges / project_state | Route-dependent; L-SOCIAL denies |
| `update_lab` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `upgrade_code` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `verify_fix` | Orchestrator unsupported boundary | L-EXEC default, then unsupported (no handler) | work_state | No provider call in unsupported fallback |
| `work_context` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |
| `work_status` | Registered Orchestrator handler | L-EXEC by default; saved-session/context overrides are validated | work_state by default; validated route may narrow scope | RouteDecision grant required; handler may remain local |

## Interpretation notes

1. The registry is first refusal after the response-cache gate. Unregistered intents are not captured by a default handler.
2. The explicit `needs_llm(intent)` fallback is separate from the handler registry and must use `authorized_ask`.
3. `CYBER_EXPLAIN` and `ARCHITECTURE` are domain-sensitive: project questions use `L-FACT`; technical explanations use `P-TOOL`.
4. `RESUME` and `SESSION_RESTORE` may represent saved-dialogue selection or work-checkpoint behavior; the selected identity and evidence scope decide the route.
5. `MEMORY_DUMP` is not a general Orchestrator handler: live-history and saved-memory operations are selected by ConversationManager.
6. Unmapped values remain explicit unsupported/clarification outcomes; they must not acquire an implicit provider or execution path.
7. The matrix must be regenerated or reviewed whenever Intent declarations, registry ownership, `needs_llm`, or `finalize_route` changes.
