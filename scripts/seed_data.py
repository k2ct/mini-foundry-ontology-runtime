"""
Seed data loader for Mini Foundry Ontology Runtime.

Reads JSON files from ``data/`` and inserts rows into the database.
Safe to run multiple times — existing records are skipped (upsert-by-id).

Usage (from project root)::

    python scripts\\seed_data.py

    # or, if conda activation is not available:
    .\\.conda\\python.exe scripts\\seed_data.py
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _ensure_project_root() -> None:
    """Change working directory to the project root (parent of scripts/)."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    os.chdir(project_root)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)


def _load_json(filename: str) -> List[Dict[str, Any]]:
    """Load a JSON array from data/<filename>."""
    path = os.path.join("data", filename)
    if not os.path.exists(path):
        print(f"[seed_data] WARNING: {path} not found — skipping.")
        return []
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON array.")
    return data


# ──────────────────────────────────────────────────────────────────────────────
# Per-entity seed helpers
# ──────────────────────────────────────────────────────────────────────────────


def _seed_entities(
    session: Any,
    model_cls: Any,
    records: List[Dict[str, Any]],
    label: str,
) -> Tuple[int, int]:
    """Generic upsert: insert if not exists, skip otherwise.

    Returns (inserted, skipped).
    """
    inserted = 0
    skipped = 0
    for rec in records:
        pk = rec.get("id")
        if pk is None:
            print(f"[seed_data] WARNING: record in {label} missing 'id' — skipped.")
            skipped += 1
            continue
        existing = session.get(model_cls, pk)
        if existing is not None:
            skipped += 1
            continue
        session.add(model_cls(**rec))
        inserted += 1
    return inserted, skipped


def seed_suppliers(session: Any) -> Tuple[int, int]:
    from app.ontology.models import Supplier

    records = _load_json("seed_suppliers.json")
    return _seed_entities(session, Supplier, records, "suppliers")


def seed_orders(session: Any) -> Tuple[int, int]:
    from app.ontology.models import PurchaseOrder

    records = _load_json("seed_orders.json")
    return _seed_entities(session, PurchaseOrder, records, "orders")


def seed_risk_signals(session: Any) -> Tuple[int, int]:
    from app.ontology.models import RiskSignal

    records = _load_json("seed_risk_signals.json")
    return _seed_entities(session, RiskSignal, records, "risk_signals")


def seed_policy_chunks(session: Any) -> Tuple[int, int]:
    from app.ontology.models import PolicyChunk

    records = _load_json("seed_policy_chunks.json")
    return _seed_entities(session, PolicyChunk, records, "policy_chunks")


def seed_approval_tasks(session: Any) -> Tuple[int, int]:
    """Create one pending approval task per order that is still pending_review."""
    from app.ontology.models import ApprovalTask, PurchaseOrder

    inserted = 0
    skipped = 0
    orders = session.query(PurchaseOrder).filter(
        PurchaseOrder.status.in_(["pending_review", "frozen"])
    ).all()
    for order in orders:
        task_id = f"task_{order.id}"
        existing = session.get(ApprovalTask, task_id)
        if existing is not None:
            skipped += 1
            continue
        session.add(
            ApprovalTask(
                id=task_id,
                order_id=order.id,
                status="open",
                assignee=None,
            )
        )
        inserted += 1
    return inserted, skipped


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────


def main() -> None:
    _ensure_project_root()

    # Late imports after path setup — SQLAlchemy needs the project on sys.path
    from app.database import SessionLocal

    # Import all models so table metadata is registered
    import app.ontology.models  # noqa: F401

    # Ensure data/ directory and database file exist
    data_dir = os.path.join(os.getcwd(), "data")
    os.makedirs(data_dir, exist_ok=True)

    from app.database import Base, engine

    Base.metadata.create_all(bind=engine)

    session = SessionLocal()
    total_inserted = 0
    total_skipped = 0

    seeders = [
        ("Suppliers", seed_suppliers),
        ("PurchaseOrders", seed_orders),
        ("RiskSignals", seed_risk_signals),
        ("PolicyChunks", seed_policy_chunks),
        ("ApprovalTasks", seed_approval_tasks),
    ]

    try:
        for label, seeder in seeders:
            ins, skp = seeder(session)
            session.flush()  # make inserted rows visible to later queries
            total_inserted += ins
            total_skipped += skp
            print(f"[seed_data] {label:20s} -> inserted {ins:2d}, skipped {skp:2d}")

        session.commit()
        print("=" * 50)
        print(f"[seed_data] Total -> inserted {total_inserted}, skipped {total_skipped}")
        print("[seed_data] Seed data loaded successfully.")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
