"""
Order risk analyzer — the core analysis pipeline.

Exports four standalone functions (as required by spec):

    extract_json_from_text()   — robust JSON extraction from LLM output
    validate_agent_output()    — clamp / repair invalid or missing fields
    fallback_analysis()        — deterministic rule-based fallback
    analyze_order()            — full pipeline: context → LLM → parse → validate → save

Also keeps DeepSeekAgent as a thin wrapper for backward compatibility.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.agent.base import LLMClient, AgentAnalysisResult
from app.agent.mock_llm import MockLLMAgent
from app.agent.prompts import SYSTEM_PROMPT, build_user_prompt
from app.ontology.models import (
    Supplier,
    PurchaseOrder,
    RiskSignal,
    PolicyChunk,
    AgentRun,
)

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

VALID_RISK_LEVELS = frozenset({"low", "medium", "high", "critical"})
VALID_ACTIONS = frozenset({"approve_order", "reject_order", "escalate_order", "freeze_order"})


# ═══════════════════════════════════════════════════════════════════════════════
# 1. extract_json_from_text
# ═══════════════════════════════════════════════════════════════════════════════

def extract_json_from_text(text: str) -> Dict[str, Any]:
    """Extract a JSON object from potentially noisy LLM output.

    Tries, in order:
    1. Parse the whole text as JSON.
    2. Extract from ```json ... ``` code fence.
    3. Extract from ``` ... ``` code fence.
    4. Find the first { ... } span and parse it.

    Parameters
    ----------
    text : str
        Raw LLM response text.

    Returns
    -------
    dict
        Parsed JSON object.

    Raises
    ------
    ValueError
        If no parseable JSON is found.
    """
    if not text or not text.strip():
        raise ValueError("Empty LLM response — nothing to parse")

    text = text.strip()

    # Attempt 1: direct JSON parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Attempt 2: extract from ```json ... ```
    if "```json" in text:
        try:
            start = text.index("```json") + 7
            end = text.index("```", start)
            inner = text[start:end].strip()
            return json.loads(inner)
        except (ValueError, json.JSONDecodeError):
            pass

    # Attempt 3: extract from ``` ... ```
    if "```" in text:
        try:
            start = text.index("```") + 3
            end = text.index("```", start)
            inner = text[start:end].strip()
            return json.loads(inner)
        except (ValueError, json.JSONDecodeError):
            pass

    # Attempt 4: find first { ... } pair
    try:
        brace_start = text.index("{")
        # Find the matching closing brace by counting nesting
        depth = 0
        brace_end = -1
        for i, ch in enumerate(text[brace_start:], start=brace_start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    brace_end = i
                    break
        if brace_end > brace_start:
            inner = text[brace_start:brace_end + 1]
            return json.loads(inner)
    except (ValueError, json.JSONDecodeError):
        pass

    raise ValueError(f"Cannot extract valid JSON from LLM response: {text[:200]}...")


# ═══════════════════════════════════════════════════════════════════════════════
# 2. validate_agent_output
# ═══════════════════════════════════════════════════════════════════════════════

def validate_agent_output(
    parsed: Dict[str, Any],
    context: Dict[str, Any],
) -> Dict[str, Any]:
    """Validate and normalize a parsed LLM output dict.

    Applies safe defaults and clamps illegal values:

    - ``risk_level`` → clamp to {low, medium, high, critical}, default "medium"
    - ``suggested_action`` → clamp to 4 allowed actions, default "escalate_order"
    - ``reason`` → ensure non-empty string
    - ``confidence`` → clamp to [0.0, 1.0], default 0.5
    - ``evidence_ids`` → filter to only IDs present in context; if empty,
      auto-populate with all risk_xxx and policy_xxx from context

    Parameters
    ----------
    parsed : dict
        Raw parsed output from the LLM.
    context : dict
        The order analysis context (used to validate evidence_ids).

    Returns
    -------
    dict
        Cleaned and validated output dict with keys:
        ``risk_level``, ``action``, ``reason``, ``evidence_ids``, ``confidence``.
    """
    out: Dict[str, Any] = {}

    # ── risk_level ──────────────────────────────────────────────────────
    rl = str(parsed.get("risk_level", "medium")).lower().strip()
    out["risk_level"] = rl if rl in VALID_RISK_LEVELS else "medium"

    # ── suggested_action ────────────────────────────────────────────────
    action = str(parsed.get("suggested_action", parsed.get("action", "escalate_order"))).lower().strip()
    # Normalize shorthand: "escalate" → "escalate_order"
    if not action.endswith("_order") and action in {"approve", "reject", "escalate", "freeze"}:
        action = f"{action}_order"
    out["action"] = action if action in VALID_ACTIONS else "escalate_order"

    # ── reason ──────────────────────────────────────────────────────────
    reason = str(parsed.get("reason", "")).strip()
    out["reason"] = reason if reason else "No reason provided by agent"

    # ── confidence ──────────────────────────────────────────────────────
    try:
        conf = float(parsed.get("confidence", 0.5))
    except (TypeError, ValueError):
        conf = 0.5
    out["confidence"] = max(0.0, min(1.0, conf))

    # ── evidence_ids ────────────────────────────────────────────────────
    valid_ids = _collect_valid_ids(context)
    raw_evidence = parsed.get("evidence_ids", [])
    if not isinstance(raw_evidence, list):
        raw_evidence = []

    filtered = [eid for eid in raw_evidence if eid in valid_ids]

    # Auto-populate if empty: include all risk_xxx and policy_xxx from context
    if not filtered:
        auto_ids: List[str] = []
        for prefix in ("risk_", "policy_"):
            for eid in valid_ids:
                if eid.startswith(prefix):
                    auto_ids.append(eid)
        filtered = sorted(auto_ids)

    out["evidence_ids"] = filtered

    return out


def _collect_valid_ids(context: Dict[str, Any]) -> set:
    """Collect all valid evidence IDs from the context dict."""
    valid: set = set()
    for key in ("risk_signals", "policies", "agent_runs"):
        for item in context.get(key, []):
            if isinstance(item, dict) and "id" in item:
                valid.add(item["id"])
    return valid


# ═══════════════════════════════════════════════════════════════════════════════
# 3. fallback_analysis
# ═══════════════════════════════════════════════════════════════════════════════

def fallback_analysis(context: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic rule-based fallback when the LLM is unavailable or fails.

    Rules (in priority order):
    1. Supplier is blacklisted → ``freeze_order`` / ``critical``
    2. Any risk signal has ``signal_type == "blacklisted_supplier"`` → ``freeze_order`` / ``critical``
    3. Any risk signal has severity ``critical`` → ``freeze_order`` / ``critical``
    4. Any risk signal has ``signal_type == "missing_document"`` → ``reject_order`` / ``high``
    5. Order amount > 100,000 or ``high_amount`` signal → ``escalate_order`` / ``high``
    6. Otherwise → ``approve_order`` / ``low``

    Parameters
    ----------
    context : dict
        Order analysis context dict.

    Returns
    -------
    dict
        Fallback analysis result with keys:
        ``risk_level``, ``action``, ``reason``, ``evidence_ids``, ``confidence``.
    """
    supplier = context.get("supplier") or {}
    order = context.get("order") or {}
    risks: List[Dict[str, Any]] = context.get("risk_signals", [])
    policies: List[Dict[str, Any]] = context.get("policies", [])

    # Collect all evidence IDs
    evidence: List[str] = []
    for r in risks:
        rid = r.get("id", "")
        if rid:
            evidence.append(rid)
    for p in policies:
        pid = p.get("id", "")
        if pid:
            evidence.append(pid)

    # ── Rule 1: supplier blacklisted ──────────────────────────────────
    supplier_status = str(supplier.get("status", "")).lower()
    if supplier_status == "blacklisted":
        return {
            "risk_level": "critical",
            "action": "freeze_order",
            "reason": (
                f"供应商 {supplier.get('name', '?')} 已被列入黑名单，"
                f"订单 {order.get('id', '?')} 必须立即冻结。"
            ),
            "evidence_ids": evidence,
            "confidence": 0.95,
        }

    # ── Rule 2: blacklisted_supplier risk signal ──────────────────────
    for r in risks:
        if str(r.get("signal_type", "")).lower() == "blacklisted_supplier":
            return {
                "risk_level": "critical",
                "action": "freeze_order",
                "reason": (
                    f"检测到黑名单供应商风险信号 ({r.get('id')})，"
                    f"订单 {order.get('id', '?')} 必须冻结。"
                ),
                "evidence_ids": evidence,
                "confidence": 0.95,
            }

    # ── Rule 3: critical severity ─────────────────────────────────────
    for r in risks:
        if str(r.get("severity", "")).lower() == "critical":
            return {
                "risk_level": "critical",
                "action": "freeze_order",
                "reason": (
                    f"检测到严重风险信号 ({r.get('id')}): "
                    f"{r.get('description', r.get('signal_type', ''))}，"
                    f"订单 {order.get('id', '?')} 必须冻结。"
                ),
                "evidence_ids": evidence,
                "confidence": 0.90,
            }

    # ── Rule 4: missing_document ──────────────────────────────────────
    for r in risks:
        if str(r.get("signal_type", "")).lower() == "missing_document":
            return {
                "risk_level": "high",
                "action": "reject_order",
                "reason": (
                    f"供应商资质文件缺失 ({r.get('id')})，"
                    f"订单 {order.get('id', '?')} 应予拒绝或要求补交材料。"
                ),
                "evidence_ids": evidence,
                "confidence": 0.85,
            }

    # ── Rule 5: amount > 100k or high_amount signal ───────────────────
    amount = 0.0
    try:
        amount = float(order.get("amount", 0))
    except (TypeError, ValueError):
        pass

    if amount > 100_000:
        return {
            "risk_level": "high",
            "action": "escalate_order",
            "reason": (
                f"订单金额 {amount:,.0f} 元，超过 100,000 元升级审批阈值，"
                f"需要升级审批。"
            ),
            "evidence_ids": evidence,
            "confidence": 0.85,
        }

    for r in risks:
        if str(r.get("signal_type", "")).lower() == "high_amount":
            return {
                "risk_level": "high",
                "action": "escalate_order",
                "reason": (
                    f"检测到高金额风险信号 ({r.get('id')})，"
                    f"订单 {order.get('id', '?')} 需要升级审批。"
                ),
                "evidence_ids": evidence,
                "confidence": 0.85,
            }

    # ── Rule 6: default approve ───────────────────────────────────────
    return {
        "risk_level": "low",
        "action": "approve_order",
        "reason": (
            f"订单 {order.get('id', '?')} 风险较低，材料完整，建议直接批准。"
        ),
        "evidence_ids": evidence,
        "confidence": 0.80,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 4. analyze_order
# ═══════════════════════════════════════════════════════════════════════════════

def analyze_order(
    db: Session,
    order_id: str,
    llm_client: Optional[LLMClient] = None,
) -> AgentRun:
    """Run the full analysis pipeline on a purchase order.

    Pipeline:
    1. Load order + supplier + risk signals + policies from DB
    2. Build system + user prompts
    3. Call LLM via ``llm_client.generate()``
    4. Extract JSON from LLM response via :func:`extract_json_from_text`
    5. Validate & normalize via :func:`validate_agent_output`
    6. If any step fails → :func:`fallback_analysis`
    7. Persist the result as an ``AgentRun`` record (flushed, not committed)
    8. Return the ``AgentRun``

    **This function does NOT modify PurchaseOrder.status.**

    Parameters
    ----------
    db : Session
        Active database session.
    order_id : str
        The PurchaseOrder ID to analyze.
    llm_client : LLMClient or None
        The LLM client to use.  If None or if the call fails, fallback is used.

    Returns
    -------
    AgentRun
        The persisted AgentRun record (flushed, not committed).

    Raises
    ------
    ValueError
        If the order does not exist.
    """
    # ── 1. Build context ─────────────────────────────────────────────────
    context = _build_analysis_context(db, order_id)

    status: str = "success"
    error_message: Optional[str] = None
    raw_output: str = ""
    result: Dict[str, Any]

    # ── 2. Try LLM path ──────────────────────────────────────────────────
    if llm_client is not None:
        try:
            system_prompt = SYSTEM_PROMPT
            user_prompt = build_user_prompt(context)
            raw_output = llm_client.generate(system_prompt, user_prompt)
            parsed = extract_json_from_text(raw_output)
            result = validate_agent_output(parsed, context)
            logger.info(
                "LLM analysis succeeded for order '%s': action=%s risk=%s confidence=%s",
                order_id, result["action"], result["risk_level"], result["confidence"],
            )
        except Exception as exc:
            logger.warning(
                "LLM analysis failed for order '%s': %s — using fallback",
                order_id, exc,
            )
            status = "fallback"
            error_message = str(exc)
            raw_output = ""
            result = fallback_analysis(context)
    else:
        # No LLM client provided → go straight to fallback
        status = "fallback"
        error_message = "No LLM client configured"
        result = fallback_analysis(context)

    # ── 3. Persist AgentRun ──────────────────────────────────────────────
    agent_run = _save_agent_run(
        db=db,
        order_id=order_id,
        risk_level=result["risk_level"],
        suggested_action=result["action"],
        reason=result["reason"],
        evidence_ids=result["evidence_ids"],
        confidence=result["confidence"],
        raw_output=raw_output,
        status=status,
        error_message=error_message,
    )

    logger.info(
        "AgentRun saved: id=%s order=%s action=%s status=%s",
        agent_run.id, order_id, agent_run.suggested_action, agent_run.status,
    )

    return agent_run


# ═══════════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _build_analysis_context(db: Session, order_id: str) -> Dict[str, Any]:
    """Build the analysis context dict from the database.

    Raises ValueError if the order is not found.
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

    # Prior agent runs for historical context (latest 3)
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
        } if supplier else {},
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


def _save_agent_run(
    db: Session,
    *,
    order_id: str,
    risk_level: str,
    suggested_action: str,
    reason: str,
    evidence_ids: List[str],
    confidence: float,
    raw_output: str,
    status: str,
    error_message: Optional[str],
) -> AgentRun:
    """Persist an AgentRun record (flush, don't commit)."""
    import uuid

    run_id = f"agent_run_{uuid.uuid4().hex[:8]}"

    agent_run = AgentRun(
        id=run_id,
        order_id=order_id,
        risk_level=risk_level,
        suggested_action=suggested_action,
        reason=reason,
        evidence_ids=json.dumps(evidence_ids, ensure_ascii=False) if evidence_ids else None,
        confidence=confidence,
        raw_output=raw_output,
        status=status,
        error_message=error_message,
    )

    db.add(agent_run)
    db.flush()
    return agent_run


# ═══════════════════════════════════════════════════════════════════════════════
# DeepSeekAgent — backward-compatible wrapper
# ═══════════════════════════════════════════════════════════════════════════════

from app.agent.base import BaseAgent


class DeepSeekAgent(BaseAgent):
    """Backward-compatible DeepSeek agent that wraps :func:`analyze_order`.

    This class exists so existing code (e.g., ``run_agent_analysis`` in
    the service layer) continues to work.  Prefer :func:`analyze_order`
    for new code.
    """

    ACTOR = "deepseek_agent"

    def __init__(self, timeout: float = 30.0, max_retries: int = 1) -> None:
        from app.agent.deepseek_llm import DeepSeekLLMClient
        self._llm = DeepSeekLLMClient(timeout=timeout, max_retries=max_retries)

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Implement BaseContract._call_llm."""
        return self._llm.generate(system_prompt, user_prompt)

    # analyze() is inherited from BaseAgent and uses _call_llm() + _parse_response()
    # + _validate_result() + _fallback_result() from the parent class.
    # This works identically to the old behavior.
