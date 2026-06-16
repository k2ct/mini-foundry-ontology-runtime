"""
PurchaseOrder query API — list all orders, fetch detail, and query timelines.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.deps import get_db
from app.ontology.models import PurchaseOrder
from app.ontology.schemas import PurchaseOrderDetailRead, PurchaseOrderRead
from app.audit.trace import build_timeline

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("", response_model=List[PurchaseOrderRead])
def list_orders(
    status: str | None = Query(None, description="Filter by order status"),
    db: Session = Depends(get_db),
):
    """Return all purchase orders, newest first.

    Optionally filter by ``?status=pending_review``.
    """
    q = db.query(PurchaseOrder).order_by(PurchaseOrder.created_at.desc())
    if status is not None:
        q = q.filter(PurchaseOrder.status == status)
    return q.all()


@router.get("/{order_id}", response_model=PurchaseOrderDetailRead)
def get_order(order_id: str, db: Session = Depends(get_db)):
    """Return a single purchase order with its supplier, risk signals,
    approval tasks, and agent run history.

    Example: ``GET /orders/PO-001``
    """
    order = db.get(PurchaseOrder, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order '{order_id}' not found")
    return order


@router.get("/{order_id}/timeline")
def get_order_timeline(order_id: str, db: Session = Depends(get_db)):
    """Return the complete audit timeline for a purchase order.

    The timeline includes:
    - Order and supplier details
    - All risk signals detected
    - All referenced policies
    - All agent analysis runs
    - All action audit log entries (successful and failed)
    - All approval tasks
    - A unified chronological event timeline

    Example: ``GET /orders/PO-002/timeline``
    """
    timeline = build_timeline(db, order_id)
    if timeline is None:
        raise HTTPException(status_code=404, detail=f"Order '{order_id}' not found")
    return timeline
