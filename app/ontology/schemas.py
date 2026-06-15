"""
Pydantic v2 schemas for the Mini Foundry Ontology Action Runtime.

Provides read schemas for every ORM model, plus composite detail schemas
used in API responses.

All schemas use ``ConfigDict(from_attributes=True)`` (Pydantic v2 equivalent
of the deprecated ``class Config: orm_mode = True``).
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ═══════════════════════════════════════════════════════════════════════════════
# Supplier
# ═══════════════════════════════════════════════════════════════════════════════

class SupplierRead(BaseModel):
    """Public read representation of a supplier."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    risk_level: str
    status: str
    created_at: datetime


# ═══════════════════════════════════════════════════════════════════════════════
# PurchaseOrder
# ═══════════════════════════════════════════════════════════════════════════════

class PurchaseOrderRead(BaseModel):
    """Flat read representation of a purchase order."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    supplier_id: str
    amount: float
    currency: str
    description: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime


class PurchaseOrderDetailRead(BaseModel):
    """Composite detail view: order + supplier + risks + tasks + agent runs.

    Used by API endpoints that return a full audit-ready picture of one order.
    """
    model_config = ConfigDict(from_attributes=True)

    id: str
    supplier_id: str
    amount: float
    currency: str
    description: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime

    supplier: SupplierRead | None = None
    risk_signals: list["RiskSignalRead"] = Field(default_factory=list)
    approval_tasks: list["ApprovalTaskRead"] = Field(default_factory=list)
    agent_runs: list["AgentRunRead"] = Field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════════
# RiskSignal
# ═══════════════════════════════════════════════════════════════════════════════

class RiskSignalRead(BaseModel):
    """Public read representation of a risk signal."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    order_id: str
    signal_type: str
    severity: str
    description: str | None = None
    created_at: datetime


# ═══════════════════════════════════════════════════════════════════════════════
# PolicyChunk
# ═══════════════════════════════════════════════════════════════════════════════

class PolicyChunkRead(BaseModel):
    """Public read representation of a policy chunk."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    content: str
    policy_type: str
    created_at: datetime


# ═══════════════════════════════════════════════════════════════════════════════
# ApprovalTask
# ═══════════════════════════════════════════════════════════════════════════════

class ApprovalTaskRead(BaseModel):
    """Public read representation of an approval task."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    order_id: str
    status: str
    assignee: str | None = None
    created_at: datetime
    updated_at: datetime


# ═══════════════════════════════════════════════════════════════════════════════
# AgentRun
# ═══════════════════════════════════════════════════════════════════════════════

class AgentRunRead(BaseModel):
    """Public read representation of an agent analysis run."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    order_id: str
    risk_level: str | None = None
    suggested_action: str | None = None
    reason: str | None = None
    evidence_ids: str | None = None
    confidence: float | None = None
    raw_output: str | None = None
    status: str
    error_message: str | None = None
    created_at: datetime


# ═══════════════════════════════════════════════════════════════════════════════
# ActionAuditLog
# ═══════════════════════════════════════════════════════════════════════════════

class ActionAuditLogRead(BaseModel):
    """Public read representation of an action audit log entry.

    All fields marked with ★ are hard requirements from the interview task spec.
    """
    model_config = ConfigDict(from_attributes=True)

    id: str
    action_type: str        # ★
    object_id: str          # ★
    actor: str              # ★
    reason: str | None = None  # ★
    evidence_ids: str | None = None  # ★
    before_state: str | None = None  # ★
    after_state: str | None = None   # ★
    timestamp: datetime     # ★
    success: bool           # ★
    error_message: str | None = None  # ★
