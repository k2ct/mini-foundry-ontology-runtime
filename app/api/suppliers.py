"""
Supplier query API — list all suppliers or fetch one by ID.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_db
from app.ontology.models import Supplier
from app.ontology.schemas import SupplierRead

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


@router.get("", response_model=List[SupplierRead])
def list_suppliers(db: Session = Depends(get_db)):
    """Return all suppliers, ordered by creation time (newest first)."""
    return db.query(Supplier).order_by(Supplier.created_at.desc()).all()


@router.get("/{supplier_id}", response_model=SupplierRead)
def get_supplier(supplier_id: str, db: Session = Depends(get_db)):
    """Return a single supplier by its ID (e.g. ``supplier_001``)."""
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail=f"Supplier '{supplier_id}' not found")
    return supplier
