"""
Validators for the Action Runtime.

Covers three validation dimensions:

    1. Actor validation — only ``user:*`` and ``system:*`` actors may execute state
       changes.  ``agent:*`` actors are READ-ONLY suggesters and are FORBIDDEN.
    2. Evidence validation — every ``evidence_id`` must be non-empty AND traceable
       to a real RiskSignal, PolicyChunk, or AgentRun record.
    3. State transition validation — delegated to ``app.actions.state_machine``.

Hard requirement (面试任务硬性要求):
    - Agent 不能直接执行状态变更
    - evidence_ids 不能为空，必须能追踪到 RiskSignal、PolicyChunk 或 AgentRun
"""

from __future__ import annotations

from typing import Any, Dict, List, Set

from sqlalchemy.orm import Session

from app.actions.types import (
    FORBIDDEN_ACTOR_PREFIX,
    ALLOWED_ACTOR_PREFIXES,
)


# ── Custom exceptions ─────────────────────────────────────────────────────────


class ActorValidationError(Exception):
    """Raised when the actor is not allowed to execute actions."""

    def __init__(self, actor: str, reason: str = "") -> None:
        self.actor = actor
        super().__init__(
            f"Actor validation failed for '{actor}': {reason}"
            if reason else
            f"Actor validation failed for '{actor}'"
        )


class OrderNotFoundError(Exception):
    """Raised when a PurchaseOrder is not found."""

    def __init__(self, order_id: str) -> None:
        self.order_id = order_id
        super().__init__(f"PurchaseOrder '{order_id}' not found")


class EvidenceValidationError(Exception):
    """Raised when evidence_ids fail validation."""

    def __init__(self, missing_ids: List[str] | None = None, *, empty: bool = False) -> None:
        self.missing_ids = missing_ids or []
        if empty:
            super().__init__(
                "Evidence validation failed: evidence_ids cannot be empty. "
                "Every action must reference at least one RiskSignal, PolicyChunk, or AgentRun."
            )
        else:
            super().__init__(
                f"Evidence validation failed: the following IDs do not exist "
                f"in the database: {self.missing_ids}"
            )


# ── Actor validation ──────────────────────────────────────────────────────────


def validate_actor(actor: str, action_type: str) -> None:
    """Validate that *actor* is permitted to execute *action_type*.

    Rules:
        1. actor cannot be empty
        2. actor with ``agent:`` prefix is FORBIDDEN — agents are READ-ONLY
        3. actor must start with ``user:`` or ``system:``

    Args:
        actor: The actor string (e.g. "user:risk_manager", "agent:deepseek").
        action_type: The action being attempted (for error messages).

    Raises:
        ActorValidationError: If the actor is not allowed.
    """
    if not actor or not actor.strip():
        raise ActorValidationError(
            actor,
            reason="actor cannot be empty",
        )

    actor = actor.strip()

    # ── Rule 2: agent:* is FORBIDDEN ──────────────────────────────────────
    if actor.startswith(FORBIDDEN_ACTOR_PREFIX):
        raise ActorValidationError(
            actor,
            reason=(
                f"Actors with '{FORBIDDEN_ACTOR_PREFIX}' prefix (e.g. 'agent:deepseek') "
                f"are READ-ONLY suggesters. They CANNOT execute state-changing actions "
                f"like '{action_type}'. "
                f"Only actors with prefix {sorted(ALLOWED_ACTOR_PREFIXES)} may do so. "
                f"This enforces the Agent execution boundary (智能体执行边界)."
            ),
        )

    # ── Rule 3: must start with user: or system: ──────────────────────────
    allowed = False
    for prefix in ALLOWED_ACTOR_PREFIXES:
        if actor.startswith(prefix):
            allowed = True
            break

    if not allowed:
        raise ActorValidationError(
            actor,
            reason=(
                f"Actor must start with one of {sorted(ALLOWED_ACTOR_PREFIXES)}. "
                f"Got: '{actor}'."
            ),
        )


# ── Evidence validation ───────────────────────────────────────────────────────


def validate_evidence_ids(
    db: Session,
    evidence_ids: List[str],
) -> Dict[str, Any]:
    """Validate that all *evidence_ids* reference real entities in the database.

    Rules:
        1. evidence_ids cannot be empty
        2. Each ID must start with risk_ / policy_ / agent_run_
        3. Each ID must exist in the corresponding database table

    Args:
        db: Active SQLAlchemy database session.
        evidence_ids: List of evidence IDs to validate.

    Returns:
        Categorized valid IDs: ``{"risk": [...], "policy": [...], "agent_run": [...]}``

    Raises:
        EvidenceValidationError: If evidence is empty or contains non-existent IDs.
    """
    from app.ontology.models import RiskSignal, PolicyChunk, AgentRun

    # ── Rule 1: cannot be empty ───────────────────────────────────────────
    if not evidence_ids:
        raise EvidenceValidationError(empty=True)

    missing: Set[str] = set()
    categorized: Dict[str, List[str]] = {
        "risk": [],
        "policy": [],
        "agent_run": [],
    }

    for eid in evidence_ids:
        if eid.startswith("risk_"):
            exists = db.query(RiskSignal).filter(RiskSignal.id == eid).first()
            if exists:
                categorized["risk"].append(eid)
            else:
                missing.add(eid)
        elif eid.startswith("policy_"):
            exists = db.query(PolicyChunk).filter(PolicyChunk.id == eid).first()
            if exists:
                categorized["policy"].append(eid)
            else:
                missing.add(eid)
        elif eid.startswith("agent_run_"):
            exists = db.query(AgentRun).filter(AgentRun.id == eid).first()
            if exists:
                categorized["agent_run"].append(eid)
            else:
                missing.add(eid)
        else:
            missing.add(eid)

    if missing:
        raise EvidenceValidationError(sorted(missing))

    return categorized


# ── Composite validation ──────────────────────────────────────────────────────


def validate_action_request(
    db: Session,
    order_id: str,
    action_type: str,
    actor: str,
    evidence_ids: List[str],
) -> None:
    """Run all pre-execution validations on an action request.

    Validation order:
        1. Actor validation (no agent:*, must be user:* or system:*)
        2. Order existence check
        3. State transition validation
        4. Evidence ID traceability

    Args:
        db: Active SQLAlchemy database session.
        order_id: Target PurchaseOrder ID.
        action_type: One of approve_order | reject_order | escalate_order | freeze_order.
        actor: Who is executing this action.
        evidence_ids: Evidence IDs supporting this action.

    Raises:
        ActorValidationError: If the actor is not allowed.
        OrderNotFoundError: If the order does not exist.
        InvalidStateTransitionError: If the state transition is not allowed.
        EvidenceValidationError: If evidence IDs are invalid.
    """
    from app.ontology.models import PurchaseOrder
    from app.actions.state_machine import validate_state_transition

    # 1. Actor validation
    validate_actor(actor, action_type)

    # 2. Order exists
    order = db.get(PurchaseOrder, order_id)
    if order is None:
        raise OrderNotFoundError(order_id)

    # 3. State transition is valid
    validate_state_transition(order.id, order.status, action_type)

    # 4. Evidence is valid
    validate_evidence_ids(db, evidence_ids)


# Alias for backwards compatibility
validate_action_execution = validate_action_request

