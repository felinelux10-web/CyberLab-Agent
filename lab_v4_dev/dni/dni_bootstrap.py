"""
DNI Bootstrap

Temporary bootstrap module.

Current responsibility:
- Verify that the complete DNI foundation can be created.

No integration with Agent or Orchestrator yet.
"""

from lab_v4_dev.dni.dni_facade import DNIFacade


def initialize():
    return DNIFacade()
