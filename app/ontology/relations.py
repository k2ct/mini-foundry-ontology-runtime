"""
Entity relationship map and query helpers for the ontology layer.

Relationships at a glance
──────────────────────────

    Supplier (1) ────< (N) PurchaseOrder
        A supplier can have many purchase orders.

    PurchaseOrder (1) ────< (N) RiskSignal
        An order can accumulate multiple risk signals during review.

    PurchaseOrder (1) ────< (N) ApprovalTask
        An order can have multiple approval tasks (e.g. multi-level approvals).

    PurchaseOrder (1) ────< (N) AgentRun
        An order can be analysed by the agent multiple times (re-analysis,
        different policy checks, etc.).  AgentRuns are READ-ONLY suggestions.

    PolicyChunk ── referenced via evidence_ids ──> AgentRun / ActionAuditLog
        PolicyChunks are not linked by FK.  They are cited by ID in the
        ``evidence_ids`` JSON field of AgentRun and ActionAuditLog.

    ActionAuditLog ── logical reference via object_id ──> PurchaseOrder
        ActionAuditLog.object_id stores the ID of the entity that was acted
        upon (most commonly a PurchaseOrder).  There is no FK constraint here
        because the log may reference objects that have been deleted, and
        because it is a write-once, append-only audit store.

Design constraint (面试任务硬性要求)
────────────────────────────────────

    AgentRun → PurchaseOrder is a READ-ONLY suggestion relationship.
    Agents write to ``agent_runs``; the Action Runtime reads those suggestions
    and decides whether to mutate ``purchase_orders.status``.  Every mutation
    is recorded in ``action_audit_logs`` with before/after state snapshots.
"""

from app.ontology.models import (
    ActionAuditLog,
    AgentRun,
    ApprovalTask,
    PolicyChunk,
    PurchaseOrder,
    RiskSignal,
    Supplier,
)

# Re-export all models for convenience, so callers can do:
#     from app.ontology.relations import Supplier, PurchaseOrder, ...
__all__ = [
    "Supplier",
    "PurchaseOrder",
    "RiskSignal",
    "PolicyChunk",
    "ApprovalTask",
    "AgentRun",
    "ActionAuditLog",
]
