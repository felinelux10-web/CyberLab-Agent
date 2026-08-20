"""
Legacy compatibility wrapper.

P08:
The Intent layer is now provider-neutral.
Use lab_v4_dev.intent.llm_intent_resolver instead.

This module remains temporarily for backward compatibility.
"""

from lab_v4_dev.intent.llm_intent_resolver import resolve

__all__ = ["resolve"]
