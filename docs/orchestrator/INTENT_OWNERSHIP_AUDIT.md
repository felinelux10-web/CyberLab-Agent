# Orchestrator Intent Ownership Audit

- Repository: `felinelux10-web/CyberLab-Agent`
- Branch: `work/FRIENDLY-DIALOGUE-REPAIR-01`
- Baseline HEAD: `6f0f35f9a5907fba707128913c2a06513f358e2f`
- Audit source HEAD: `1a67cf3dd5f8595c8c77cc3e61f833067759c371`
- Source file: `lab_v4_dev/core/orchestrator.py`
- Source blob SHA: `242d072593a805c482dad9b9e5dd5a86d1e31dda`
- Scope: complete top-level conditional inventory of the current `_route` body; this is an inventory, not a claim that all ownership/dependency/effect reviews are complete.

## Inventory totals

- Top-level conditional statements found in the current `_route`: **56** (3 infrastructure gates: RouteDecision guard, Response Cache gate, Dispatcher result gate; 53 remaining intent/fallback conditions).
- Ten intent branches have been removed from `_route`: seven system-inspection/log intents and `READ_FILE`, `PROJECT_SCAN`, plus `PROJECT_INDEX` in `project_inspection.py`.
- Distinct `Intent.*` symbols referenced in `_route`: **58**.
- Literal `show_last_result` condition: present.
- Explicit `needs_llm(intent)` fallback: present.
- Response cache gate remains before Dispatcher in the migrated code.
- Migrated registry currently owns: `SPACE`, `STATUS`, `HEALTH`, `MEMORY_STATUS`, `SYSTEM_STATUS`, `AUDIT_LOG`, `SECURITY_LOG`, `READ_FILE`, `PROJECT_SCAN`, `PROJECT_INDEX`.

## Top-level branch inventory

