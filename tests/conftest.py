"""
Shared test fixtures for the Mini Foundry Ontology Action Runtime.

Uses an in-memory SQLite database so tests are fast and isolated.
No real DeepSeek API key is required — tests use MockLLMAgent.
"""

from __future__ import annotations

import os
import sys
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure the project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Force mock agent mode (no real API key)
os.environ["DEEPSEEK_API_KEY"] = ""
os.environ["APP_ENV"] = "testing"

from app.database import Base
from app.deps import get_db
from app.main import app
from app.ontology.models import (  # noqa: F401 — register all models
    Supplier,
    PurchaseOrder,
    RiskSignal,
    PolicyChunk,
    ApprovalTask,
    AgentRun,
    ActionAuditLog,
)


# ── Engine & Session ─────────────────────────────────────────────────────────

@pytest.fixture(scope="function")
def engine():
    """Create a fresh in-memory SQLite engine per test.

    Uses StaticPool so every connection shares the same in-memory database.
    Without this, SQLite :memory: creates a separate DB per connection.
    """
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture(scope="function")
def db_session(engine) -> Generator[Session, None, None]:
    """Create a fresh database session per test, with schema already created.

    Uses the same engine connection pool so it shares the in-memory database
    with the FastAPI dependency override.
    """
    connection = engine.connect()
    transaction = connection.begin()
    SessionLocal = sessionmaker(bind=connection)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


# ── FastAPI TestClient ───────────────────────────────────────────────────────

@pytest.fixture(scope="function")
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """Create a FastAPI TestClient with the test database session injected."""
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as tc:
        yield tc
    app.dependency_overrides.clear()


# ── Seed data helpers ────────────────────────────────────────────────────────

def seed_supplier(db: Session, **kwargs) -> Supplier:
    """Create and flush a supplier. Defaults are safe for testing."""
    defaults = {
        "id": "supplier_test",
        "name": "Test Supplier",
        "risk_level": "low",
        "status": "active",
    }
    defaults.update(kwargs)
    s = Supplier(**defaults)
    db.add(s)
    db.flush()
    return s


def seed_order(db: Session, **kwargs) -> PurchaseOrder:
    """Create and flush a purchase order. Defaults are safe for testing."""
    defaults = {
        "id": "PO-TEST",
        "supplier_id": "supplier_test",
        "amount": 50000.0,
        "currency": "CNY",
        "status": "pending_review",
    }
    defaults.update(kwargs)
    o = PurchaseOrder(**defaults)
    db.add(o)
    db.flush()
    return o


def seed_risk_signal(db: Session, **kwargs) -> RiskSignal:
    """Create and flush a risk signal."""
    defaults = {
        "id": "risk_test",
        "order_id": "PO-TEST",
        "signal_type": "low_amount",
        "severity": "low",
        "description": "Test risk signal",
    }
    defaults.update(kwargs)
    r = RiskSignal(**defaults)
    db.add(r)
    db.flush()
    return r


def seed_policy(db: Session, **kwargs) -> PolicyChunk:
    """Create and flush a policy chunk."""
    defaults = {
        "id": "policy_test",
        "title": "Test Policy",
        "content": "Test policy content for testing.",
        "policy_type": "approval_rule",
    }
    defaults.update(kwargs)
    p = PolicyChunk(**defaults)
    db.add(p)
    db.flush()
    return p


def seed_approval_task(db: Session, **kwargs) -> ApprovalTask:
    """Create and flush an approval task."""
    defaults = {
        "id": "task_test",
        "order_id": "PO-TEST",
        "status": "open",
        "assignee": "tester",
    }
    defaults.update(kwargs)
    t = ApprovalTask(**defaults)
    db.add(t)
    db.flush()
    return t


def seed_agent_run(db: Session, **kwargs) -> AgentRun:
    """Create and flush an agent run record."""
    defaults = {
        "id": "agent_run_test",
        "order_id": "PO-TEST",
        "risk_level": "low",
        "suggested_action": "approve_order",
        "reason": "Test agent run",
        "evidence_ids": '["policy_test"]',
        "confidence": 0.9,
        "status": "success",
    }
    defaults.update(kwargs)
    a = AgentRun(**defaults)
    db.add(a)
    db.flush()
    return a


def seed_full_context(db: Session) -> dict:
    """Seed a complete test context: supplier + order + risk + policy + task."""
    supplier = seed_supplier(db)
    order = seed_order(db, supplier_id=supplier.id)
    risk = seed_risk_signal(db, order_id=order.id)
    policy = seed_policy(db)
    task = seed_approval_task(db, order_id=order.id)
    return {
        "supplier": supplier,
        "order": order,
        "risk": risk,
        "policy": policy,
        "task": task,
    }
