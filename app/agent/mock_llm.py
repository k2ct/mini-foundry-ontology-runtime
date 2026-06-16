"""
Deterministic mock LLM for testing and fallback scenarios.

This mock analyzes order context using simple rule-based logic instead of
calling a real LLM.  It is useful for:

- Unit tests that shouldn't require API keys
- Development without a valid DEEPSEEK_API_KEY
- Fallback when the real LLM API is unavailable

Design: the mock uses the same ``BaseAgent`` interface as the real analyzer,
so callers don't need to know which implementation they're talking to.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from app.agent.base import BaseAgent, AgentAnalysisResult


class MockLLMAgent(BaseAgent):
    """Rule-based mock agent that deterministically analyzes order context.

    Rules (in priority order):
    1. If any risk signal has severity == "critical" — freeze_order
    2. If supplier is blacklisted — freeze_order
    3. If any risk signal has signal_type == "missing_document" — reject_order
    4. If order amount > 100000 — escalate_order
    5. Otherwise — approve_order
    """

    # Label used in audit logs
    ACTOR = "mock_agent"

    def __init__(self) -> None:
        self._call_count = 0

    # ── LLM call (no-op — we compute locally) ───────────────────────────────

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """The mock agent doesn't call an LLM — it computes the result locally.

        We return a JSON string for compatibility with the BaseAgent pipeline.
        The real decision is made in :meth:`analyze`, which we override.
        """
        self._call_count += 1
        return "{}"  # placeholder — not used because we override analyze()

    # ── full override ───────────────────────────────────────────────────────

    def analyze(self, context: Dict[str, Any]) -> AgentAnalysisResult:
        """Run deterministic rule-based analysis (no LLM call)."""
        order_id = context.get("order", {}).get("id", "unknown")
        risk_level, action, reason, evidence = self._apply_rules(context)

        result_dict = {
            "risk_level": risk_level,
            "action": action,
            "reason": reason,
            "evidence_ids": evidence,
            "confidence": 0.95,  # mock is "confident" in its rules
        }

        return AgentAnalysisResult(
            order_id=order_id,
            risk_level=result_dict["risk_level"],
            suggested_action=result_dict["action"],
            reason=result_dict["reason"],
            evidence_ids=result_dict["evidence_ids"],
            confidence=result_dict["confidence"],
            raw_output=json.dumps(result_dict, ensure_ascii=False, indent=2),
            status="success",
            error_message=None,
        )

    # ── rules engine ────────────────────────────────────────────────────────

    def _apply_rules(
        self, context: Dict[str, Any]
    ) -> tuple[str, str, str, list[str]]:
        """Apply deterministic rules and return (risk_level, action, reason, evidence_ids)."""
        order = context.get("order", {})
        supplier = context.get("supplier", {})
        risks = context.get("risk_signals", [])
        policies = context.get("policies", [])

        max_severity = "low"
        evidence: list[str] = []

        for r in risks:
            rid = r.get("id", "")
            sev = str(r.get("severity", "low")).lower()
            stype = str(r.get("signal_type", "")).lower()

            # Track max severity
            if sev == "critical" and max_severity != "critical":
                max_severity = "critical"
            elif sev == "high" and max_severity not in ("critical",):
                max_severity = "high"
            elif sev == "medium" and max_severity == "low":
                max_severity = "medium"

            if rid:
                evidence.append(rid)

        # Also add relevant policies to evidence
        for p in policies:
            evidence.append(p.get("id", ""))

        # ── Rule 1: critical risk → freeze ──────────────────────────
        if max_severity == "critical":
            return (
                "critical",
                "freeze_order",
                f"检测到严重风险信号，供应商 {supplier.get('name', '?')} "
                f"状态为 {supplier.get('status', '?')}，订单必须立即冻结。",
                evidence,
            )

        # ── Rule 2: blacklisted supplier → freeze ────────────────────
        if supplier.get("status") == "blacklisted":
            return (
                "critical",
                "freeze_order",
                f"供应商 {supplier.get('name', '?')} 已被列入黑名单，订单必须冻结。",
                evidence,
            )

        # ── Rule 3: missing document → reject ───────────────────────
        for r in risks:
            if str(r.get("signal_type", "")).lower() == "missing_document":
                return (
                    "high",
                    "reject_order",
                    f"供应商资质文件缺失，订单 {order.get('id')} 应予拒绝。",
                    evidence,
                )

        # ── Rule 4: amount > threshold → escalate ───────────────────
        amount = order.get("amount", 0)
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            amount = 0

        if amount > 100_000:
            return (
                "high",
                "escalate_order",
                f"订单金额 {amount:.0f} 元，超过 100000 元升级审批阈值，需要升级审批。",
                evidence,
            )

        # ── Rule 5: default → approve ───────────────────────────────
        return (
            "low",
            "approve_order",
            f"订单 {order.get('id')} 风险较低，材料完整，建议直接批准。",
            evidence,
        )
