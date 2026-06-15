"""
RiskSignal query API — list all risk signals or fetch one by ID.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.deps import get_db
from app.ontology.models import RiskSignal
from app.ontology.schemas import RiskSignalRead

router = APIRouter(prefix="/risk-signals", tags=["risk-signals"])


@router.get("", response_model=List[RiskSignalRead])
def list_risk_signals(
    order_id: str | None = Query(None, description="Filter by order ID"),
    severity: str | None = Query(None, description="Filter by severity"),
    db: Session = Depends(get_db),
):
    """Return all risk signals, newest first.

    Optional filters:
    - ``?order_id=PO-001``
    - ``?severity=critical``
    """
    q = db.query(RiskSignal).order_by(RiskSignal.created_at.desc())
    if order_id is not None:
        q = q.filter(RiskSignal.order_id == order_id)
    if severity is not None:
        q = q.filter(RiskSignal.severity == severity)
    return q.all()


@router.get("/{risk_id}", response_model=RiskSignalRead)
def get_risk_signal(risk_id: str, db: Session = Depends(get_db)):
    """Return a single risk signal by its ID (e.g. ``risk_001``)."""
    risk = db.get(RiskSignal, risk_id)
    if risk is None:
        raise HTTPException(status_code=404, detail=f"RiskSignal '{risk_id}' not found")
    return risk
