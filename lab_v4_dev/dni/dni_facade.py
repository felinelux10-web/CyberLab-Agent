"""
DNI Facade

Single Entry Point for the DNI Layer.

Stage:
Foundation Integration

No execution logic.
No routing decisions.
No filtering decisions.
"""

from lab_v4_dev.dni.dni_kernel import DNIKernel
from lab_v4_dev.dni.dni_router import DNIRouter


class DNIFacade:

    def __init__(self):
        self.kernel = DNIKernel()
        self.router = DNIRouter()

    def status(self):
        return {
            "layer": "DNI",
            "kernel": self.kernel.status(),
            "router": self.router.status()
        }
