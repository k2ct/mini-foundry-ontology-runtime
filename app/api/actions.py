"""
Action execution API — the ONLY entry point for business state changes.

POST /actions/execute
    Execute an action (approve/reject/escalate/freeze) on a purchase order.
    Validates the actor, state transition, and evidence, applies the change,
    and writes an audit log.

    Both success and failure are recorded in action_audit_logs.

Actor rules:
    - ``agent:*`` actors are FORBIDDEN — they are READ-ONLY suggesters
    - Only ``user:*`` and ``system:*`` actors may execute state changes

State machine rules:
    - See ``app/actions/state_machine.py`` for the full transition table
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.actions.runtime import ActionRuntime, ActionExecutionError
from app.actions.types import ActionExecuteRequest, ActionExecuteResponse
from app.actions.validators import ActorValidationError
from app.deps import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/actions", tags=["actions"])


@router.post("/execute", response_model=ActionExecuteResponse)
def execute_action(
    request: ActionExecuteRequest,
    db: Session = Depends(get_db),
):
    """Execute an action on a purchase order.

    This is the **only** endpoint that can mutate ``PurchaseOrder.status``.
    All state changes are validated, executed, and audited atomically.

    Request body example (using ``object_id``)::

        {
            "action_type": "escalate_order",
            "object_id": "PO-002",
            "actor": "user:risk_manager",
            "reason": "Order amount exceeds 100000 and requires escalation.",
            "evidence_ids": ["risk_002", "policy_001"]
        }

    **Allowed action_type values:**
    - ``approve_order``  — approve the order
    - ``reject_order``   — reject the order
    - ``escalate_order`` — escalate for further review
    - ``freeze_order``   — freeze the order immediately

    **Actor constraints:**
    - ``user:*`` and ``system:*`` — allowed
    - ``agent:*`` — FORBIDDEN (agents are READ-ONLY suggesters)

    **Evidence constraints:**
    - evidence_ids must be non-empty
    - Each ID must be traceable to a real RiskSignal, PolicyChunk, or AgentRun

    **Design constraint:** AgentRun records are READ-ONLY suggestions.
    Only the Action Runtime can change PurchaseOrder.status, and every
    state change (success or failure) is recorded in action_audit_logs.
    """
    runtime = ActionRuntime(db)

    # Extract object_id (supports both "object_id" and legacy "order_id" key)
    object_id = request.object_id

    try:
        result = runtime.execute(
            action_type=request.action_type,
            order_id=object_id,
            actor=request.actor,
            reason=request.reason,
            evidence_ids=request.evidence_ids,
        )
    except ActionExecutionError as exc:
        logger.exception("Action execution failed")
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        logger.exception("Unexpected error during action execution")
        raise HTTPException(status_code=500, detail=f"Action execution error: {exc}")

    if not result.success:
        # Check if it was an actor validation failure → 403 Forbidden
        if result.error and "actor" in result.error.lower():
            raise HTTPException(status_code=403, detail=result.error)
        # Return 422 for other business-logic failures (invalid state, bad evidence, etc.)
        raise HTTPException(status_code=422, detail=result.error or result.message)

    return result
