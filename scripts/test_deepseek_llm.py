"""
DeepSeek LLM Connectivity Test

Tests that the real DeepSeek Chat Completions API is reachable,
that the ProcurementRiskAnalyzer can use it, and that fallback
still works correctly.

Usage:
    python scripts\\test_deepseek_llm.py

This script requires a valid DEEPSEEK_API_KEY in .env.
It does NOT depend on a running server — it uses an in-memory database.

Exit code 0 → connectivity test PASSED
Exit code 1 → connectivity test FAILED (but fallback still works)
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

# Project root is the parent of scripts/
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

# Load .env explicitly (in case the script is run standalone)
load_dotenv(ROOT / ".env")

from app.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
from app.agent.deepseek_llm import DeepSeekLLMClient, DeepSeekAPIError
from app.database import engine, SessionLocal
from app.ontology.models import Base


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def init_memory_db():
    """Create all tables in the in-memory database and return a session."""
    # Override: use in-memory SQLite to avoid touching the real DB
    import app.config as cfg
    original_url = cfg.DATABASE_URL
    cfg.DATABASE_URL = "sqlite://"
    # Force re-initialization
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    mem_engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=mem_engine)
    MemSession = sessionmaker(bind=mem_engine)
    return MemSession(), original_url


def seed_data(db):
    """Load seed data from JSON files into the in-memory DB."""
    from app.ontology.models import Supplier, PurchaseOrder, RiskSignal, PolicyChunk, ApprovalTask

    data_dir = ROOT / "data"
    count = 0

    # Suppliers
    with open(data_dir / "seed_suppliers.json", "r", encoding="utf-8") as f:
        suppliers = json.load(f)
    for s in suppliers:
        if not db.get(Supplier, s["id"]):
            db.add(Supplier(**s))
            count += 1

    # PurchaseOrders
    with open(data_dir / "seed_orders.json", "r", encoding="utf-8") as f:
        orders = json.load(f)
    for o in orders:
        if not db.get(PurchaseOrder, o["id"]):
            # Handle datetime fields
            from datetime import datetime
            o_copy = dict(o)
            for dt_field in ("created_at", "updated_at"):
                if dt_field in o_copy and o_copy[dt_field]:
                    o_copy[dt_field] = datetime.fromisoformat(o_copy[dt_field])
            db.add(PurchaseOrder(**o_copy))
            count += 1

    # RiskSignals
    with open(data_dir / "seed_risk_signals.json", "r", encoding="utf-8") as f:
        risks = json.load(f)
    for r in risks:
        if not db.get(RiskSignal, r["id"]):
            from datetime import datetime
            r_copy = dict(r)
            if "created_at" in r_copy and r_copy["created_at"]:
                r_copy["created_at"] = datetime.fromisoformat(r_copy["created_at"])
            db.add(RiskSignal(**r_copy))
            count += 1

    # PolicyChunks
    with open(data_dir / "seed_policy_chunks.json", "r", encoding="utf-8") as f:
        policies = json.load(f)
    for p in policies:
        if not db.get(PolicyChunk, p["id"]):
            db.add(PolicyChunk(**p))
            count += 1

    # ApprovalTasks — auto-create for pending orders
    for o in orders:
        task_id = f"task_{o['id']}"
        if not db.get(ApprovalTask, task_id):
            db.add(ApprovalTask(
                id=task_id,
                order_id=o["id"],
                status="open",
                assignee=None,
            ))
            count += 1

    db.commit()
    return count


# ──────────────────────────────────────────────────────────────────────────────
# Test 1: Minimal LLM call
# ──────────────────────────────────────────────────────────────────────────────


def _run_minimal_llm_call() -> tuple[bool, str]:
    """Send a minimal prompt to DeepSeek and return (success, response_text)."""
    print("\n" + "=" * 70)
    print("  Test 1: Minimal DeepSeek LLM call")
    print("=" * 70)

    if not DEEPSEEK_API_KEY:
        return False, "DEEPSEEK_API_KEY is not set — cannot test real LLM"

    print(f"  Base URL : {DEEPSEEK_BASE_URL}")
    print(f"  Model    : {DEEPSEEK_MODEL}")
    print(f"  API Key  : {DEEPSEEK_API_KEY[:12]}...{DEEPSEEK_API_KEY[-4:]}")
    print()

    client = DeepSeekLLMClient(timeout=30.0, max_retries=1)

    try:
        response = client.generate(
            system_prompt="You are a helpful assistant. Reply in JSON format only.",
            user_prompt='Reply with exactly: {"greeting":"hello","ready":true}',
        )
        print(f"  LLM raw response: {response[:500]}")
        return True, response
    except DeepSeekAPIError as exc:
        print(f"  ✗ DeepSeek API Error: {exc}")
        if exc.status_code:
            print(f"    HTTP status: {exc.status_code}")
        return False, str(exc)
    except Exception as exc:
        print(f"  ✗ Unexpected error: {exc}")
        traceback.print_exc()
        return False, str(exc)


# ──────────────────────────────────────────────────────────────────────────────
# Test 2: Full analyze_order pipeline
# ──────────────────────────────────────────────────────────────────────────────


def _run_analyze_order(db) -> tuple[bool, dict]:
    """Run the full analyze_order pipeline on PO-002."""
    print("\n" + "=" * 70)
    print("  Test 2: analyze_order( PO-002 ) with real DeepSeek LLM")
    print("=" * 70)

    from app.agent.analyzer import analyze_order

    # Seed data into the in-memory DB
    print("  Seeding in-memory database...")
    count = seed_data(db)
    print(f"  Seeded {count} records")

    # Create LLM client
    if not DEEPSEEK_API_KEY:
        print("  No API key — using fallback (llm_client=None)")
        llm_client = None
    else:
        llm_client = DeepSeekLLMClient(timeout=30.0, max_retries=1)
        print("  Using DeepSeekLLMClient")

    try:
        agent_run = analyze_order(db, "PO-002", llm_client=llm_client)
        db.commit()
    except Exception as exc:
        print(f"  ✗ analyze_order failed: {exc}")
        traceback.print_exc()
        return False, {"error": str(exc)}

    # Parse evidence_ids
    evidence_list = []
    if agent_run.evidence_ids:
        try:
            evidence_list = json.loads(agent_run.evidence_ids)
        except (json.JSONDecodeError, TypeError):
            pass

    result = {
        "agent_run_id": agent_run.id,
        "status": agent_run.status,
        "risk_level": agent_run.risk_level,
        "suggested_action": agent_run.suggested_action,
        "reason": agent_run.reason,
        "evidence_ids": evidence_list,
        "confidence": agent_run.confidence,
        "error_message": agent_run.error_message,
        "raw_output_preview": (agent_run.raw_output or "")[:300],
    }

    print(f"  Agent Run ID     : {result['agent_run_id']}")
    print(f"  Status           : {result['status']}")
    print(f"  Risk Level       : {result['risk_level']}")
    print(f"  Suggested Action : {result['suggested_action']}")
    print(f"  Confidence       : {result['confidence']}")
    print(f"  Evidence IDs     : {result['evidence_ids']}")
    print(f"  Reason           : {result['reason'][:200]}...")
    if result["status"] != "success":
        print(f"  Error Message    : {result['error_message']}")
    if result["raw_output_preview"]:
        print(f"  Raw Output       : {result['raw_output_preview']}...")

    return True, result


# ──────────────────────────────────────────────────────────────────────────────
# Test 3: Verify fallback still works
# ──────────────────────────────────────────────────────────────────────────────


def _run_fallback_works(db) -> bool:
    """Verify that fallback analysis still works when llm_client=None."""
    print("\n" + "=" * 70)
    print("  Test 3: Fallback still works (llm_client=None)")
    print("=" * 70)

    from app.agent.analyzer import analyze_order

    try:
        agent_run = analyze_order(db, "PO-001", llm_client=None)
        db.commit()
        is_fallback = agent_run.status == "fallback"
        print(f"  Status           : {agent_run.status}")
        print(f"  Suggested Action : {agent_run.suggested_action}")
        print(f"  Fallback works   : {is_fallback}")
        return is_fallback
    except Exception as exc:
        print(f"  ✗ Fallback test failed: {exc}")
        traceback.print_exc()
        return False


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────


def main() -> int:
    print("=" * 70)
    print("  Mini Foundry Ontology Runtime")
    print("  DeepSeek LLM Connectivity Test")
    print("=" * 70)

    # Check config
    print(f"\nConfiguration from .env:")
    print(f"  DEEPSEEK_API_KEY   : {'SET' if DEEPSEEK_API_KEY else 'NOT SET'}")
    print(f"  DEEPSEEK_BASE_URL  : {DEEPSEEK_BASE_URL}")
    print(f"  DEEPSEEK_MODEL     : {DEEPSEEK_MODEL}")

    # Initialize in-memory DB
    db, original_url = init_memory_db()

    llm_success = False
    analyze_success = False
    fallback_ok = False
    using_real_llm = False

    try:
        # ── Test 1: Minimal LLM call ──
        llm_success, llm_response = _run_minimal_llm_call()

        # ── Test 2: Full analyze_order ──
        analyze_success, analyze_result = _run_analyze_order(db)

        if analyze_success:
            using_real_llm = analyze_result["status"] == "success"

        # ── Test 3: Fallback ──
        fallback_ok = _run_fallback_works(db)

    finally:
        db.close()

    # ── Summary ───────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("  RESULTS")
    print("=" * 70)
    print(f"  Test 1 (Minimal LLM call)     : {'PASS' if llm_success else 'FAIL'}")
    print(f"  Test 2 (analyze_order PO-002) : {'PASS' if analyze_success else 'FAIL'}")
    print(f"  Test 3 (Fallback works)       : {'PASS' if fallback_ok else 'FAIL'}")
    print(f"  Using real LLM (not fallback) : {using_real_llm}")

    # Overall
    if llm_success and analyze_success and fallback_ok:
        print("\n  DEEPSEEK CONNECTIVITY TEST PASSED")
        if using_real_llm:
            print("  Agent status: success (real LLM)")
        else:
            print("  Agent status: fallback (LLM called but analyzer fell back)")
        return 0
    else:
        print("\n  DEEPSEEK CONNECTIVITY TEST FAILED")
        if not llm_success:
            print(f"  Reason: Minimal LLM call failed — {llm_response[:200]}")
        if not analyze_success:
            print("  Reason: analyze_order pipeline failed")
        print(f"  Fallback still works: {fallback_ok}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
