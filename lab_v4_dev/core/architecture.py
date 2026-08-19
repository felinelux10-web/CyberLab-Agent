"""
CyberLab Agent — P00 Architecture Boundary Manifest

Descriptive architectural contract. No runtime routing is performed here.

Primary runtime:

run.py
 -> Agent.boot()
 -> Agent.run()
 -> ConversationManager.process()
 -> Orchestrator.handle()
 -> interpretation/context/policy/routing
 -> execution
 -> result
 -> Agent.run()
 -> DialogueMemory
 -> output

P00 boundaries:

INPUT              -> Request
DIALOGUE           -> ConversationManager
INTERPRETATION     -> Intent
CONTEXT            -> Context
ROUTING            -> RoutingDecision
ORCHESTRATION      -> Orchestrator
EXECUTION          -> existing executor/planner subsystems
RESULT             -> Result
PUBLIC OUTPUT      -> Response

Compatibility:
existing runtime dictionaries remain valid.
"""

ENTRY_POINTS = {
    "cli": "run.py:main",
    "agent": "lab_v4_dev.core.agent:Agent",
    "conversation": "lab_v4_dev.conversation.conversation_manager:ConversationManager",
    "orchestrator": "lab_v4_dev.core.orchestrator:Orchestrator",
}

PIPELINE = [
    "Request",
    "ConversationManager",
    "Intent",
    "Context",
    "RoutingDecision",
    "Orchestrator",
    "Execution",
    "Result",
    "Response",
]

LAYER_RULES = {
    "request": "input representation only",
    "conversation": "dialogue and mode coordination",
    "intent": "semantic interpretation only",
    "context": "operational and contextual state",
    "routing": "route selection",
    "orchestration": "cross-layer coordination",
    "planning": "plan construction",
    "execution": "approved operation execution",
    "memory": "persistence",
    "llm": "provider abstraction and model invocation",
    "response": "result/output representation",
}