| # | Current line | Exact condition | Candidate owner | Audit status |
|---:|---:|---|---|---|
| 1 | 321 | `if route_decision is not None:` | Special branch / fallback | Pending detailed audit |
| 2 | 351 | `if intent in _cache_intents and not response_attributes:` | Special branch / fallback | Pending detailed audit |
| 3 | 366 | `if _handled is not None:` | Special branch / fallback | Pending detailed audit |
| 4 | 370 | `if intent == Intent.READ_FILE:` | Project Inspection | Pending detailed audit |
| 5 | 413 | `elif intent == Intent.PROJECT_SCAN:` | Project Inspection | Pending detailed audit |
| 6 | 475 | `elif intent == Intent.IMPACT_ANALYSIS:` | Project Analysis & Impact | Pending detailed audit |
| 7 | 484 | `elif intent == Intent.SHOW_CHANGES:` | Project Inspection | Pending detailed audit |
| 8 | 499 | `elif intent == Intent.CLEAN:` | System Maintenance / Destructive | Pending detailed audit |
| 9 | 507 | `elif intent == Intent.CLEAN_DEVICE:` | System Maintenance / Destructive | Pending detailed audit |
| 10 | 520 | `elif intent == Intent.CLEANUP_CODE:` | Planning | Pending detailed audit |
| 11 | 577 | `elif intent in [Intent.REPORT, Intent.SESSION_REPORT]:` | Reports & Work Tracking | Pending detailed audit |
| 12 | 587 | `elif intent in [Intent.PROGRESS_REPORT, Intent.REMAINING_WORK, Intent.PROJECT_REPORT]:` | Reports & Work Tracking | Pending detailed audit |
| 13 | 606 | `elif needs_llm(intent):` | Special branch / fallback | Pending detailed audit |
| 14 | 624 | `elif intent == Intent.CONTEXT_REPORT:` | Reports & Work Tracking | Pending detailed audit |
| 15 | 647 | `elif intent == "show_last_result":` | Reports & Work Tracking | Pending detailed audit |
| 16 | 657 | `elif intent == Intent.HISTORY:` | Reports & Work Tracking | Pending detailed audit |
| 17 | 667 | `elif intent == Intent.LAST_PROJECT:` | Release & Project Lifecycle | Pending detailed audit |
| 18 | 681 | `elif intent == Intent.CURRENT_VERSION:` | Release & Project Lifecycle | Pending detailed audit |
| 19 | 688 | `elif intent == Intent.RELEASE_INDEX:` | Release & Project Lifecycle | Pending detailed audit |
| 20 | 699 | `elif intent == Intent.ANALYZE_RELEASE:` | Release & Project Lifecycle | Pending detailed audit |
| 21 | 726 | `elif intent == Intent.COMPARE_FILES:` | Project Analysis & Impact | Pending detailed audit |
| 22 | 873 | `elif intent == Intent.COMPARE_VERSIONS:` | Release & Project Lifecycle | Pending detailed audit |
| 23 | 904 | `elif intent in [Intent.WORK_STATUS, Intent.REMAINING_TASKS, Intent.NEXT_TASK]:` | Reports & Work Tracking | Pending detailed audit |
| 24 | 929 | `elif intent == Intent.PLAN_CHANGE:` | Planning | Pending detailed audit |
| 25 | 983 | `elif intent == Intent.CAPABILITIES:` | Knowledge | Pending detailed audit |
| 26 | 1003 | `elif intent in [Intent.SELF_DIAGNOSE, Intent.FULL_DIAGNOSE]:` | System Inspection & Audit | Pending detailed audit |
| 27 | 1018 | `elif intent == Intent.PROJECT_INDEX:` | Project Inspection | Pending detailed audit |
| 28 | 1233 | `elif intent == Intent.SEARCH:` | Project Inspection | Pending detailed audit |
| 29 | 1263 | `elif intent == Intent.SEARCH_CODE:` | Project Inspection | Pending detailed audit |
| 30 | 1336 | `elif intent == Intent.FILE_IMPACT and any(w in raw for w in ["تعتمد على","يعتمد على","تستخدم","يستخدم","من يستورد","تستورد"]):` | Project Analysis & Impact | Preserve condition priority |
| 31 | 1360 | `elif intent == Intent.DEPENDENCY_MAP:` | Project Analysis & Impact | Pending detailed audit |
| 32 | 1382 | `elif intent == Intent.READ_EXTERNAL_PROJECT:` | Project Inspection | Pending detailed audit |
| 33 | 1413 | `elif intent == Intent.CYBER_EXPLAIN:` | Knowledge | Pending detailed audit |
| 34 | 1644 | `elif intent == Intent.ENTRY_POINT_QUERY:` | Project Analysis & Impact | Pending detailed audit |
| 35 | 1664 | `elif intent == Intent.DEPENDENTS_QUERY:` | Project Analysis & Impact | Pending detailed audit |
| 36 | 1681 | `elif intent == Intent.DEPENDENCIES:` | Project Analysis & Impact | Pending detailed audit |
| 37 | 1697 | `elif intent == Intent.IMPACT_CHAIN_QUERY:` | Project Analysis & Impact | Pending detailed audit |
| 38 | 1715 | `elif intent == Intent.CRITICALITY_QUERY:` | Project Analysis & Impact | Pending detailed audit |
| 39 | 1737 | `elif intent == Intent.FILE_IMPACT:` | Project Analysis & Impact | Preserve condition priority |
| 40 | 1793 | `elif intent == Intent.PROJECT_TIMELINE:` | Release & Project Lifecycle | Pending detailed audit |
| 41 | 1813 | `elif intent in (Intent.RESUME, Intent.SESSION_RESTORE):` | Session & Memory | Pending detailed audit |
| 42 | 2720 | `elif intent == Intent.SESSION_SAVE:` | Session & Memory | Pending detailed audit |
| 43 | 2771 | `elif intent == Intent.GENERATE_CODE:` | Code Authoring | Pending detailed audit |
| 44 | 2788 | `elif intent == Intent.ANALYZE_CODE:` | Code Authoring | Pending detailed audit |
| 45 | 2838 | `elif intent == Intent.MODIFY_CODE:` | Code Authoring | Pending detailed audit |
| 46 | 2936 | `elif intent == Intent.LIST_SCRIPTS:` | Script Execution | Pending detailed audit |
| 47 | 2951 | `elif intent == Intent.RUN_SCRIPT:` | Script Execution | Pending detailed audit |
| 48 | 2991 | `elif intent == Intent.ERROR_REPORT:` | Script Execution | Pending detailed audit |
| 49 | 3004 | `elif intent == Intent.DRY_RUN:` | Script Execution | Pending detailed audit |
| 50 | 3021 | `elif intent == Intent.RUN_HISTORY:` | Script Execution | Pending detailed audit |
| 51 | 3033 | `elif intent == Intent.REPAIR_ANALYZE:` | Repair Workflow | Pending detailed audit |
| 52 | 3052 | `elif intent == Intent.REPAIR_APPROVE:` | Repair Workflow | Pending detailed audit |
| 53 | 3068 | `elif intent == Intent.REPAIR_REJECT:` | Repair Workflow | Pending detailed audit |
| 54 | 3073 | `elif intent == Intent.PENDING_FIXES:` | Repair Workflow | Pending detailed audit |
| 55 | 3085 | `elif intent in (Intent.SWITCH_PROJECT, Intent.RETURN_BASE_PROJECT):` | Release & Project Lifecycle | Pending detailed audit |
| 56 | 3193 | `elif intent == Intent.AUDIT_LOG:` | System Inspection & Audit | Pending detailed audit |
| 57 | 3228 | `elif intent == Intent.SAVE_KB:` | Knowledge | Pending detailed audit |
| 58 | 3242 | `elif intent == Intent.SKIP_KB:` | Knowledge | Pending detailed audit |
| 59 | 3248 | `elif intent == Intent.SECURITY_LOG:` | System Inspection & Audit | Pending detailed audit |
| 60 | 3262 | `elif intent == Intent.WORK_CONTEXT:` | Reports & Work Tracking | Pending detailed audit |
| 61 | 3287 | `elif intent == Intent.DELETE_FILE:` | System Maintenance / Destructive | Pending detailed audit |

