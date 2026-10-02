"""Execution substrate adapters (Public Deployment Overlay).

``demo.py`` implements the W11 ``ExecutionSubstrate`` provider port
(``sos.execution.ExecutionProviderPort``) by IMPORTING ``sos.execution``
types — never editing them. The Apify adapter arrives with PUB-08; this
registry is the single dispatch table the API wires at startup.
"""
from .demo import DemoProvider

__all__ = ["DemoProvider", "build_execution_registry"]
