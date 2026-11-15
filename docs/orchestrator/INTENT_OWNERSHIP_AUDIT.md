# Orchestrator Decomposition — Live Ownership Audit and Single-Owner Corrections

- Repository: `felinelux10-web/CyberLab-Agent`
- Active branch: `work/FRIENDLY-DIALOGUE-REPAIR-01`
- Baseline commit: `6f0f35f9a5907fba707128913c2a06513f358e2f`
- Baseline `lab_v4_dev/core/orchestrator.py` blob: `28bafb091cd27b682ef83ef77c27a108e864eb02`
- Audited implementation and verification HEAD: `4b76e484f9e7ccc1324dba6ba0ef7a3ee0acbb82`
- Audit date: 2026-11-13
- Status: **The 2026-11-13 audit below is a historical baseline, not the final completion claim. Single-owner corrections were pushed on 2026-11-15; final closure remains pending the post-change CI run and end-to-end dialogue scenarios. No APK build is claimed.**

## 1. Baseline and structural result

The baseline Orchestrator was 3,416 lines. At the audited code HEAD, `lab_v4_dev/core/orchestrator.py` is 481 lines and retains the public `handle()` entry point and route authorization; the 2026-11-15 correction moved response-cache ordering and registry dispatch into `orchestrator_handlers.dispatch.route_request`, leaving no parallel `_route()` implementation in the facade.

The active handler package contains:

- An immutable, duplicate-safe `HANDLER_REGISTRY` with **82 keys**: 69 baseline Orchestrator branch keys plus 13 provider-backed intent keys.
- Twelve domain handler modules plus the dedicated `provider_fallback.py` handler for provider-backed intents.
- Separate dispatch, request-context, and service-capability modules.
- No catch-all handler for unregistered intents.

The previous live audit recorded 68 registrations. Direct extraction from the baseline branch conditions and the current registry establishes the correct count as **69**, including the literal `show_last_result` key. The parity manifest and test now use the verified count.

### Current branch structure after the 2026-11-15 correction

Source inspection at the current branch tip records `lab_v4_dev/core/orchestrator.py` at **352 lines**. Its `_route()` method has been removed; `handle()` calls `orchestrator_handlers.dispatch.route_request()` directly. The pre-handler profile/impact gates and post-response profile shaping now live in `orchestrator_handlers/policy.py`. The dispatch module owns the response-cache gate, the unique registry lookup, and the unsupported boundary. Provider-backed intents are registry entries, not a second branch after the registry.

The active route ownership boundary is now explicit:

- `ConversationManager` owns `L-SOCIAL`, `L-LIVE`, and `L-FACT`.
- `Orchestrator` accepts only `L-EXEC`, `L-SESSION`, and `P-TOOL`; it rejects `L-FACT`.
- `ConversationManager._dispatch()` has no parser/mode compatibility fallback; a missing final RouteDecision is denied.
- `HANDLER_REGISTRY` owns all 69 baseline Orchestrator branch keys plus 13 provider-backed intents.
- `llm/router.py` is now a read-only classification adapter derived from `HANDLER_REGISTRY`; its independent provider-intent list was removed. The unused `llm/smart_router.py` and `core/guard.py` parallel routing modules were deleted, and their unused entrypoint imports were removed from `run.py`.
- `EventLoop` accepts only `PreparedExecutionRequest`; the raw `submit()` plus parser/clarifier/decomposer path is removed, and `tick()` rejects raw scheduler items.
- Explicit `ماذا عن X؟` subjects are extracted from the current utterance before NLU context inheritance. A technical/general domain change starts a clean dialogue branch, preventing stale entities such as `SQL Injection` from contaminating an unrelated subject.

This is a source-level structural result only. The post-correction test suite and end-to-end dialogue scenarios are still pending; no final completion claim is made.

## 2. Intent ownership and legacy branch parity

- Unique declared Intent values: **166**.
- Baseline Orchestrator branch keys: **69**.
- Current registered keys: **82**.
- Missing baseline keys: **0**.
- Additional registered provider-backed keys: **13**.
- The complete per-intent owner/route/evidence/provider inventory is in `INTENT_ROUTE_AUTHORIZATION_MATRIX.md`.
- Exact branch-to-handler mapping is in `LEGACY_BRANCH_PARITY.md`.

The current provider-backed list contains 13 values. All 13 are registered to `provider_fallback.handle_provider_intent`; the six former overlaps were removed from the provider list. `Orchestrator._route()` no longer contains a secondary provider execution branch. Other unregistered values remain explicit unsupported/clarification outcomes.

## 3. Ordering and special branches

The following order is implemented by `orchestrator_handlers.dispatch.route_request()` and covered by tests:

1. RouteDecision ownership guard.
2. Response Cache gate.
3. Single `HANDLER_REGISTRY` dispatch, including all provider-backed intents.
4. Explicit unsupported fallback when no registered owner exists.

Special behavior is retained:

- Both `FILE_IMPACT` modes remain in `project_analysis.handle_file_impact()`: dependency/reverse-import questions are checked first; general impact analysis is the fallback mode.
- `show_last_result` remains a literal registry key mapped to `reports.handle_show_last_result`.
- Read-only `show_last_result` and session reports do not mutate active context.
- No default handler was added for unknown or unsupported intents.

## 4. RouteDecision, evidence, session identity, and provider authorization

