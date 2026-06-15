"""
PurchaseOrder query API — list all orders or fetch one by ID with nested details.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.deps import get_db
from app.ontology.models import PurchaseOrder
from app.ontology.schemas import PurchaseOrderDetailRead, PurchaseOrderRead

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
