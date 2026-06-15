"""
Database initialisation script for Mini Foundry Ontology Runtime.

Creates the ``data/`` directory (if missing) and all 7 ontology tables via
SQLAlchemy ``Base.metadata.create_all``.

Usage (from project root)::

    python scripts\\init_db.py

    # or, if conda activation is not available:
    .\\.conda\\python.exe scripts\\init_db.py
"""

import os
import sys


def _ensure_project_root() -> None:
    """Change working directory to the project root (parent of scripts/)."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    os.chdir(project_root)
    # Make sure the project root is on sys.path so ``app`` is importable.
    if project_root not in sys.path:
        sys.path.insert(0, project_root)


def main() -> None:
    _ensure_project_root()

    # ── late imports (after path setup) ──────────────────────────────────
    from app.database import Base, engine

    # Import ALL ontology models so they register their table metadata.
    import app.ontology.models  # noqa: F401

    # ── ensure data/ directory exists ────────────────────────────────────
    data_dir = os.path.join(os.getcwd(), "data")
    os.makedirs(data_dir, exist_ok=True)

    # ── create all tables ────────────────────────────────────────────────
    Base.metadata.create_all(bind=engine)

    db_path = os.path.join(data_dir, "mini_foundry.db")
    print(f"[init_db] Database initialised successfully → {db_path}")


if __name__ == "__main__":
    main()
