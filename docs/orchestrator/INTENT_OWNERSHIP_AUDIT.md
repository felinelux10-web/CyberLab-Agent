# Orchestrator Decomposition — Live Ownership Audit

- Repository: `felinelux10-web/CyberLab-Agent`
- Branch: `work/FRIENDLY-DIALOGUE-REPAIR-01`
- Audited code HEAD: `6614de90239e9d16bb89045a05c55c27f3f578a1`
- Authoritative runtime: `lab_v4_dev/core/orchestrator.py`
- Scope: live registry, route facade, authorization boundaries, and a scoped caller/provider trace.
- Status: **migration substantially implemented; final architectural certification remains open**.

## 1. Current structural baseline

The authoritative `_route()` implementation is now a compact dispatcher boundary rather than the former 3,000-line intent switch.

- `orchestrator.py`: 475 lines.
- Dispatcher registry: **68 unique explicit registrations**.
- Declared Intent constants: **168 names / 166 unique values**.
- The current `_route()` has four top-level decision gates: RouteDecision guard, response-cache gate, registered-handler result gate, and the explicit `needs_llm(intent)` fallback.
- Response cache remains before Dispatcher.
- Unregistered intents are not captured by a default handler.
- `FILE_IMPACT` specialized/general behavior is consolidated in `project_analysis.py`; the specialized raw-text branch has priority inside its handler.
- `needs_llm(intent)` remains an explicit fallback after registry dispatch, not a catch-all.
- The old `lab_v4/core/orchestrator.py` is legacy; `lab_v4_dev/core/orchestrator.py` remains authoritative.

## 2. Explicit ownership registry

The following are the live owners registered in `dispatch.py` at the audited HEAD:

### `system_inspection.py`
`space`, `status`, `health`, `memory_status`, `system_status`, `audit_log`, `security_log`, `self_diagnose`, `full_diagnose`

### `maintenance.py`
`clean_device`, `delete_file`, `clean`

### `code_authoring.py`
`modify_code`, `analyze_code`, `generate_code`

### `execution.py`
`run_script`, `list_scripts`, `error_report`, `dry_run`, `run_history`

### `repair.py`
`repair_analyze`, `repair_approve`, `repair_reject`, `pending_fixes`

### `project_inspection.py`
`read_file`, `project_scan`, `project_index`, `search`, `search_code`, `read_external_project`

### `project_analysis.py`
`dependency_map`, `entry_point_query`, `dependents_query`, `dependencies`, `impact_chain_query`, `criticality_query`, `impact_analysis`, `file_impact`, `compare_files`

### `reports.py`
`report`, `session_report`, `progress_report`, `remaining_work`, `project_report`, `context_report`, `history`, `work_status`, `remaining_tasks`, `next_task`, `work_context`, `show_changes`

### `knowledge.py`
`capabilities`, `save_kb`, `skip_kb`, `cyber_explain`

### `releases.py`
`last_project`, `current_version`, `release_index`, `analyze_release`, `compare_versions`, `project_timeline`, `switch_project`, `return_base_project`

### `sessions.py`
`resume`, `session_restore`, `session_save`

### `planning.py`
`cleanup_code`, `plan_change`

The literal key `show_last_result` is also registered to `reports.handle_show_last_result`.

The registry is immutable at runtime and rejects duplicate keys and non-callable handlers. Its tests assert exact ownership and that unregistered intents return `None`.

## 3. Unregistered intent policy

The explicit provider fallback remains defined by `lab_v4_dev/llm/router.py`. After registered handlers have first refusal, the following **13** currently unregistered intent values reach that fallback:

`diagnose`, `propose_solution`, `propose_fix`, `risk_analysis`, `plan`, `decompose`, `refactor_file`, `optimize_code`, `generate_test`, `project_purpose`, `architecture`, `modules`, `execution_flow`

The remaining unregistered Intent values are not silently treated as registered Orchestrator work. ConversationManager owns non-executable/social/agent-self routing; other values retain the existing explicit unsupported behavior if they reach the Orchestrator. A separate product-level intent taxonomy audit is still required before changing those legacy semantics.

## 4. RouteDecision and evidence authorization

The current runtime enforces these boundaries:

1. `Orchestrator.handle()` denies a request with no `RouteDecision`.
2. The parsed intent must equal `RouteDecision.intent`.
3. Only `L-EXEC`, `L-SESSION`, `L-FACT`, and `P-TOOL` may enter Orchestrator.
4. Saved-session restore intents must use `L-SESSION`; the reverse mismatch is denied.
5. `L-EXEC` requires `work_state`; `L-FACT` requires `project_state`.
6. `L-SESSION` is restricted to saved-session evidence scopes and validates output-kind/session-reference combinations.
7. Cross-scope saved/live evidence is denied.
8. TaskChain child steps are re-parsed and re-authorized by ConversationManager; a child cannot widen the parent's route or provider permission.
9. Provider calls from Orchestrator handlers go through the route-bound `authorized_ask` capability. It denies when `provider_allowed` is false and calls the gateway with an explicit provider grant only after that check.
10. Saved-session evidence synthesis and report synthesis now receive that same capability; the handler no longer opens a direct gateway call.

