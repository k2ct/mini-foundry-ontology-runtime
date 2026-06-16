"""
Abstract base class for LLM agents.

Defines the contract that every agent implementation must fulfill.
The base agent is order-analysis-specific — it takes a PurchaseOrder ID,
queries related context from the database, calls an LLM, and returns
a structured AgentRun record.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ── LLM Client abstraction ───────────────────────────────────────────────────

class LLMClient(ABC):
    """Minimal abstraction for an LLM chat-completions client.

    Implementations only need to provide ``generate()`` — the agent
    layer handles prompt construction, parsing, validation, and fallback.
    """

    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Send prompts to the LLM and return the raw text response.

        Parameters
        ----------
        system_prompt : str
            System-level instruction (role, rules, output format).
        user_prompt : str
            The concrete analysis request with order context.

        Returns
        -------
        str
            Raw LLM response text (to be parsed by the caller).

        Raises
        ------
        Exception
            Implementations should raise on network errors, timeouts,
            authentication failures, etc.  The agent layer catches these
            and triggers fallback analysis.
        """
        ...


# ── Agent Analysis Result ────────────────────────────────────────────────────

@dataclass
class AgentAnalysisResult:
    """Structured output from an agent analysis run.

    This is a plain-data DTO — it carries the agent's *suggestion* only.
    It does NOT modify any business object.  That is the Action Runtime's job.
    """

    order_id: str
    risk_level: str                          # low | medium | high | critical
    suggested_action: str                    # approve_order | reject_order | escalate_order | freeze_order
    reason: str                              # human-readable explanation
    evidence_ids: List[str] = field(default_factory=list)  # references to RiskSignal / PolicyChunk / AgentRun IDs
    confidence: float = 0.0                  # 0.0 – 1.0
    raw_output: str = ""                     # raw LLM response for audit
    status: str = "success"                  # success | fallback | error
    error_message: Optional[str] = None