## Referenced Intent symbols

- `ANALYZE_CODE` — Code Authoring
- `ANALYZE_RELEASE` — Release & Project Lifecycle
- `AUDIT_LOG` — System Inspection & Audit
- `CAPABILITIES` — Knowledge
- `CLEAN` — System Maintenance / Destructive
- `CLEANUP_CODE` — Planning
- `CLEAN_DEVICE` — System Maintenance / Destructive
- `COMPARE_FILES` — Project Analysis & Impact
- `COMPARE_VERSIONS` — Release & Project Lifecycle
- `CONTEXT_REPORT` — Reports & Work Tracking
- `CRITICALITY_QUERY` — Project Analysis & Impact
- `CURRENT_VERSION` — Release & Project Lifecycle
- `CYBER_EXPLAIN` — Knowledge
- `DELETE_FILE` — System Maintenance / Destructive
- `DEPENDENCIES` — Project Analysis & Impact
- `DEPENDENCY_MAP` — Project Analysis & Impact
- `DEPENDENTS_QUERY` — Project Analysis & Impact
- `DRY_RUN` — Script Execution
- `ENTRY_POINT_QUERY` — Project Analysis & Impact
- `ERROR_REPORT` — Script Execution
- `FILE_IMPACT` — Project Analysis & Impact
- `FULL_DIAGNOSE` — System Inspection & Audit
- `GENERATE_CODE` — Code Authoring
- `HISTORY` — Reports & Work Tracking
- `IMPACT_ANALYSIS` — Project Analysis & Impact
- `IMPACT_CHAIN_QUERY` — Project Analysis & Impact
- `LAST_PROJECT` — Release & Project Lifecycle
- `LIST_SCRIPTS` — Script Execution
- `MODIFY_CODE` — Code Authoring
- `NEXT_TASK` — Reports & Work Tracking
- `PENDING_FIXES` — Repair Workflow
- `PLAN_CHANGE` — Planning
- `PROGRESS_REPORT` — Reports & Work Tracking
- `PROJECT_INDEX` — Project Inspection
- `PROJECT_REPORT` — Reports & Work Tracking
- `PROJECT_SCAN` — Project Inspection
- `PROJECT_TIMELINE` — Release & Project Lifecycle
- `READ_EXTERNAL_PROJECT` — Project Inspection
- `READ_FILE` — Project Inspection
- `RELEASE_INDEX` — Release & Project Lifecycle
- `REMAINING_TASKS` — Reports & Work Tracking
- `REMAINING_WORK` — Reports & Work Tracking
- `REPAIR_ANALYZE` — Repair Workflow
- `REPAIR_APPROVE` — Repair Workflow
- `REPAIR_REJECT` — Repair Workflow
- `REPORT` — Reports & Work Tracking
- `RESUME` — Session & Memory
- `RETURN_BASE_PROJECT` — Release & Project Lifecycle
- `RUN_HISTORY` — Script Execution
- `RUN_SCRIPT` — Script Execution
- `SAVE_KB` — Knowledge
- `SEARCH` — Project Inspection
- `SEARCH_CODE` — Project Inspection
- `SECURITY_LOG` — System Inspection & Audit
- `SELF_DIAGNOSE` — System Inspection & Audit
- `SESSION_REPORT` — Reports & Work Tracking
- `SESSION_RESTORE` — Session & Memory
- `SESSION_SAVE` — Session & Memory
- `SHOW_CHANGES` — Project Inspection
- `SKIP_KB` — Knowledge
- `SWITCH_PROJECT` — Release & Project Lifecycle
- `WORK_CONTEXT` — Reports & Work Tracking
- `WORK_STATUS` — Reports & Work Tracking

## Mandatory special-path notes

1. `FILE_IMPACT` occurs in specialized and general branches. The specialized raw-text condition must remain ahead of the general branch.
2. `show_last_result` is a literal string condition, not an `Intent.SHOW_LAST_RESULT` reference.
3. `needs_llm(intent)` remains an independent fallback and must not become a catch-all registered handler.
4. The response-cache gate must execute before explicit handler dispatch. In particular, `HEALTH` remains cache-eligible.
5. This inventory does not yet certify the complete direct/indirect caller graph, provider call graph, or each handler's evidence-scope contract. Those remain gates before later migrations.

