"""
Timeline / trace builder for purchase orders.

Collects every event related to an order into a single, chronological view:
    - Supplier details
    - Order details
    - Risk signals
    - Policy chunks (referenced in evidence_ids — or all if none referenced)
    - Agent runs (LLM analysis history)
    - Action audit logs (state change history)
    - Approval tasks

This is the "可追溯查询" (traceable query) component of the system.

Evidence tracing logic:
    1. Extract policy_xxx IDs from AgentRun.evidence_ids (JSON array string)
    2. Extract policy_xxx IDs from ActionAuditLog.evidence_ids (JSON array string)
    3. If any policy IDs are found, return only those PolicyChunks
    4. If none are found, return ALL PolicyChunks as a fallback
    5. JSON parse failures are silently tolerated — the timeline still builds
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session


def _safe_parse_json_array(raw: str | None) -> list[str]:
    """Parse a JSON-encoded string array, returning [] on any failure.

    This handles evidence_ids which are stored as ``'["id1","id2"]'``.
    """
    if not raw or not isinstance(raw, str):
        return []
    raw = raw.strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(item) for item in parsed if isinstance(item, (str, int))]
        return []
    except (json.JSONDecodeError, TypeError):
        return []


def build_timeline(
    db: Session,
    order_id: str,
) -> Optional[Dict[str, Any]]:
    """Build a complete audit timeline for a purchase order.

    The timeline includes every entity related to the order, plus a unified
    chronological ``timeline`` array of events suitable for rendering.

    Parameters
    ----------
    db : Session
        Active database session.
    order_id : str
        The PurchaseOrder ID to trace.

    Returns
    -------
    dict or None
        A complete timeline dict, or None if the order was not found.

    Timeline structure::

        {
            "order": { ... },
            "supplier": { ... },
            "risk_signals": [ ... ],
            "related_policies": [ ... ],
            "agent_runs": [ ... ],
            "action_audit_logs": [ ... ],
            "approval_tasks": [ ... ],
            "timeline": [
                {
                    "timestamp": "2026-06-15T10:00:00",
                    "event_type": "order_created | risk_signal | agent_run | action_audit_log | task_created",
                    "title": "订单创建",
                    "description": "...",
                    "ref_id": "PO-002",
                    "details": { ... }
                },
                ...
            ]
        }
    """
    from app.ontology.models import (
        Supplier,
        PurchaseOrder,
        RiskSignal,
        PolicyChunk,
        AgentRun,
        ActionAuditLog,
        ApprovalTask,
    )

    # ── 1. Fetch the order ──────────────────────────────────────────────────
    order = db.get(PurchaseOrder, order_id)
    if order is None:
        return None

    # ── 2. Fetch related entities ───────────────────────────────────────────
    supplier = db.get(Supplier, order.supplier_id)

    risk_signals = (
        db.query(RiskSignal)
        .filter(RiskSignal.order_id == order_id)
        .order_by(RiskSignal.created_at.asc())
        .all()
    )

    agent_runs = (
        db.query(AgentRun)
        .filter(AgentRun.order_id == order_id)
        .order_by(AgentRun.created_at.asc())
        .all()
    )

    audit_logs = (
        db.query(ActionAuditLog)
        .filter(ActionAuditLog.object_id == order_id)
        .order_by(ActionAuditLog.timestamp.asc())
        .all()
    )

    approval_tasks = (
        db.query(ApprovalTask)
        .filter(ApprovalTask.order_id == order_id)
        .order_by(ApprovalTask.created_at.asc())
        .all()
    )

    # ── 3. Collect policy IDs from evidence ─────────────────────────────────
    # Evidence IDs can appear in BOTH AgentRun.evidence_ids AND
    # ActionAuditLog.evidence_ids.  We collect from both sources.
    referenced_policy_ids: set[str] = set()

    # From agent runs
    for run in agent_runs:
        for eid in _safe_parse_json_array(run.evidence_ids):
            if eid.startswith("policy_"):
                referenced_policy_ids.add(eid)

    # From audit logs (this was missing before — important for traceability!)
    for log_entry in audit_logs:
        for eid in _safe_parse_json_array(log_entry.evidence_ids):
            if eid.startswith("policy_"):
                referenced_policy_ids.add(eid)

    # Fetch policies: referenced ones, or ALL as fallback
    if referenced_policy_ids:
        policies = (
            db.query(PolicyChunk)
            .filter(PolicyChunk.id.in_(referenced_policy_ids))
            .all()
        )
    else:
        # Fallback: return all available policies so the timeline is never empty
        policies = db.query(PolicyChunk).all()

    # ── 4. Serialize to dicts ───────────────────────────────────────────────

    def _serialize(obj: Any, fields: List[str]) -> Dict[str, Any]:
        """Serialize an ORM object to a dict of named fields."""
        result: Dict[str, Any] = {}
        for field in fields:
            val = getattr(obj, field, None)
            # Skip ORM relationship objects (they have __table__ or are types)
            if isinstance(val, type) or hasattr(val, "__table__"):
                continue
            if hasattr(val, "isoformat"):
                val = val.isoformat()
            result[field] = val
        return result

    order_dict = _serialize(order, [
        "id", "supplier_id", "amount", "currency", "description",
        "status", "created_at", "updated_at",
    ])

    supplier_dict: Optional[Dict[str, Any]] = None
    if supplier:
        supplier_dict = _serialize(supplier, [
            "id", "name", "risk_level", "status", "created_at",
        ])

    risk_dicts = [
        _serialize(r, ["id", "order_id", "signal_type", "severity", "description", "created_at"])
        for r in risk_signals
    ]

    policy_dicts = [
        _serialize(p, ["id", "title", "content", "policy_type", "created_at"])
        for p in policies
    ]

    agent_run_dicts = [
        _serialize(r, [
            "id", "order_id", "risk_level", "suggested_action", "reason",
            "evidence_ids", "confidence", "status", "error_message", "created_at",
        ])
        for r in agent_runs
    ]

    audit_log_dicts = [
        _serialize(l, [
            "id", "action_type", "object_id", "actor", "reason",
            "evidence_ids", "before_state", "after_state", "timestamp",
            "success", "error_message",
        ])
        for l in audit_logs
    ]

    task_dicts = [
        _serialize(t, ["id", "order_id", "status", "assignee", "created_at", "updated_at"])
        for t in approval_tasks
    ]

    # ── 5. Build unified chronological timeline ─────────────────────────────

    events: List[Dict[str, Any]] = []

    # ▶ order_created
    events.append({
        "timestamp": order.created_at.isoformat() if order.created_at else "",
        "event_type": "order_created",
        "title": "订单创建",
        "description": (
            f"采购订单 {order.id} 创建 — "
            f"金额 {order.amount:,.2f} {order.currency}"
            f"{' — ' + order.description if order.description else ''}"
        ),
        "ref_id": order.id,
        "details": {
            "supplier_id": order.supplier_id,
            "amount": order.amount,
            "currency": order.currency,
            "initial_status": order.status,
        },
    })

    # ▶ risk_signals
    for r in risk_signals:
        events.append({
            "timestamp": r.created_at.isoformat() if r.created_at else "",
            "event_type": "risk_signal",
            "title": f"风险信号: {r.signal_type}",
            "description": f"[{r.severity}] {r.signal_type}: {r.description or '（无描述）'}",
            "ref_id": r.id,
            "details": {
                "risk_signal_id": r.id,
                "signal_type": r.signal_type,
                "severity": r.severity,
            },
        })

    # ▶ agent_runs
    for r in agent_runs:
        events.append({
            "timestamp": r.created_at.isoformat() if r.created_at else "",
            "event_type": "agent_run",
            "title": f"Agent 分析: {r.suggested_action or 'unknown'}",
            "description": (
                f"Agent 建议 '{r.suggested_action}' "
                f"(风险等级: {r.risk_level}, 置信度: {r.confidence})"
            ),
            "ref_id": r.id,
            "details": {
                "agent_run_id": r.id,
                "suggested_action": r.suggested_action,
                "risk_level": r.risk_level,
                "confidence": r.confidence,
                "status": r.status,
                "reason": r.reason,
            },
        })

    # ▶ action_audit_logs
    for l in audit_logs:
        status_text = "成功" if l.success else "失败"
        events.append({
            "timestamp": l.timestamp.isoformat() if l.timestamp else "",
            "event_type": "action_audit_log",
            "title": f"Action 执行: {l.action_type}",
            "description": (
                f"[{status_text}] {l.action_type} by {l.actor}"
                f"{' — ' + l.reason if l.reason else ''}"
            ),
            "ref_id": l.id,
            "details": {
                "audit_log_id": l.id,
                "action_type": l.action_type,
                "actor": l.actor,
                "success": l.success,
                "before_state": l.before_state,
                "after_state": l.after_state,
                "error_message": l.error_message,
            },
        })

    # ▶ approval_tasks
    for t in approval_tasks:
        events.append({
            "timestamp": t.created_at.isoformat() if t.created_at else "",
            "event_type": "task_created",
            "title": f"审批任务: {t.id}",
            "description": (
                f"审批任务 '{t.id}' 创建 — 状态: {t.status}, "
                f"负责人: {t.assignee or '未分配'}"
            ),
            "ref_id": t.id,
            "details": {
                "task_id": t.id,
                "status": t.status,
                "assignee": t.assignee,
            },
        })

    # Sort events by timestamp
    events.sort(key=lambda e: e["timestamp"])

    # ── 6. Return the full picture ──────────────────────────────────────────

    return {
        "order": order_dict,
        "supplier": supplier_dict,
        "risk_signals": risk_dicts,
        "related_policies": policy_dicts,
        "agent_runs": agent_run_dicts,
        "action_audit_logs": audit_log_dicts,
        "approval_tasks": task_dicts,
        "timeline": events,
    }
