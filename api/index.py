"""Vercel serverless entry — wraps Flask WSGI app."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

# Cloud defaults: no local Ollama on Vercel
os.environ.setdefault("OLLAMA_WARMUP", "0")
os.environ.setdefault("LOCAL_STREET_FIRST", "1")
os.environ.setdefault("RAG_ENABLED", "1")

from app import app  # noqa: E402
