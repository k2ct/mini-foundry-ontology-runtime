"""
Audit Logger — immutable, append-only record of every action execution.

Design constraint (面试任务硬性要求):
    Every successful AND failed action execution MUST be recorded in the
    action_audit_logs table with before/after snapshots, actor, reason,
    evidence_ids, timestamp, and success flag.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.ontology.models import ActionAuditLog


class AuditLogger:
    """Append-only audit trail writer.

    Usage::

        logger = AuditLogger(db_session)
        logger.log_success(
            action_type="escalate_order",
            object_id="PO-002",
            actor="admin",
            reason="金额超阈值，需要升级审批",
            evidence_ids=["risk_002", "policy_001"],
            before_state=json.dumps({"status": "pending_review"}),
            after_state=json.dumps({"status": "escalated"}),
        )
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    # ── public API ──────────────────────────────────────────────────────────

    def log_success(
        self,
        *,
        action_type: str,
        object_id: str,
        actor: str,
        reason: str,
        evidence_ids: List[str],
        before_state: str,
        after_state: str,
    ) -> ActionAuditLog:
        """Record a successful action execution.

        Returns the created ActionAuditLog ORM instance (already flushed).
        """
        return self._write(
            action_type=action_type,
            object_id=object_id,
            actor=actor,
            reason=reason,
            evidence_ids=evidence_ids,
            before_state=before_state,
            after_state=after_state,
            success=True,
            error_message=None,
        )

    def log_failure(
        self,
        *,
        action_type: str,
        object_id: str,
        actor: str,
        reason: str,
        evidence_ids: List[str],
        before_state: str,
        error_message: str,
    ) -> ActionAuditLog:
        """Record a failed action execution.

        Returns the created ActionAuditLog ORM instance (already flushed).
        """
        return self._write(
            action_type=action_type,
            object_id=object_id,
            actor=actor,
            reason=reason,
            evidence_ids=evidence_ids,
            before_state=before_state,
            after_state=before_state,  # state unchanged on failure
            success=False,
            error_message=error_message,
        )

    # ── internal ────────────────────────────────────────────────────────────

    def _write(
        self,
        *,
        action_type: str,
        object_id: str,
        actor: str,
        reason: str,
        evidence_ids: List[str],
        before_state: str,
        after_state: str,
        success: bool,
        error_message: Optional[str],
    ) -> ActionAuditLog:
        """Write a single audit log entry and flush it to the database."""
        audit_id = self._generate_id()

        entry = ActionAuditLog(
            id=audit_id,
            action_type=action_type,
            object_id=object_id,
            actor=actor,
            reason=reason,
            evidence_ids=json.dumps(evidence_ids, ensure_ascii=False),
            before_state=before_state,
            after_state=after_state,
            timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
            success=success,
            error_message=error_message,
        )

        self._db.add(entry)
        self._db.flush()  # flush now so the caller can read the ID
        return entry

    @staticmethod
    def _generate_id() -> str:
        """Generate a unique audit log ID."""
        suffix = uuid.uuid4().hex[:8]
        return f"audit_{suffix}"