`RouteDecision`, `SessionRef`, and `ContextLock` remain frozen contracts. The handler request context is a frozen dataclass, but its nested dict/list members are not deeply immutable yet; this is recorded as a remaining hardening item rather than claiming deep immutability.

## 5. Handler boundary and service capabilities

- Dispatcher passes a narrow `HandlerFacade`, not the Agent object.
- `HandlerServices` exposes selected service references by intent; e.g. session handlers receive dialogue-memory/restore services, reporting handlers receive memory, and code modification receives database/pipeline capabilities.
- Provider-backed code, repair, diagnostics, release, project-report, and explanation handlers receive the authorized provider callback.
- The facade still exposes the mutable operational `context` object for legacy behavior. This is a compatibility boundary, not a fully capability-secure context API.
- Destructive/effectful handlers are now registered too (`CLEAN_DEVICE`, `DELETE_FILE`, `MODIFY_CODE`, `RUN_SCRIPT`, `REPAIR_APPROVE`). They preserve legacy effects and must remain subject to route authorization, explicit intent resolution, safe-I/O/pipeline controls, and dedicated effect-parity tests. Their migration must not be interpreted as permission to bypass those controls.

## 6. Caller and provider trace (scoped, not exhaustive)

Verified in the inspected source modules:

| Caller / boundary | Current behavior | Status |
|---|---|---|
| `core/agent.py` | Constructs the public Orchestrator facade | Preserved |
| `conversation/conversation_manager.py` | Issues final RouteDecision and forwards it to executable Orchestrator calls | Verified in inspected paths |
| `core/task_chain.py` | Delegates child steps to `ConversationManager.process_execution_step`; no raw child call to Orchestrator | Verified |
| `ConversationManager.process_execution_step` | Re-parses child, re-finalizes route, caps provider permission by parent, then calls Orchestrator with child decision | Verified |
| `core/guard.py` | Compatibility adapter delegates through ConversationManager; no direct provider/Orchestrator call in current file | Verified |
| `loop/event_loop.py` | Defines `submit_prepared`; the inspected Orchestrator helper has no internal caller | Caller graph outside inspected modules remains open |
| `intent/llm_intent_resolver.py` | Uses gateway before final RouteDecision exists | Separate pre-route NLU provider policy required |
| `llm/smart_router.py` | Contains a direct gateway call | Runtime caller/ownership not certified |
| `conversation/conversation_manager.py` | Direct dialogue gateway calls are guarded by the final route's provider permission | Verified at inspected call sites |
| `core/orchestrator.py` | Handler provider calls use `authorized_ask` | Verified |
| `core/orchestrator_handlers/sessions.py` | Saved-session synthesis now uses `authorized_ask` | Updated in audited code HEAD |

This is a scoped source inspection, not a claim that every Python file or dynamic call path in the repository has been exhaustively enumerated. The full repository-wide caller graph remains a mandatory gate.

## 7. Test evidence at the preceding code HEAD

For `b1c80cf398f7961196aaf6da9090ee4eb6236a17`:

- Dialogue/memory regression workflow: **484 passed**.
- Full-suite advisory workflow: **1070 passed, 1 failed**.
- The sole failure exposed an identity-contract conflict: an outer saved-checkpoint ID and a nested DialogueMemory ID are distinct identity domains in legitimate saved records, but the implementation had started requiring them to be equal.

The current code HEAD `6614de90239e9d16bb89045a05c55c27f3f578a1` addresses that defect by accepting distinct IDs only when all nested exchanges carry the nested session ID and the expected DialogueMemory provenance fields (`context_kind`, `conversation_domain`); sparse or mixed-identity nested payloads fail closed. The CI run for this code HEAD must complete before this repair is certified.

## 8. Remaining gates — not marked complete

1. Complete the repository-wide caller graph across all Python modules, tests, entry points, plugins, and dynamic dispatch paths.
2. Complete a provider-call inventory, separating pre-route NLU calls from post-route response-generation calls, and certify every gateway path.
3. Complete an intent-to-route/evidence/provider matrix for all declared Intent values, including those intentionally handled outside Orchestrator.
4. Deep-freeze nested HandlerContext collections or replace them with immutable contracts, after verifying compatibility.
5. Audit each effectful handler against its original legacy behavior and its authorization/effect boundary.
6. Verify all original intent branches and special ordering against the legacy source, including cache, both FILE_IMPACT modes, `show_last_result`, `needs_llm`, and `unsupported`.
7. Run and pass the focused ownership/authorization tests and the complete CI suite on the final HEAD.
8. Only after those gates pass may the legacy route implementation be removed.

**Conclusion:** the bulk of the Strangler migration is present in the live registry, but the full acceptance criteria are not yet certified. No claim of completion or legacy-route removal is authorized by this audit snapshot.