The authoritative route is finalized in ConversationManager and passed downstream as a frozen `RouteDecision`. Orchestrator denies a missing decision, mismatched intent, unauthorized route, invalid session/output combination, or invalid evidence scope. `PreparedExecutionRequest` now carries that exact decision; its contract accepts only matching `L-EXEC` + `work_state` authority, and EventLoop validates the grant again at queue and processing boundaries.

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
| `core/orchestrator.py` | Creates the route-bound `authorized_ask` capability; the callback denies before reaching the gateway. |
| `core/orchestrator_handlers/provider_fallback.py` | Consumes only the injected `authorized_ask` capability for the 13 provider-backed registered intents. |

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
- The prepared-execution submission capability is exposed only to the `RUN_SCRIPT` handler; the handler cannot access the Agent or EventLoop directly.
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

The tests verify the cleaner invocation/report, safe-delete backup and snapshot contract, explicit script selection through the prepared EventLoop path, repair proposal persistence across ContextStore updates and explicit approval, and SafePipeline write plus post-write verification. `RUN_SCRIPT` rejects implicit selection of the newest script, constrains the resolved path to the workspace, applies the path security guard, uses the typed prepared handoff, and preserves execution-history recording.

Effectful Orchestrator intents are denied without a final RouteDecision or with the wrong work-evidence scope. Existing safe-I/O and SafePipeline controls remain in place; the handler migration does not grant additional execution authority.

## 8. Repository-wide caller graph

The caller-graph test scans active Python source across the repository root, including the active package, entry points, and any plugin/source directories. It separates the retained `lab_v4/` historical snapshot and confirms that the active entrypoint (`run.py` → `lab_v4_dev.core.agent.Agent`) and active source do not import or dispatch into it. The old tree is isolated reference material, not a competing runtime path. The 2026-11-15 correction also removes the legacy no-RouteDecision selection branch from `ConversationManager._dispatch()`; direct calls without a finalized route now fail closed. The raw `EventLoop.submit()` parser path was also removed, and `tick()` rejects any queued item that is not a `PreparedExecutionRequest`.

Verified active call paths:

| Caller / boundary | Verified behavior |
|---|---|
| `core/agent.py` | Enters through `ConversationManager.process()`. |
| `conversation/conversation_manager.py` | Sole active caller of `Orchestrator.handle()`. |
| `core/task_chain.py` | Calls `ConversationManager.process_execution_step()`; it does not call Orchestrator directly. |
| `core/guard.py` | Compatibility adapter delegates to ConversationManager; it has no gateway or direct Orchestrator call. |
| `core/orchestrator.py` | Validates the final RouteDecision, delegates once to `route_request()`, and defines the PreparedExecutionRequest handoff capability. |
| `core/orchestrator_handlers/dispatch.py` | Owns the response-cache gate, unique handler registry dispatch, and explicit unsupported result. |
| `loop/event_loop.py` | Exposes only typed `submit_prepared(PreparedExecutionRequest)`; the raw `submit()` and parser/clarifier/decomposer execution path were removed. |

The prepared execution handoff is active for `RUN_SCRIPT`: `HandlerServices` exposes a narrowly scoped bound capability, the registered handler supplies a fixed `run_command` execution specification plus the final RouteDecision, and `Orchestrator._submit_prepared_execution()` submits the typed request to `EventLoop.submit_prepared()`. The raw `EventLoop.submit()` parser path remains defined for compatibility but has no active runtime caller.

The scan also identifies Guard's dynamic `getattr(manager, "process")` delegation. Test modules may call Orchestrator directly for unit-level coverage; the active runtime scan found no additional direct callers.

## 9. Historical CI evidence and current verification status

GitHub Actions run `43568184890`, head SHA `4b76e484f9e7ccc1324dba6ba0ef7a3ee0acbb82`:

- Focused dialogue regressions: **484 passed**.
- Full-suite advisory job: **1,116 passed**.
- Failed tests: **0**.
- The job logs, not only the overall workflow conclusion, were inspected.

The full suite includes the ownership, route authorization, repository-wide active-source provider-call inventory, deep immutability, repository-wide active-source caller graph, effect parity, exact legacy branch parity, response-cache ordering, both FILE_IMPACT mode tests, prepared-execution route binding, prepared EventLoop caller wiring, fail-closed profile/impact policy, and repair-selection persistence.

Post-audit commits on 2026-11-15 remove the legacy ConversationManager dispatch fallback, register the 13 provider-backed intents under the same duplicate-safe registry, and remove the secondary provider branch from Orchestrator. The corresponding focused tests were updated. **No CI result for these post-audit commits is recorded yet; this document does not claim those changes passed.**

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
| 10 — Legacy Caller Migration | Complete for the active runtime call graph, including the `RUN_SCRIPT` → prepared EventLoop path; the raw `EventLoop.submit()` and `_process()` parser path were removed; only the typed `submit_prepared()` handoff remains |
| 11 — Final Parity Verification | Complete at the audited code HEAD |
| 12 — Legacy Route Removal | The active 3,000-line intent switch had already been replaced by the compact dispatch boundary before this final audit; this session performed no further legacy-tree deletion. The separate `lab_v4/` tree remains retained. |

Out of scope and not claimed as complete: APK packaging/build, UI work, API work, a ConversationManager/EventLoop/SafePipeline rewrite, or deletion of the retained `lab_v4/` legacy tree.

## 11. Final conclusion

The Orchestrator decomposition is verified against the baseline branch-key inventory, route/evidence/provider authorization boundaries, effectful-handler parity, and the active runtime caller graph. The focused and full CI suites pass at the audited implementation HEAD.

The remaining documented compatibility boundary is the mutable operational ContextStore reference inside HandlerFacade. The prepared handoff is no longer dormant: it is route-bound and exercised by the active `RUN_SCRIPT` handler. The legacy raw EventLoop submission API and the separate `lab_v4/` tree remain retained because no further deletion is required to satisfy the active caller contract.
