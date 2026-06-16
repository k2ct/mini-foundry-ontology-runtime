"""
Audit trace query API — query action audit logs.

GET /audit-logs         — list all audit log entries
GET /audit-logs/{id}    — get a single audit log entry
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.deps import get_db
from app.ontology.models import ActionAuditLog
from app.ontology.schemas import ActionAuditLogRead

router = APIRouter(prefix="/audit-logs", tags=["audit"])


@router.get("", response_model=List[ActionAuditLogRead])
def list_audit_logs(
    order_id: str | None = Query(None, description="Filter by order ID (alias for object_id)"),
    object_id: str | None = Query(None, description="Filter by target object ID (e.g. PO-002)"),
    action_type: str | None = Query(None, description="Filter by action type"),
    success: bool | None = Query(None, description="Filter by success status (true/false)"),
    db: Session = Depends(get_db),
):
    """List all action audit log entries, newest first.

    Optional filters (can be combined):
    - ``?order_id=PO-002`` or ``?object_id=PO-002``
    - ``?action_type=escalate_order``
    - ``?success=true`` or ``?success=false``

    Examples::

        GET /audit-logs?object_id=PO-002
        GET /audit-logs?success=false
        GET /audit-logs?action_type=freeze_order&success=true
    """
    q = db.query(ActionAuditLog).order_by(ActionAuditLog.timestamp.desc())

    # Resolve filter target: object_id takes precedence, order_id as fallback
    filter_object_id = object_id or order_id
    if filter_object_id is not None:
        q = q.filter(ActionAuditLog.object_id == filter_object_id)
    if action_type is not None:
        q = q.filter(ActionAuditLog.action_type == action_type)
    if success is not None:
        q = q.filter(ActionAuditLog.success == success)
    return q.all()


@router.get("/{log_id}", response_model=ActionAuditLogRead)
def get_audit_log(log_id: str, db: Session = Depends(get_db)):
    """Return a single action audit log entry by its ID."""
    log_entry = db.get(ActionAuditLog, log_id)
    if log_entry is None:
        raise HTTPException(status_code=404, detail=f"ActionAuditLog '{log_id}' not found")
    return log_entry
