# ADR: Frozen Route Decision Contract

- Status: Accepted for staged migration
- Scope: Routing, output-kind selection, evidence ownership, provider permission
- Issuer: ConversationManager (runtime authority)
- Contract: `lab_v4_dev.core.contracts.RouteDecision`

## Decision

A request is interpreted first. The ConversationManager then issues exactly one
frozen `RouteDecision`. Downstream components consume that decision and must
not independently reclassify the route, output kind, or selected session.

`SemanticRequest` remains an interpretation input. It is not an authoritative
routing decision. The legacy `RoutingDecision` remains available during
migration and must not be treated as equivalent to the new contract.

## Route values

- `L-SOCIAL`: local social/dialogue response
- `L-LIVE`: response grounded in the current live dialogue
- `L-SESSION`: response grounded in one explicitly selected saved session
- `L-FACT`: local/project knowledge retrieval
- `L-EXEC`: prepared operational execution
- `P-TOOL`: optional provider/tool continuation after local routing
- `CLARIFY`: request lacks information required for a safe decision
- `DENY`: request is not permitted

## Output-kind dispatch

| output_kind | Owner | Rendering contract |
|---|---|---|
| `none` | route handler | ordinary route response |
| `brief` | SummaryEngine | 2–4 sentences; no speaker pairs |
| `summary` | SummaryEngine | topic, themes, open points, stopping point; no transcript pairs |
| `report` | ReportEngine | topic, progression, points, decisions, open items, stopping point |
| `topic_summary` | SummaryEngine + topic filter | only evidence matching the selected topic |
| `transcript` | pair formatter | user/assistant pairs only |
| `list` | session index | saved-session index only |
| `continue_topic` | dialogue responder | continue the topic; do not substitute a summary |
| `capability` | local capability catalog | concise capability answer |

## Evidence ownership

- `none`: no conversation/project/work evidence is authorized.
- `live_exchanges`: current live dialogue only.
- `saved_session`: only the session identified by `session_ref`.
- `project_state`: project knowledge/state.
- `work_state`: active work/execution state.

Saved-session evidence requires an explicit `session_ref`. Saved sessions must
not be injected into a new live DialogueMemory.

## Provider boundary

`provider_allowed` is a permission bit, not a routing hint. Providers may
not change route, output kind, session reference, or evidence scope. Provider
calls must receive already-authorized structured evidence.

## Context lock

A context lock retains the selected session/topic/output contract over
compatible follow-ups. It may be released only by an explicit user request,
a confirmed topic switch, or an explicit session change.

## Migration rule

The first change defines and validates the contract without changing runtime
behavior. Subsequent stages add one ConversationManager issuance point and
migrate consumers incrementally. Each stage preserves existing behavior unless
the new contract explicitly specifies a correction. Live Arabic acceptance
scenarios are required before declaring the migration complete.
