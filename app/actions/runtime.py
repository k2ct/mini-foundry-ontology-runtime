"""
Action Runtime — the single source of truth for business state changes.

This is the ONLY module allowed to mutate PurchaseOrder.status.
It enforces:

1. State transition validation (pending_review → approved/rejected/escalated/frozen)
2. Evidence traceability (every action must reference real RiskSignal/PolicyChunk/AgentRun)
3. Audit logging (every successful AND failed action writes an ActionAuditLog entry)
4. ApprovalTask status synchronization (order status change → task status change)

Usage::

    from app.actions.runtime import ActionRuntime

    runtime = ActionRuntime(db_session)
    result = runtime.execute(
        action_type="escalate_order",
        order_id="PO-002",
        actor="deepseek_agent",
        reason="金额超阈值，需升级审批",
        evidence_ids=["risk_002", "policy_001"],
        agent_run_id="agent_run_001",
    )
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from app.actions.state_machine import (
    InvalidStateTransitionError,
    validate_state_transition,
)
from app.actions.types import (
    ACTION_TO_TARGET_STATUS,
    ActionExecuteResponse,
)
from app.actions.validators import (
    ActorValidationError,
    EvidenceValidationError,
    OrderNotFoundError,
    validate_evidence_ids,
)

logger = logging.getLogger(__name__)


class ActionExecutionError(Exception):
    """Raised when an action cannot be executed (wraps all sub-errors)."""

    def __init__(self, order_id: str, action_type: str, reason: str) -> None:
        self.order_id = order_id
        self.action_type = action_type
        self.reason = reason
        super().__init__(f"Action '{action_type}' on '{order_id}' failed: {reason}")


class ActionRuntime:
    """The central state-change engine.

    Design constraint (面试任务硬性要求):
        - AgentRun cannot directly modify PurchaseOrder.status.
        - AgentRun cannot directly modify ApprovalTask.status.
        - Action Runtime is the ONLY state-change entry point.
        - Every successful AND failed action must write an ActionAuditLog.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    # ── public API ──────────────────────────────────────────────────────────

    def execute(
        self,
        *,
        action_type: str,
        order_id: str,
        actor: str,
        reason: str,
        evidence_ids: Optional[List[str]] = None,
        agent_run_id: Optional[str] = None,
    ) -> ActionExecuteResponse:
        """Execute an action on a purchase order.

        This is the main entry point.  All validation, state mutation,
        and audit logging happens within this method.

        Parameters
        ----------
        action_type : str
            One of approve_order | reject_order | escalate_order | freeze_order.
        order_id : str
            Target PurchaseOrder ID (e.g. PO-001).
        actor : str
            Who/what is executing this action.
        reason : str
            Human-readable justification.
        evidence_ids : list[str], optional
            Supporting evidence IDs.
        agent_run_id : str, optional
            The AgentRun that suggested this action.

        Returns
        -------
        ActionExecuteResponse
        """
        evidence_ids = evidence_ids or []

        # ── 1. Pre-validation ───────────────────────────────────────────
        try:
            self._validate(order_id, action_type, actor, evidence_ids)
        except (
            ValueError,
            InvalidStateTransitionError,
            EvidenceValidationError,
            OrderNotFoundError,
            ActorValidationError,
        ) as exc:
            # Write a FAILED audit log entry and COMMIT it immediately.
            # The transaction is otherwise rolled back by the HTTP exception.
            audit_log_id = self._write_audit_log(
                action_type=action_type,
                order_id=order_id,
                actor=actor,
                reason=reason,
                evidence_ids=evidence_ids,
                before_status="unknown",
                after_status="unknown",
                success=False,
                error_message=str(exc),
            )
            try:
                self.db.commit()
            except Exception:
                self.db.rollback()
            return ActionExecuteResponse(
                success=False,
                action_type=action_type,
                object_id=order_id,
                before_state="unknown",
                after_state="unknown",
                audit_log_id=audit_log_id,
                message=f"Action validation failed: {exc}",
                error=str(exc),
            )

        # ── 2. Execute state change ─────────────────────────────────────
        try:
            before_status, after_status = self._apply_state_change(
                order_id, action_type
            )
        except Exception as exc:
            audit_log_id = self._write_audit_log(
                action_type=action_type,
                order_id=order_id,
                actor=actor,
                reason=reason,
                evidence_ids=evidence_ids,
                before_status="unknown",
                after_status="unknown",
                success=False,
                error_message=str(exc),
            )
            # Commit the failed audit log before rolling back other changes
            try:
                self.db.commit()
            except Exception:
                self.db.rollback()
            return ActionExecuteResponse(
                success=False,
                action_type=action_type,
                object_id=order_id,
                before_state="unknown",
                after_state="unknown",
                audit_log_id=audit_log_id,
                message=f"State change failed: {exc}",
                error=str(exc),
            )

        # ── 3. Write successful audit log ───────────────────────────────
        audit_log_id = self._write_audit_log(
            action_type=action_type,
            order_id=order_id,
            actor=actor,
            reason=reason,
            evidence_ids=evidence_ids,
            before_status=before_status,
            after_status=after_status,
            success=True,
            error_message=None,
        )

        # ── 4. Synchronize approval task status ─────────────────────────
        self._sync_approval_tasks(order_id, after_status)

        # ── 5. Commit ───────────────────────────────────────────────────
        try:
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            raise ActionExecutionError(order_id, action_type, f"Commit failed: {exc}") from exc

        return ActionExecuteResponse(
            success=True,
            action_type=action_type,
            object_id=order_id,
            before_state=before_status,
            after_state=after_status,
            audit_log_id=audit_log_id,
            message=(
                f"Action '{action_type}' executed on '{order_id}': "
                f"{before_status} → {after_status}"
            ),
            error=None,
        )

    # ── private helpers ─────────────────────────────────────────────────────

    def _validate(
        self,
        order_id: str,
        action_type: str,
        actor: str,
        evidence_ids: List[str],
    ) -> None:
        """Run pre-execution validations.  Raises on first failure."""
        from app.actions.validators import validate_action_request

        validate_action_request(self.db, order_id, action_type, actor, evidence_ids)
        logger.info(
            "Validation passed for action '%s' on order '%s' by actor '%s'",
            action_type, order_id, actor,
        )

    def _apply_state_change(
        self, order_id: str, action_type: str
    ) -> tuple[str, str]:
        """Apply the state change to the PurchaseOrder.

        Returns (before_status, after_status).

        Raises InvalidStateTransitionError if the transition is invalid.
        """
        from app.ontology.models import PurchaseOrder

        order = self.db.get(PurchaseOrder, order_id)
        if order is None:
            raise ValueError(f"PurchaseOrder '{order_id}' not found")

        before_status = order.status
        target_status = validate_state_transition(order.id, order.status, action_type)

        order.status = target_status
        order.updated_at = datetime.now()  # type: ignore[assignment]

        self.db.flush()  # make the change visible within the transaction
        logger.info(
            "State change applied: %s: %s → %s",
            order_id, before_status, target_status,
        )

        return before_status, target_status

    def _write_audit_log(
        self,
        *,
        action_type: str,
        order_id: str,
        actor: str,
        reason: str,
        evidence_ids: List[str],
        before_status: str,
        after_status: str,
        success: bool,
        error_message: Optional[str],
    ) -> str:
        """Write an ActionAuditLog entry and return its ID."""
        from app.ontology.models import ActionAuditLog

        # Generate a deterministic ID from the current timestamp + order + a random
        # suffix to prevent collisions when multiple actions run in rapid succession.
        import uuid
        suffix = uuid.uuid4().hex[:6]
        audit_id = f"audit_{order_id}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{suffix}"

        log_entry = ActionAuditLog(
            id=audit_id,
            action_type=action_type,
            object_id=order_id,
            actor=actor,
            reason=reason,
            evidence_ids=json.dumps(evidence_ids, ensure_ascii=False) if evidence_ids else None,
            before_state=json.dumps(
                {"status": before_status}, ensure_ascii=False
            ),
            after_state=json.dumps(
                {"status": after_status}, ensure_ascii=False
            ),
            timestamp=datetime.now(),
            success=success,
            error_message=error_message,
        )

        self.db.add(log_entry)
        self.db.flush()  # assign ID without committing

        level = logging.INFO if success else logging.WARNING
        logger.log(
            level,
            "Audit log written: %s (success=%s, action=%s, order=%s)",
            audit_id, success, action_type, order_id,
        )

        return audit_id

    def _sync_approval_tasks(self, order_id: str, new_status: str) -> None:
        """Synchronize ApprovalTask status with the order's new status.

        When an order moves to a terminal state, all open approval tasks
        for that order are updated to match.
        """
        from app.ontology.models import ApprovalTask

        # Map order status → task status
        status_map = {
            "approved": "approved",
            "rejected": "rejected",
            "escalated": "escalated",
            "frozen": "frozen",
        }

        task_status = status_map.get(new_status)
        if task_status is None:
            return

        tasks = (
            self.db.query(ApprovalTask)
            .filter(
                ApprovalTask.order_id == order_id,
                ApprovalTask.status == "open",
            )
            .all()
        )

        for task in tasks:
            task.status = task_status
            task.updated_at = datetime.now()  # type: ignore[assignment]

        if tasks:
            logger.info(
                "Synced %d approval task(s) for order '%s' to status '%s'",
                len(tasks), order_id, task_status,
            )
