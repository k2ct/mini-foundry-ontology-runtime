"""
Action type definitions — request schemas, response schemas, and constants.

All state changes flow through these types.  The Action Runtime is the
**only** module allowed to mutate PurchaseOrder.status.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ═══════════════════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════════════════

class ActionType(str, Enum):
    """The four allowed action types."""
    APPROVE = "approve_order"
    REJECT = "reject_order"
    ESCALATE = "escalate_order"
    FREEZE = "freeze_order"


class OrderStatus(str, Enum):
    """The five valid PurchaseOrder statuses."""
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"
    FROZEN = "frozen"


# ═══════════════════════════════════════════════════════════════════════════════
# State transition table — the single source of truth for all valid transitions
# ═══════════════════════════════════════════════════════════════════════════════
#
# Format:  { current_status: { action_type: target_status } }
#
# Terminal states (rejected, frozen) have no outbound transitions.
# ──────────────────────────────────────────────────────────────────────────────

STATE_TRANSITIONS: Dict[str, Dict[str, str]] = {
    "pending_review": {
        "approve_order":  "approved",
        "reject_order":   "rejected",
        "escalate_order": "escalated",
        "freeze_order":   "frozen",
    },
    "escalated": {
        "approve_order":  "approved",
        "reject_order":   "rejected",
        "freeze_order":   "frozen",
    },
    "approved": {
        "freeze_order":   "frozen",
    },
    # rejected — terminal (no outbound transitions)
    # frozen   — terminal (no outbound transitions)
}

# Derived helpers — computed from STATE_TRANSITIONS
ALLOWED_SOURCE_STATUSES: frozenset[str] = frozenset(STATE_TRANSITIONS.keys())

ACTION_TO_TARGET_STATUS: dict[str, str] = {
    "approve_order": "approved",
    "reject_order": "rejected",
    "escalate_order": "escalated",
    "freeze_order": "frozen",
}

# All actions that appear in any transition (should match ActionType)
ALL_ACTION_TYPES: frozenset[str] = frozenset(ACTION_TO_TARGET_STATUS.keys())


# ═══════════════════════════════════════════════════════════════════════════════
# Actor validation constants
# ═══════════════════════════════════════════════════════════════════════════════

# Actors with the "agent:" prefix are READ-ONLY suggesters — they MUST NOT
# execute state-changing actions.  Only user:* and system:* actors may do so.
FORBIDDEN_ACTOR_PREFIX = "agent:"
ALLOWED_ACTOR_PREFIXES: frozenset[str] = frozenset({"user:", "system:"})


# ═══════════════════════════════════════════════════════════════════════════════
# Request / Response Schemas
# ═══════════════════════════════════════════════════════════════════════════════

class ActionExecuteRequest(BaseModel):
    """Request body for POST /actions/execute.

    Fields:
        action_type : one of approve_order | reject_order | escalate_order | freeze_order
        object_id   : target PurchaseOrder ID (e.g. PO-001)
        actor       : who or what is executing this action (must be user:* or system:*)
        reason      : human-readable justification
        evidence_ids: list of RiskSignal / PolicyChunk / AgentRun IDs (must be non-empty)

    Both ``object_id`` and ``order_id`` are accepted on input for backward
    compatibility.  The canonical name is ``object_id``.
    """

    model_config = ConfigDict(populate_by_name=True)

    action_type: str = Field(
        ..., description="approve_order | reject_order | escalate_order | freeze_order"
    )
    object_id: str = Field(
        ...,
        validation_alias="order_id",  # backward-compatible: accepts "order_id" on input
        description="Target PurchaseOrder ID, e.g. PO-001",
    )
    actor: str = Field(
        ..., description="Who/what is executing this action (user:* or system:*)"
    )
    reason: str = Field(
        ..., min_length=1, description="Justification for this action"
    )
    evidence_ids: List[str] = Field(
        ...,
        min_length=1,  # evidence_ids cannot be empty
        description="Supporting evidence IDs — risk_xxx / policy_xxx / agent_run_xxx",
    )

    @field_validator("action_type")
    @classmethod
    def validate_action_type(cls, v: str) -> str:
        allowed = {a.value for a in ActionType}
        if v not in allowed:
            raise ValueError(
                f"Invalid action_type '{v}'. Must be one of: {sorted(allowed)}"
            )
        return v

    @field_validator("actor")
    @classmethod
    def validate_actor_format(cls, v: str) -> str:
        """Basic format check — must be non-empty with a recognized prefix.

        Agent-prefix actors are NOT rejected here.  They are allowed through
        so the Action Runtime can record a failed audit log (the runtime's
        ``validate_actor()`` will block agent actors from actually executing
        the state change, but the audit trail is preserved).
        """
        if not v or not v.strip():
            raise ValueError("actor cannot be empty")
        # Must have a prefix (contains ':')
        if ":" not in v:
            raise ValueError(f"actor '{v}' must include a prefix (e.g. 'user:', 'system:', 'agent:')")
        return v.strip()


class ActionExecuteResponse(BaseModel):
    """Response body for POST /actions/execute.

    Successful action::

        {
            "success": true,
            "action_type": "escalate_order",
            "object_id": "PO-002",
            "before_state": "pending_review",
            "after_state": "escalated",
            "audit_log_id": "audit_001",
            "message": "..."
        }

    Failed action::

        {
            "success": false,
            "action_type": "approve_order",
            "object_id": "PO-005",
            "error": "Action approve_order is not allowed from state frozen."
        }
    """

    model_config = ConfigDict(populate_by_name=True)

    success: bool
    action_type: str
    object_id: str = Field(
        default="",
        validation_alias="order_id",       # accepts "order_id" on input (backward compat)
        serialization_alias="object_id",   # always serializes as "object_id"
    )
    before_state: str = ""
    after_state: str = ""
    audit_log_id: str = ""
    message: str = ""
    error: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════════
# Timeline schemas
# ═══════════════════════════════════════════════════════════════════════════════

class TimelineItem(BaseModel):
    """A single chronological event in an order's timeline.

    Fields:
        event_type : order_created | risk_signal | agent_run | action_audit_log | task_created
        timestamp  : ISO-8601 datetime string
        title      : short human-readable label for this event
        description: longer human-readable description
        ref_id     : the ID of the related entity (risk_xxx / agent_run_xxx / audit_xxx / PO-xxx)
        details    : additional structured data (optional)
    """

    timestamp: str
    event_type: str
    title: str = ""
    description: str = ""
    ref_id: str = ""
    details: dict = Field(default_factory=dict)


class TimelineResponse(BaseModel):
    """Complete audit timeline for a purchase order.

    ``related_policies`` contains PolicyChunks referenced via evidence_ids
    in AgentRun and ActionAuditLog records.  If no evidence is found, all
    PolicyChunks are returned as a fallback so the timeline is never empty.
    """

    order: dict
    supplier: Optional[dict] = None
    risk_signals: List[dict] = Field(default_factory=list)
    related_policies: List[dict] = Field(
        default_factory=list,
        validation_alias="policies",  # backward-compat: accepts "policies" as input
    )
    agent_runs: List[dict] = Field(default_factory=list)
    action_audit_logs: List[dict] = Field(default_factory=list)
    approval_tasks: List[dict] = Field(default_factory=list)
    timeline: List[TimelineItem] = Field(default_factory=list)