class BaseAgent(ABC):
    """Abstract agent for purchase order risk analysis.

    Subclasses must implement ``_call_llm`` — the rest of the workflow
    (fetch context → build prompt → parse response → validate) is shared.
    """

    # ── valid values ────────────────────────────────────────────────────────
    VALID_RISK_LEVELS = frozenset({"low", "medium", "high", "critical"})
    VALID_ACTIONS = frozenset({"approve_order", "reject_order", "escalate_order", "freeze_order"})
    VALID_EVIDENCE_PREFIXES = frozenset({"risk_", "policy_", "agent_run_"})

    # ── abstract ────────────────────────────────────────────────────────────

    @abstractmethod
    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Call the LLM and return its raw text response.

        Subclasses implement this — e.g. DeepSeek over HTTP, mock for tests.
        """
        ...

    # ── public API ──────────────────────────────────────────────────────────

    def analyze(self, context: Dict[str, Any]) -> AgentAnalysisResult:
        """Run the full analysis pipeline on a single order.

        Parameters
        ----------
        context : dict
            Pre-built context dict with keys like ``order``, ``supplier``,
            ``risk_signals``, ``policies``, ``approval_tasks``.
            The caller (typically a service or API handler) is responsible for
            fetching and assembling this context — the agent does NOT touch the
            database itself.

        Returns
        -------
        AgentAnalysisResult
        """
        order_id = context.get("order", {}).get("id", "unknown")

        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(context)

        raw_output: str = ""
        status: str = "success"
        error_message: Optional[str] = None

        try:
            raw_output = self._call_llm(system_prompt, user_prompt)
        except Exception as exc:
            status = "error"
            error_message = str(exc)
            raw_output = ""
            # Build a fallback result — conservative: escalate
            return self._fallback_result(order_id, error_message)

        try:
            parsed = self._parse_response(raw_output)
        except Exception as exc:
            status = "fallback"
            error_message = f"Parse error: {exc}"
            return self._fallback_result(order_id, error_message)

        validated = self._validate_result(parsed, context)

        return AgentAnalysisResult(
            order_id=order_id,
            risk_level=validated.get("risk_level", "medium"),
            suggested_action=validated.get("action", "escalate_order"),
            reason=validated.get("reason", "No reason provided"),
            evidence_ids=validated.get("evidence_ids", []),
            confidence=validated.get("confidence", 0.5),
            raw_output=raw_output,
            status=status,
            error_message=error_message,
        )

    # ── prompt construction ─────────────────────────────────────────────────

    def _build_system_prompt(self) -> str:
        """Return the system prompt for risk analysis."""
        from app.agent.prompts import SYSTEM_PROMPT
        return SYSTEM_PROMPT

    def _build_user_prompt(self, context: Dict[str, Any]) -> str:
        """Serialize the order context into a user prompt."""
        from app.agent.prompts import build_user_prompt
        return build_user_prompt(context)

    # ── response parsing ────────────────────────────────────────────────────

    def _parse_response(self, raw: str) -> Dict[str, Any]:
        """Extract a JSON object from the LLM response.

        Handles DeepSeek's typical response format: code-fenced JSON
        or bare JSON.  The JSON must contain at minimum:
        ``risk_level``, ``action``, ``reason``.

        Raises ValueError if no parseable JSON is found.
        """
        text = raw.strip()

        # Try code-fenced JSON first
        if "```json" in text:
            start = text.index("```json") + 7
            end = text.index("```", start)
            text = text[start:end].strip()
        elif "```" in text:
            start = text.index("```") + 3
            end = text.index("```", start)
            text = text[start:end].strip()

        return json.loads(text)

    # ── validation ──────────────────────────────────────────────────────────

    def _validate_result(
        self, parsed: Dict[str, Any], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate and normalize the parsed LLM output.

        - Clamp risk_level to known values
        - Clamp action to allowed actions
        - Filter evidence_ids to IDs that actually exist in the context
        - Clamp confidence to [0, 1]
        """
        out: Dict[str, Any] = {}

        # risk_level
        rl = str(parsed.get("risk_level", "medium")).lower()
        out["risk_level"] = rl if rl in self.VALID_RISK_LEVELS else "medium"

        # action
        act = str(parsed.get("action", "escalate_order")).lower()
        # Normalize: if the LLM returns "escalate" → "escalate_order", etc.
        if not act.endswith("_order") and act in {"approve", "reject", "escalate", "freeze"}:
            act = f"{act}_order"
        out["action"] = act if act in self.VALID_ACTIONS else "escalate_order"

        # reason
        reason = str(parsed.get("reason", "")).strip()
        out["reason"] = reason if reason else "No reason provided by agent"

        # evidence_ids — only keep IDs that reference actual evidence in the context
        raw_evidence = parsed.get("evidence_ids", [])
        if not isinstance(raw_evidence, list):
            raw_evidence = []
        valid_ids = self._collect_valid_evidence_ids(context)
        out["evidence_ids"] = [eid for eid in raw_evidence if eid in valid_ids]

        # confidence
        conf = parsed.get("confidence", 0.5)
        try:
            conf = float(conf)
        except (TypeError, ValueError):
            conf = 0.5
        out["confidence"] = max(0.0, min(1.0, conf))

        return out

    def _collect_valid_evidence_ids(self, context: Dict[str, Any]) -> set:
        """Collect all valid evidence IDs from the context."""
        valid: set = set()
        for key in ("risk_signals", "policies", "agent_runs"):
            for item in context.get(key, []):
                if isinstance(item, dict) and "id" in item:
                    valid.add(item["id"])
        return valid

    # ── fallback ────────────────────────────────────────────────────────────

    def _fallback_result(
        self, order_id: str, error_message: str
    ) -> AgentAnalysisResult:
        """Return a conservative fallback result when the LLM fails.

        Default: suggest escalate_order (safest option — human must decide).
        """
        return AgentAnalysisResult(
            order_id=order_id,
            risk_level="medium",
            suggested_action="escalate_order",
            reason=f"Fallback: agent analysis failed — {error_message}",
            evidence_ids=[],
            confidence=0.0,
            raw_output="",
            status="error" if "error" in str(error_message).lower() else "fallback",
            error_message=error_message,
        )
