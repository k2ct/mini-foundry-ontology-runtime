"""
PolicyChunk query API — list all policy chunks or fetch one by ID.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.deps import get_db
from app.ontology.models import PolicyChunk
from app.ontology.schemas import PolicyChunkRead

router = APIRouter(prefix="/policies", tags=["policies"])


@router.get("", response_model=List[PolicyChunkRead])
def list_policies(
    policy_type: str | None = Query(None, description="Filter by policy type"),
    db: Session = Depends(get_db),
):
    """Return all policy chunks, newest first.

    Optional filter: ``?policy_type=amount_threshold``
    """
    q = db.query(PolicyChunk).order_by(PolicyChunk.created_at.desc())
    if policy_type is not None:
        q = q.filter(PolicyChunk.policy_type == policy_type)
    return q.all()


@router.get("/{policy_id}", response_model=PolicyChunkRead)
def get_policy(policy_id: str, db: Session = Depends(get_db)):
    """Return a single policy chunk by its ID (e.g. ``policy_001``)."""
    policy = db.get(PolicyChunk, policy_id)
    if policy is None:
        raise HTTPException(status_code=404, detail=f"PolicyChunk '{policy_id}' not found")
    return policy
