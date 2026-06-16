"""
Policy chunk service — policy-related business operations.
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from app.ontology.models import PolicyChunk


class PolicyService:
    """Business operations for policy chunks."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_all(self, policy_type: Optional[str] = None) -> List[PolicyChunk]:
        """Return all policy chunks, optionally filtered by type."""
        q = self.db.query(PolicyChunk).order_by(PolicyChunk.created_at.desc())
        if policy_type:
            q = q.filter(PolicyChunk.policy_type == policy_type)
        return q.all()

    def get_by_id(self, policy_id: str) -> Optional[PolicyChunk]:
        """Return a single policy chunk by ID, or None."""
        return self.db.get(PolicyChunk, policy_id)

    def get_by_ids(self, policy_ids: List[str]) -> List[PolicyChunk]:
        """Return policy chunks matching the given IDs."""
        return (
            self.db.query(PolicyChunk)
            .filter(PolicyChunk.id.in_(policy_ids))
            .all()
        )
