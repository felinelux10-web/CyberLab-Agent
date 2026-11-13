# Orchestrator Decomposition — Final Live Ownership Audit

- Repository: `felinelux10-web/CyberLab-Agent`
- Active branch: `work/FRIENDLY-DIALOGUE-REPAIR-01`
- Baseline commit: `6f0f35f9a5907fba707128913c2a06513f358e2f`
- Baseline `lab_v4_dev/core/orchestrator.py` blob: `28bafb091cd27b682ef83ef77c27a108e864eb02`
- Audited implementation code HEAD: `08146e7bc941ecafd426df9aed85a7218e17b9b8`
- Audit date: 2026-11-13
- Status: **Orchestrator decomposition and its eight final audit gates are verified by source inspection and CI. Residual boundaries are recorded below; no APK build is claimed.**

## 1. Baseline and structural result

The baseline Orchestrator was 3,416 lines. At the audited code HEAD, `lab_v4_dev/core/orchestrator.py` is 481 lines and retains the public `handle()` entry point, route authorization, response-cache ordering, and the compact `_route()` dispatch boundary.

The active handler package contains:

- An immutable, duplicate-safe `HANDLER_REGISTRY` with **69 keys**.
- Twelve domain handler modules: system inspection, project inspection, project analysis, reports, knowledge, releases, sessions, execution, code authoring, maintenance, planning, and repair.
- Separate dispatch, request-context, and service-capability modules.
- No catch-all handler for unregistered intents.

The previous live audit recorded 68 registrations. Direct extraction from the baseline branch conditions and the current registry establishes the correct count as **69**, including the literal `show_last_result` key. The parity manifest and test now use the verified count.

## 2. Intent ownership and legacy branch parity

- Unique declared Intent values: **166**.
- Baseline Orchestrator branch keys: **69**.
- Current registered keys: **69**.
- Missing baseline keys: **0**.
- Unexpected current keys: **0**.
- The complete per-intent owner/route/evidence/provider inventory is in `INTENT_ROUTE_AUTHORIZATION_MATRIX.md`.
- Exact branch-to-handler mapping is in `LEGACY_BRANCH_PARITY.md`.

The current `needs_llm` list contains 19 values. Six overlap registered handlers and are handled by the registry first; the remaining 13 continue through the explicit provider fallback. Other unregistered values remain explicit unsupported/clarification outcomes.

## 3. Ordering and special branches

The following order is verified in `Orchestrator._route()` and covered by tests:

1. RouteDecision ownership guard.
2. Response Cache gate.
3. Registered handler dispatch.
4. Explicit `needs_llm(intent)` fallback.
5. Explicit unsupported fallback.

Special behavior is retained:

- Both `FILE_IMPACT` modes remain in `project_analysis.handle_file_impact()`: dependency/reverse-import questions are checked first; general impact analysis is the fallback mode.
- `show_last_result` remains a literal registry key mapped to `reports.handle_show_last_result`.
- Read-only `show_last_result` and session reports do not mutate active context.
- No default handler was added for unknown or unsupported intents.

## 4. RouteDecision, evidence, session identity, and provider authorization

The authoritative route is finalized in ConversationManager and passed downstream as a frozen `RouteDecision`. Orchestrator denies a missing decision, mismatched intent, unauthorized route, invalid session/output combination, or invalid evidence scope.

Verified contract points:

- `RouteDecision`, `SessionRef`, and `ContextLock` remain frozen contracts.
- RouteDecision metadata is recursively frozen.
- `L-SESSION` accepts only saved-session evidence scopes and validates the selected session reference and output kind.
- Saved-session and live-dialogue evidence cannot be mixed across scopes.
- Exact nested session identity is preserved; sparse or mixed-identity nested payloads fail closed.
- `TaskChain` child steps are re-parsed and re-authorized by ConversationManager; the parent route must grant `L-EXEC`, and child provider permission cannot exceed the parent grant.
- Handler provider calls receive the route-bound `authorized_ask` capability.
- `gateway.ask()` now defaults to `provider_allowed=False`; provider access is explicit.
- The gateway evaluates privacy restrictions before returning a route-provider denial, preserving privacy-specific error classification.
- Saved-session evidence synthesis and report synthesis use the same authorized capability; provider synthesis remains conditional on the final session route, supported output kind, and session-synthesis policy.

## 5. Provider-call inventory

The repository-wide runtime AST inventory identifies only two direct gateway boundaries:

| Runtime boundary | Policy |
|---|---|
| `conversation/conversation_manager.py` | Dialogue provider calls require a non-null final RouteDecision with `provider_allowed=True`. |
| `core/orchestrator.py` | Handler provider calls are exposed through `authorized_ask`; the callback denies before reaching the gateway. |

Pre-route NLU is deliberately separate:

- `intent/llm_intent_resolver.py` has no gateway import and requires an explicitly injected `nlu_provider` capability.
- The canonical IntentParser calls `resolve(user_input)` without that capability, so pre-route external NLU is disabled by default.
- `llm/smart_router.py` has no direct gateway import and requires an injected `authorized_ask` capability.
- The legacy Groq resolver is only a compatibility wrapper around the provider-neutral resolver.

