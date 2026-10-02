"""Provider seams for the SOS Public Deployment Overlay (PUB-01).

One subpackage per provider (``neon/``, ``upstash/``, ``r2/``, ``github/``),
each exposing ONE provider-neutral seam interface plus a LOCAL implementation
and a cloud implementation placeholder (public-deployment contract §B).

Semantic authority stays in ``src/sos``: these packages are transport and
mapping only — no SOS decision logic, no truth-state invention, no second
authority of any kind (contract §A.5).
"""
