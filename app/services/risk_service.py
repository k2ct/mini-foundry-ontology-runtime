"""
Risk signal service — risk-related business operations.
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from app.ontology.models import RiskSignal


class RiskService:
    """Business operations for risk signals."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_all(
        self,
        order_id: Optional[str] = None,
        severity: Optional[str] = None,
    ) -> List[RiskSignal]:
        """Return risk signals, optionally filtered by order or severity."""
        q = self.db.query(RiskSignal).order_by(RiskSignal.created_at.desc())
        if order_id:
            q = q.filter(RiskSignal.order_id == order_id)
        if severity:
            q = q.filter(RiskSignal.severity == severity)
        return q.all()

    def get_by_id(self, risk_id: str) -> Optional[RiskSignal]:
        """Return a single risk signal by ID, or None."""
        return self.db.get(RiskSignal, risk_id)

    def get_for_order(self, order_id: str) -> List[RiskSignal]:
        """Return all risk signals for a given order."""
        return (
            self.db.query(RiskSignal)
            .filter(RiskSignal.order_id == order_id)
            .all()
        )
