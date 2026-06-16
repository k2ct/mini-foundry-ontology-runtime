"""
Supplier service — supplier-related business operations.
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from app.ontology.models import Supplier


class SupplierService:
    """Business operations for suppliers."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_all(self) -> List[Supplier]:
        """Return all suppliers, newest first."""
        return (
            self.db.query(Supplier)
            .order_by(Supplier.created_at.desc())
            .all()
        )

    def get_by_id(self, supplier_id: str) -> Optional[Supplier]:
        """Return a single supplier by ID, or None."""
        return self.db.get(Supplier, supplier_id)

    def to_dict(self, supplier: Supplier) -> dict:
        """Serialize a Supplier to a plain dict for agent context."""
        return {
            "id": supplier.id,
            "name": supplier.name,
            "risk_level": supplier.risk_level,
            "status": supplier.status,
        }
