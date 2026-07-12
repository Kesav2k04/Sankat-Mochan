"""Shared pytest setup: make the backend runtime modules (app, models, triage,
intelligence, …) importable from tests/, and force the no-LLM/no-DB code paths so
the suite runs identically on any machine (CI, laptop, the venue AI PC)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/ modules

# The suite must never depend on a live GenieX/Ollama or PostgreSQL.
for var in ("LLM_BASE_URL", "TAGS_LLM_BASE_URL", "DATABASE_URL",
            "SANKAT_DATABASE_REQUIRED"):
    os.environ.pop(var, None)
