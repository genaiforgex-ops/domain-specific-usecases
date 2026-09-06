"""ADK Web entry point — exposes the LegalOS root agent for ``adk web``.

Dev-only. Production chat still goes through FastAPI → orchestrator pipeline.

ADK Web only puts ``adk_web/`` on ``sys.path``, so we bootstrap the backend
root here so ``import app`` works without requiring ``PYTHONPATH``.
"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.orchestrator.agent import build_app, build_root_agent

root_agent = build_root_agent()
app = build_app()
