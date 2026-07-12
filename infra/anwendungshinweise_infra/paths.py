"""Gemeinsame Pfadkonstanten (Repository-Layout)."""

from __future__ import annotations

from pathlib import Path

# .../infra/anwendungshinweise_infra/paths.py -> Repository-Wurzel
REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = REPO_ROOT / "backend" / "src"
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"
