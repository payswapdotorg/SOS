"""``services.api`` — the FastAPI control-plane adapter (PUB-01).

Import bootstrap: make ``src`` (the immutable ``sos`` package) and the
repository root importable regardless of how the process was started
(uvicorn from repo root, pytest via ``pythonpath = ["src"]``, or direct
module execution). Idempotent; runs before any submodule import.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _entry in (str(_REPO_ROOT / "src"), str(_REPO_ROOT)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)