No handler module has a direct gateway import. The gateway inventory test scans the active source tree and fails if an unapproved import or call boundary is introduced.

## 6. Handler context and capability boundary

- `HandlerContext` is a frozen dataclass; its nested session selector, response attributes, and conversation history are recursively frozen.
- Contract mappings in `Request`, `RoutingDecision`, `RouteDecision`, `PreparedExecutionRequest`, and `AuditEvent` are recursively frozen.
- `HandlerServices` is a frozen capability container. Intent-specific service references remain limited to the declared fields.
- `HandlerFacade` is frozen and exposes no Agent object. Its lazy pipeline cache uses an internal assignment while preserving the frozen public surface.
- The facade's underlying operational `context` reference remains mutable for legacy state updates. This is an explicit compatibility boundary, not a claim that the ContextStore itself is immutable.

## 7. Effectful-handler parity and safety

Dedicated tests cover the legacy effects and authorization boundary for:

- `CLEAN_DEVICE`
- `DELETE_FILE`
- `MODIFY_CODE`
- `RUN_SCRIPT`
- `REPAIR_ANALYZE`
- `REPAIR_APPROVE`

The tests verify the cleaner invocation/report, safe-delete backup and snapshot contract, explicit script selection and sandbox execution, repair proposal persistence and approval application, and SafePipeline write plus post-write verification.

Effectful Orchestrator intents are denied without a final RouteDecision or with the wrong work-evidence scope. Existing safe-I/O and SafePipeline controls remain in place; the handler migration does not grant additional execution authority.

## 8. Repository-wide caller graph

The caller-graph test scans active Python source across the repository root, including the active package, entry points, and any plugin/source directories. It separates the retained `lab_v4/` legacy tree and confirms that active source does not import from it.

Verified active call paths:

| Caller / boundary | Verified behavior |
|---|---|
| `core/agent.py` | Enters through `ConversationManager.process()`. |
| `conversation/conversation_manager.py` | Sole active caller of `Orchestrator.handle()`. |
| `core/task_chain.py` | Calls `ConversationManager.process_execution_step()`; it does not call Orchestrator directly. |
| `core/guard.py` | Compatibility adapter delegates to ConversationManager; it has no gateway or direct Orchestrator call. |
| `core/orchestrator.py` | Owns the internal `_route()` call and defines the PreparedExecutionRequest handoff helper. |
| `loop/event_loop.py` | Defines raw `submit()` and typed `submit_prepared()`; no active raw-loop submit caller was found. |

The PreparedExecutionRequest handoff is present but dormant: `submit_prepared()` is called only by `Orchestrator._submit_prepared_execution()`, and that helper has no internal caller. This is recorded as an unused compatibility path, not misrepresented as an integrated runtime path.

The scan also identifies Guard's dynamic `getattr(manager, "process")` delegation. Test-only direct Orchestrator calls remain confined to tests.

## 9. CI evidence at the audited implementation HEAD

GitHub Actions run `43438137467`, head SHA `08146e7bc941ecafd426df9aed85a7218e17b9b8`:

- Focused dialogue regressions: **484 passed**.
- Full-suite advisory job: **1,102 passed**.
- Failed tests: **0**.
- The job logs, not only the overall workflow conclusion, were inspected.

The full suite includes the ownership, route authorization, provider-call inventory, deep immutability, caller graph, effect parity, exact legacy branch parity, response-cache ordering, and both FILE_IMPACT mode tests.

## 10. Execution phases and scope boundary

| Phase | Result |
|---|---|
| 0 — Baseline | Baseline commit/blob and current CI evidence recorded |
| 0.5 — Intent Ownership Audit | Complete: 166-value matrix, 69-key parity, caller/provider inventories |
| 1 — Dispatcher Foundation | Complete |
| 2 — Small Read-only Pilot | Complete |
| 3 — Project Inspection | Complete |
| 4 — Project Analysis | Complete |
| 5 — Reports / Knowledge | Complete |
| 6 — Release / Project Lifecycle | Complete |
| 7 — Sessions / Memory | Complete |
| 8 — Code Authoring / Execution | Complete |
| 9 — Repair / Destructive Operations | Complete |
| 10 — Legacy Caller Migration | Complete for the active runtime call graph |
| 11 — Final Parity Verification | Complete at the audited code HEAD |
| 12 — Legacy Route Removal | The active 3,000-line intent switch had already been replaced by the compact dispatch boundary before this final audit; this session performed no further legacy-tree deletion. The separate `lab_v4/` tree remains retained. |

Out of scope and not claimed as complete: APK packaging/build, UI work, API work, a ConversationManager/EventLoop/SafePipeline rewrite, or deletion of the retained `lab_v4/` legacy tree.

## 11. Final conclusion

The Orchestrator decomposition is verified against the baseline branch-key inventory, route/evidence/provider authorization boundaries, effectful-handler parity, and the active runtime caller graph. The focused and full CI suites pass at the audited implementation HEAD.

The remaining documented compatibility boundaries are the mutable operational ContextStore reference inside HandlerFacade and the dormant PreparedExecutionRequest handoff helper. Neither is represented as an active caller or as fully immutable. No further legacy cleanup is authorized by this audit.
