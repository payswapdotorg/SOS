"""Execution substrate adapters (Public Deployment Overlay).

``adapters/demo.py`` implements the W11 ``ExecutionSubstrate`` provider port
(``sos.execution.ExecutionProviderPort``) by IMPORTING ``sos.execution``
types — never editing them. The Apify adapter arrives with PUB-08; the
registry in ``adapters/__init__.py`` is the single dispatch table the API
wires at startup.
"""
