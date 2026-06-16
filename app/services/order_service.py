"""
PurchaseOrder service — orchestrates business logic across multiple modules.

This service assembles analysis context, coordinates agent runs,
and provides high-level operations that the API layer consumes.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.agent.base import BaseAgent, AgentAnalysisResult
from app.ontology.models import (
    Supplier,
    PurchaseOrder,
    RiskSignal,
    PolicyChunk,
    AgentRun,
    ApprovalTask,
)


def build_analysis_context(
    db: Session,
    order_id: str,
) -> Dict[str, Any]:
    """Build the full analysis context dict for an order.

    Fetches the order, its supplier, risk signals, approval tasks,
    and all available policies.  Prior agent runs are also included
    so the agent has historical context.

    Parameters
    ----------
    db : Session
        Active database session.
    order_id : str
        The PurchaseOrder ID.

    Returns
    -------
    dict
        Context dict ready for ``BaseAgent.analyze()``.

    Raises
    ------
    ValueError
        If the order is not found.
    """
    order = db.get(PurchaseOrder, order_id)
    if order is None:
        raise ValueError(f"PurchaseOrder '{order_id}' not found")

    supplier = db.get(Supplier, order.supplier_id)

    risk_signals = (
        db.query(RiskSignal)
        .filter(RiskSignal.order_id == order_id)
        .all()
    )

    policies = db.query(PolicyChunk).all()

    approval_tasks = (
        db.query(ApprovalTask)
        .filter(ApprovalTask.order_id == order_id)
        .all()
    )

    prior_runs = (
        db.query(AgentRun)
        .filter(AgentRun.order_id == order_id)
        .order_by(AgentRun.created_at.desc())
        .limit(3)
        .all()
    )

    return {
        "order": {
            "id": order.id,
            "supplier_id": order.supplier_id,
            "amount": order.amount,
            "currency": order.currency,
            "description": order.description,
            "status": order.status,
            "created_at": order.created_at.isoformat() if order.created_at else "",
        },
        "supplier": {
            "id": supplier.id,
            "name": supplier.name,
            "risk_level": supplier.risk_level,
            "status": supplier.status,
        } if supplier else None,
        "risk_signals": [
            {
                "id": r.id,
                "signal_type": r.signal_type,
                "severity": r.severity,
                "description": r.description,
            }
            for r in risk_signals
        ],
        "policies": [
            {
                "id": p.id,
                "title": p.title,
                "content": p.content,
                "policy_type": p.policy_type,
            }
            for p in policies
        ],
        "approval_tasks": [
            {
                "id": t.id,
                "status": t.status,
                "assignee": t.assignee,
            }
            for t in approval_tasks
        ],
        "agent_runs": [
            {
                "id": r.id,
                "suggested_action": r.suggested_action,
                "risk_level": r.risk_level,
                "confidence": r.confidence,
            }
            for r in prior_runs
        ],
    }


def run_agent_analysis(
    db: Session,
    order_id: str,
    agent: BaseAgent,
) -> AgentRun:
    """Run a full agent analysis cycle on an order.

    1. Build analysis context from the database
    2. Call the agent's analyze() method
    3. Persist the result as an AgentRun record
    4. Return the AgentRun ORM object

    The AgentRun is flushed but NOT committed — the caller owns the transaction.

    Parameters
    ----------
    db : Session
        Active database session.
    order_id : str
        The PurchaseOrder ID to analyze.
    agent : BaseAgent
        The agent to use (DeepSeekAgent or MockLLMAgent).

    Returns
    -------
    AgentRun
        The persisted AgentRun record (flushed, not committed).
    """
    import json

    # 1. Build context
    context = build_analysis_context(db, order_id)

    # 2. Analyze
    result = agent.analyze(context)

    # 3. Generate a unique AgentRun ID
    import uuid
    run_id = f"agent_run_{uuid.uuid4().hex[:8]}"

    # 4. Persist as AgentRun
    agent_run = AgentRun(
        id=run_id,
        order_id=order_id,
        risk_level=result.risk_level,
        suggested_action=result.suggested_action,
        reason=result.reason,
        evidence_ids=json.dumps(result.evidence_ids, ensure_ascii=False) if result.evidence_ids else None,
        confidence=result.confidence,
        raw_output=result.raw_output,
        status=result.status,
        error_message=result.error_message,
    )

    db.add(agent_run)
    db.flush()

    return agent_run