## Migration status

| Scope | State |
|---|---|
| Dispatcher foundation | Implemented |
| Read-only inspection pilot (5 intents) | Moved to `system_inspection.py` |
| Audit/security log readers (2 intents) | Moved to `system_inspection.py` |
| Project inspection (`READ_FILE`, `PROJECT_SCAN`, `PROJECT_INDEX`) | Moved to `project_inspection.py`; file lookup containment behavior preserved and tested; project scan remains local and audit-emitting; project registry/list and layer-map behavior preserved |
| Remaining branch ownership | Legacy route; audit required before each migration |
| Caller graph (TaskChain, Guard, direct callers) | Not certified complete |
| Provider/evidence authorization matrix | Not certified complete |
| Legacy route removal | Prohibited until final parity criteria pass |

## Policy

No unregistered intent is captured by a default handler. The dispatcher returns `None` for unregistered intents so the existing route continues to own them during the Strangler migration.


## Caller and authorization trace (scoped source inspection)

The following call sites were verified in the current branch source. This is a scoped trace of the core, conversation, intent, LLM, loop, and root entry-point modules inspected for the migration; it is not a certification that every Python file in the repository has been exhaustively scanned.

| File / location | Observed behavior | Migration consequence |
|---|---|---|
| `lab_v4_dev/core/agent.py:94` | Constructs `Orchestrator(self, context=self.context)` | Preserve the public constructor and import path |
| `lab_v4_dev/conversation/conversation_manager.py:383` | Creates the authoritative `RouteDecision` | ConversationManager remains the decision owner |
| `lab_v4_dev/conversation/conversation_manager.py` SYSTEM dispatch | Conditionally forwards `route_decision` to `Orchestrator.handle` | Compatibility path is conditional on the handle signature |
| `lab_v4_dev/conversation/conversation_manager.py:4374` | Generic executable-intent dispatch calls `orchestrator.handle` without forwarding `route_decision` | Confirmed authorization gap; must be handled in caller migration, not hidden by handler movement |
| `lab_v4_dev/core/orchestrator.py:150` | Calls `execute_chain(steps, self)` | Task-chain coordinator remains coupled to the facade |
| `lab_v4_dev/core/task_chain.py:82` | Executes each step using `orchestrator.handle(step)` | Child steps re-enter the raw-text facade without an inherited decision |
| `lab_v4_dev/core/guard.py:52` | Calls provider `ask(raw, ...)` directly | Provider-policy bypass candidate |
| `lab_v4_dev/core/guard.py:63,65` | Calls `agent.orchestrator.handle(raw)` without a RouteDecision | Legacy compatibility path requires explicit migration/retirement decision |
| `lab_v4_dev/core/orchestrator.py:59,67` | Builds `PreparedExecutionRequest` and calls `loop.submit_prepared` inside `_submit_prepared_execution` | Prepared handoff exists |
| `lab_v4_dev/loop/event_loop.py:43` | Defines `submit_prepared` | No other call site was found in the scoped source scan |
| `lab_v4_dev/core/orchestrator.py` | `_submit_prepared_execution` has no internal caller in the inspected file | Do not infer that the helper is unused repository-wide |

### Provider-call findings in inspected modules

Direct `ask()` calls were found outside the Orchestrator's local `authorized_ask` closure:

- `core/guard.py` — direct raw-request provider call.
- `core/code_engine.py` — three direct provider calls in code-generation/analysis/modification services.
- `core/repair/error_analyzer.py` and `core/repair/fix_generator.py` — direct provider calls in repair services.
- `intent/llm_intent_resolver.py` — direct provider call in intent resolution.
- `llm/smart_router.py` — direct provider call.
- `monitor/self_diagnostics.py` — `check_groq()` directly calls `ask()`; `FULL_DIAGNOSE` therefore cannot be classified as a pure read-only handler without a provider-policy decision.

These are not automatically safe merely because they are called by a service. Before migrating the associated intents, each call must either receive an authorized provider capability or remain behind a separately audited compatibility boundary.

### Confirmed holdbacks

- `SELF_DIAGNOSE` and `FULL_DIAGNOSE` remain in the legacy route because `run_diagnostics(quick=False)` can call `check_groq()`, and the diagnostics service also writes diagnostic history.
- `CYBER_EXPLAIN`, `GENERATE_CODE`, `ANALYZE_CODE`, `MODIFY_CODE`, `REPAIR_ANALYZE`, and repair application paths require provider/effect audits before migration.
- TaskChain and Guard remain unchanged in this stage. Their known authorization gaps are recorded for the caller-migration stage.
- The scoped scan did not fetch every Python module in `lab_v4_dev` or every test file; the remaining repository-wide caller audit is still an explicit gate.
