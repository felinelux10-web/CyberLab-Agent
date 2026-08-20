"""
P07 — Memory Layer

Canonical responsibilities:
    - session memory
    - task history
    - long-term lessons
    - persistence adapters

Explicitly OUT OF SCOPE:
    - conversational ContextStore
    - NLU entity context
    - runtime state
    - project knowledge
    - orchestration
    - routing decisions

P07 policy:
Memory implementations may remain internally separated,
but callers should consume memory through explicit contracts
rather than treating Memory as a generic state container.
"""
