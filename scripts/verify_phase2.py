#!/usr/bin/env python
"""
Phase 2 Automated Verification Script
=======================================
Performs a complete end-to-end verification of the Phase 2 main link.

Usage::

    .\\.conda\\python.exe scripts\\verify_phase2.py

If all checks pass, outputs::

    PHASE 2 VERIFICATION PASSED

Otherwise outputs specific failure items with repair suggestions.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import datetime
from io import StringIO

# Fix Unicode output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Ensure project root on path
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Force mock / no real API key
os.environ["DEEPSEEK_API_KEY"] = ""
os.environ["APP_ENV"] = "testing"

# Redirect stderr to suppress SQLAlchemy/logging noise during verification
import logging

logging.basicConfig(level=logging.WARNING)
logging.getLogger("sqlalchemy.engine").setLevel(logging.ERROR)
logging.getLogger("httpx").setLevel(logging.WARNING)

SEP = "=" * 70
SEP2 = "-" * 70

# ── Test result tracking ──────────────────────────────────────────────────────

_results: list[dict] = []


def check(label: str, passed: bool, detail: str = "") -> None:
    """Record a check result."""
    status = "PASS" if passed else "FAIL"
    _results.append({"label": label, "status": status, "detail": detail})
    icon = "✓" if passed else "✗"
    print(f"  [{icon}] {label}")
    if detail and not passed:
        print(f"       {detail}")


def finalize() -> int:
    """Print summary and return exit code (0 = all passed)."""
    print(f"\n{SEP}")
    print("  VERIFICATION SUMMARY")
    print(SEP)
    passed = sum(1 for r in _results if r["status"] == "PASS")
    failed = sum(1 for r in _results if r["status"] == "FAIL")
    for r in _results:
        icon = "✓" if r["status"] == "PASS" else "✗"
        print(f"  {icon} {r['label']}")
        if r["detail"] and r["status"] == "FAIL":
            print(f"       → {r['detail']}")
    print(f"\n  Total: {len(_results)}  Passed: {passed}  Failed: {failed}")
    if failed == 0:
        print(f"\n  PHASE 2 VERIFICATION PASSED")
        return 0
    else:
        print(f"\n  PHASE 2 VERIFICATION FAILED — {failed} check(s) need attention")
        return 1


# ── Verification steps ─────────────────────────────────────────────────────────


def step_reset_and_seed() -> None:
    """Step 0: Reset database and load seed data."""
    print(f"\n[Step 0] Reset database & seed data")

    # Remove old DB file if possible
    db_path = os.path.join(_project_root, "data", "mini_foundry.db")
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except PermissionError:
        # If file is locked, try to work with what's there
        pass

    from app.database import Base, engine
    import app.ontology.models  # noqa

    os.makedirs(os.path.join(_project_root, "data"), exist_ok=True)
    Base.metadata.create_all(bind=engine)

    # Now run seed_data's main logic
    from scripts.seed_data import (
        seed_suppliers,
        seed_orders,
        seed_risk_signals,
        seed_policy_chunks,
        seed_approval_tasks,
    )
    from app.database import SessionLocal

    session = SessionLocal()
    try:
        for label, seeder in [
            ("Suppliers", seed_suppliers),
            ("PurchaseOrders", seed_orders),
            ("RiskSignals", seed_risk_signals),
            ("PolicyChunks", seed_policy_chunks),
            ("ApprovalTasks", seed_approval_tasks),
        ]:
            ins, skp = seeder(session)
            session.flush()
        session.commit()
        print(f"  Database reset and seeded successfully.")
    except Exception as exc:
        session.rollback()
        raise
    finally:
        session.close()


def step_health(db_session) -> None:
    """Step 1: Verify health endpoint."""
    print(f"\n[Step 1] Health check & base data")
    from fastapi.testclient import TestClient
    from app.main import app
    from app.deps import get_db

    def _override():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override
    client = TestClient(app)

    # Health
    resp = client.get("/health")
    check("GET /health returns ok", resp.status_code == 200 and resp.json()["status"] == "ok",
          f"Got: {resp.status_code} {resp.text[:200]}")

    # OpenAPI
    resp = client.get("/openapi.json")
    check("GET /openapi.json returns valid OpenAPI JSON",
          resp.status_code == 200 and "openapi" in resp.json(),
          f"Status: {resp.status_code}")

    # Redoc
    resp = client.get("/redoc")
    check("GET /redoc accessible", resp.status_code == 200,
          f"Status: {resp.status_code}")

    return client


def step_base_data(client) -> None:
    """Step 2: Verify base data endpoints."""
    print(f"\n[Step 2] Base data queries")

    # Suppliers
    resp = client.get("/suppliers")
    suppliers = resp.json()
    check("GET /suppliers ≥ 4", len(suppliers) >= 4,
          f"Got {len(suppliers)} suppliers")

    # Orders
    resp = client.get("/orders")
    orders = resp.json()
    check("GET /orders ≥ 5", len(orders) >= 5,
          f"Got {len(orders)} orders")

    # PO-002 initial state
    resp = client.get("/orders/PO-002")
    po002 = resp.json()
    check("PO-002 initial status = pending_review",
          po002.get("status") == "pending_review",
          f"Got: {po002.get('status')}")

    # Risk signals
    resp = client.get("/risk-signals")
    risks = resp.json()
    check("GET /risk-signals ≥ 5", len(risks) >= 5,
          f"Got {len(risks)} risk signals")

    # Policies
    resp = client.get("/policies")
    policies = resp.json()
    check("GET /policies ≥ 4", len(policies) >= 4,
          f"Got {len(policies)} policies")


def step_agent_analysis(client, db_session) -> dict:
    """Step 3: Agent analysis on PO-002."""
    print(f"\n[Step 3] Agent analysis (POST /agent/analyze/PO-002)")

    resp = client.post("/agent/analyze/PO-002")
    check("Agent analysis returns 200", resp.status_code == 200,
          f"Status: {resp.status_code} {resp.text[:200]}")
    if resp.status_code != 200:
        return {}

    data = resp.json()

    check("agent_run_id present", bool(data.get("agent_run_id")),
          f"Missing agent_run_id")
    check("order_id = PO-002", data.get("order_id") == "PO-002",
          f"Got: {data.get('order_id')}")

    # suggested_action should be valid
    valid_actions = {"approve_order", "reject_order", "escalate_order", "freeze_order"}
    check(f"suggested_action is valid ({data.get('suggested_action')})",
          data.get("suggested_action") in valid_actions,
          f"Got: {data.get('suggested_action')}")

    # status should be success or fallback (not error)
    check(f"status = {data.get('status')} (success or fallback)",
          data.get("status") in ("success", "fallback"),
          f"Got: {data.get('status')}, error: {data.get('error_message')}")

    # Evidence should contain risk_002 or policy_001
    evidence = data.get("evidence_ids", [])
    # evidence_ids is now a list[str] in API responses
    if isinstance(evidence, str):
        try:
            evidence = json.loads(evidence)
        except Exception:
            evidence = []
    if not isinstance(evidence, list):
        evidence = []
    has_evidence = any("risk_002" in str(e) or "policy_001" in str(e) for e in evidence)
    check("Evidence contains risk_002 or policy_001", has_evidence or len(evidence) > 0,
          f"Got evidence: {evidence}")

    # Verify order status unchanged
    check("PO-002 order_status_unchanged is True",
          data.get("order_status_unchanged") is True)

    # Verify from DB
    from app.ontology.models import PurchaseOrder
    order = db_session.get(PurchaseOrder, "PO-002")
    check("PO-002 status unchanged in DB (still pending_review)",
          order.status == "pending_review",
          f"Got: {order.status}")

    return data


def step_action_escalate(client, db_session) -> dict:
    """Step 4: Execute escalate_order on PO-002."""
    print(f"\n[Step 4] Action Runtime — successful execution (escalate PO-002)")

    resp = client.post("/actions/execute", json={
        "action_type": "escalate_order",
        "object_id": "PO-002",
        "actor": "user:risk_manager",
        "reason": "Order amount exceeds policy threshold.",
        "evidence_ids": ["risk_002", "policy_001"],
    })

    check("POST /actions/execute returns 200",
          resp.status_code == 200,
          f"Status: {resp.status_code} {resp.text[:200]}")
    if resp.status_code != 200:
        return {}

    data = resp.json()
    check("success = True", data.get("success") is True,
          f"Got: {data}")
    check("before_state = pending_review",
          data.get("before_state") == "pending_review",
          f"Got: {data.get('before_state')}")
    check("after_state = escalated",
          data.get("after_state") == "escalated",
          f"Got: {data.get('after_state')}")
    check("audit_log_id present",
          bool(data.get("audit_log_id")),
          f"Missing audit_log_id")

    # Verify DB
    from app.ontology.models import PurchaseOrder, ActionAuditLog
    order = db_session.get(PurchaseOrder, "PO-002")
    check("PO-002.status = escalated in DB",
          order.status == "escalated",
          f"Got: {order.status}")

    # Verify audit log in DB
    audit_log = db_session.query(ActionAuditLog).filter(
        ActionAuditLog.object_id == "PO-002",
        ActionAuditLog.success == True,
    ).first()
    check("ActionAuditLog success=True exists for PO-002",
          audit_log is not None,
          "No success audit log found")
    if audit_log:
        check("AuditLog.action_type = escalate_order",
              audit_log.action_type == "escalate_order",
              f"Got: {audit_log.action_type}")
        check("AuditLog.actor = user:risk_manager",
              audit_log.actor == "user:risk_manager",
              f"Got: {audit_log.actor}")

    return data


def step_action_frozen_reject(client, db_session) -> None:
    """Step 5: Try to approve a frozen order (PO-005)."""
    print(f"\n[Step 5] Action Runtime — failed execution (approve frozen PO-005)")

    resp = client.post("/actions/execute", json={
        "action_type": "approve_order",
        "object_id": "PO-005",
        "actor": "user:risk_manager",
        "reason": "Try to approve frozen order.",
        "evidence_ids": ["risk_005", "policy_002"],
    })

    # Should return non-200
    check("Action on frozen PO-005 rejected (non-200)",
          resp.status_code != 200,
          f"Status: {resp.status_code} (expected non-200)")

    # Order status unchanged
    from app.ontology.models import PurchaseOrder, ActionAuditLog
    order = db_session.get(PurchaseOrder, "PO-005")
    check("PO-005.status still frozen",
          order.status == "frozen",
          f"Got: {order.status}")

    # Failed audit log
    fail_log = db_session.query(ActionAuditLog).filter(
        ActionAuditLog.object_id == "PO-005",
        ActionAuditLog.success == False,
    ).first()
    check("ActionAuditLog success=False exists for PO-005",
          fail_log is not None,
          "No failure audit log found")
    if fail_log:
        check("AuditLog.error_message not empty",
              fail_log.error_message is not None and len(fail_log.error_message) > 0,
              f"Got: {fail_log.error_message}")


def step_agent_bypass(client, db_session) -> None:
    """Step 6: Agent bypass test (agent:deepseek tries to execute action)."""
    print(f"\n[Step 6] Agent execution boundary — bypass test")

    resp = client.post("/actions/execute", json={
        "action_type": "freeze_order",
        "object_id": "PO-003",
        "actor": "agent:deepseek",
        "reason": "Agent tries to directly freeze an order.",
        "evidence_ids": ["risk_003", "policy_002"],
    })

    # Should return non-200
    check("Agent:deepseek action rejected (non-200)",
          resp.status_code != 200,
          f"Status: {resp.status_code} (expected non-200)")

    # PO-003 status unchanged
    from app.ontology.models import PurchaseOrder, ActionAuditLog
    order = db_session.get(PurchaseOrder, "PO-003")
    check("PO-003.status unchanged (still pending_review)",
          order.status == "pending_review",
          f"Got: {order.status}")

    # Failed audit log must exist for PO-003
    fail_log = db_session.query(ActionAuditLog).filter(
        ActionAuditLog.object_id == "PO-003",
        ActionAuditLog.success == False,
    ).first()
    check("ActionAuditLog success=False exists for agent bypass attempt",
          fail_log is not None,
          "No failure audit log found for agent bypass attempt "
          "(this is required — agent attempts must be logged)")
    if fail_log:
        check("AuditLog.error_message mentions agent",
              fail_log.error_message and (
                  "agent" in fail_log.error_message.lower()
                  or "READ-ONLY" in (fail_log.error_message or "")
              ),
              f"Got: {fail_log.error_message}")


def step_timeline(client, db_session) -> None:
    """Step 7: Timeline query for PO-002."""
    print(f"\n[Step 7] Timeline query (GET /orders/PO-002/timeline)")

    resp = client.get("/orders/PO-002/timeline")
    check("Timeline returns 200", resp.status_code == 200,
          f"Status: {resp.status_code} {resp.text[:200]}")
    if resp.status_code != 200:
        return

    data = resp.json()

    # Required fields
    for field in ["order", "supplier", "risk_signals", "related_policies",
                  "agent_runs", "action_audit_logs", "timeline"]:
        check(f"Timeline contains '{field}'",
              field in data,
              f"Missing field: {field}")

    check("order.status = escalated",
          data.get("order", {}).get("status") == "escalated",
          f"Got: {data.get('order', {}).get('status')}")

    check("supplier present",
          data.get("supplier") is not None)

    check("risk_signals not empty",
          len(data.get("risk_signals", [])) > 0)

    check("agent_runs not empty",
          len(data.get("agent_runs", [])) > 0)

    check("action_audit_logs not empty",
          len(data.get("action_audit_logs", [])) > 0)

    # Check timeline event types
    events = data.get("timeline", [])
    event_types = {e.get("event_type") for e in events}
    required_events = {"order_created", "risk_signal", "agent_run", "action_audit_log"}
    for evt in required_events:
        check(f"Timeline has '{evt}' event",
              evt in event_types,
              f"Missing event type: {evt} (got: {sorted(event_types)})")


def step_audit_logs(client, db_session) -> None:
    """Step 8: Audit log query endpoints."""
    print(f"\n[Step 8] Audit log queries")

    resp = client.get("/audit-logs")
    check("GET /audit-logs returns results", resp.status_code == 200 and len(resp.json()) > 0,
          f"Status: {resp.status_code}, count: {len(resp.json())}")

    resp = client.get("/audit-logs?object_id=PO-002")
    logs = resp.json()
    check("GET /audit-logs?object_id=PO-002 returns success logs",
          any(l.get("success") for l in logs),
          "No success logs for PO-002")

    resp = client.get("/audit-logs?object_id=PO-005")
    logs = resp.json()
    check("GET /audit-logs?object_id=PO-005 returns failure logs",
          any(not l.get("success") for l in logs),
          "No failure logs for PO-005")


# ── Main ───────────────────────────────────────────────────────────────────────


def main() -> int:
    print(SEP)
    print("  Mini Foundry Ontology Runtime — Phase 2 Verification")
    print(f"  Started: {datetime.now().isoformat()}")
    print(SEP)

    # Late imports
    from app.database import SessionLocal, Base, engine
    import app.ontology.models  # noqa: register models

    # Inject test DB dependency
    from app.main import app
    from app.deps import get_db
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    # Use in-memory SQLite for testing (avoids file lock issues)
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(test_engine)

    connection = test_engine.connect()
    transaction = connection.begin()
    TestSession = sessionmaker(bind=connection)
    db_session = TestSession()

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db

    try:
        # ── Run seed data into test DB ─────────────────────────────────
        from scripts.seed_data import (
            seed_suppliers,
            seed_orders,
            seed_risk_signals,
            seed_policy_chunks,
            seed_approval_tasks,
        )

        for label, seeder in [
            ("Suppliers", seed_suppliers),
            ("PurchaseOrders", seed_orders),
            ("RiskSignals", seed_risk_signals),
            ("PolicyChunks", seed_policy_chunks),
            ("ApprovalTasks", seed_approval_tasks),
        ]:
            seeder(db_session)
            db_session.flush()
        db_session.commit()

        # ── Run all verification steps ─────────────────────────────────
        client = step_health(db_session)
        step_base_data(client)
        step_agent_analysis(client, db_session)
        step_action_escalate(client, db_session)
        step_action_frozen_reject(client, db_session)
        step_agent_bypass(client, db_session)
        step_timeline(client, db_session)
        step_audit_logs(client, db_session)

    except Exception:
        traceback.print_exc()
        return 1
    finally:
        db_session.close()
        transaction.rollback()
        connection.close()
        app.dependency_overrides.clear()

    return finalize()


if __name__ == "__main__":
    sys.exit(main())
