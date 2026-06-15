"""
Database reset script for Mini Foundry Ontology Runtime.

Deletes the existing ``data/mini_foundry.db`` file (if present), recreates
the ``data/`` directory, and rebuilds all 7 ontology tables from scratch.

**WARNING:** This is a destructive operation — all existing data is lost.

Usage (from project root)::

    python scripts\\reset_db.py

    # or, if conda activation is not available:
    .\\.conda\\python.exe scripts\\reset_db.py
"""

import os
import sys


def _ensure_project_root() -> None:
    """Change working directory to the project root (parent of scripts/)."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    os.chdir(project_root)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)


def main() -> None:
    _ensure_project_root()

    # ── late imports (after path setup) ──────────────────────────────────
    from app.database import Base, engine

    import app.ontology.models  # noqa: F401

    data_dir = os.path.join(os.getcwd(), "data")
    db_path = os.path.join(data_dir, "mini_foundry.db")

    # ── 1. remove existing database file ─────────────────────────────────
    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"[reset_db] Removed existing database → {db_path}")

    # ── 2. ensure data/ directory exists ─────────────────────────────────
    os.makedirs(data_dir, exist_ok=True)

    # ── 3. recreate all tables ───────────────────────────────────────────
    Base.metadata.create_all(bind=engine)

    print(f"[reset_db] Database reset successfully → {db_path}")


if __name__ == "__main__":
    main()
