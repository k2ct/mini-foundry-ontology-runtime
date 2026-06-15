"""
SQLAlchemy ORM models for the Mini Foundry Ontology Action Runtime.

Seven core entities for the enterprise procurement risk audit domain:

    Supplier          — vendor master data
    PurchaseOrder     — procurement order under review
    RiskSignal        — detected risk indicator on an order
    PolicyChunk       — policy fragment used as evidence
    ApprovalTask      — human / system approval task
    AgentRun          — LLM agent analysis result (read-only suggestion)
    ActionAuditLog    — immutable audit trail for every state-changing action

Design constraint (面试任务硬性要求):
    AgentRun records are READ-ONLY suggestions.  They MUST NOT directly mutate
    PurchaseOrder.status or any other business object.  All state transitions
    go through the Action Runtime, which writes ActionAuditLog entries.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# ── Supplier ─────────────────────────────────────────────────────────────────

class Supplier(Base):
    """Vendor / supplier master record."""

    __tablename__ = "suppliers"

    id: Mapped[str] = mapped_column(
        String(50), primary_key=True, comment="e.g. supplier_001"
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    risk_level: Mapped[str] = mapped_column(
        String(20), nullable=False, default="low",
        comment="low | medium | high | critical",
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active",
        comment="active | watchlist | blacklisted",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False,
    )

    # ── relationships ────────────────────────────────────────────────────
    purchase_orders: Mapped[list["PurchaseOrder"]] = relationship(
        back_populates="supplier", lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Supplier(id={self.id!r}, name={self.name!r}, risk={self.risk_level!r})>"


# ── PurchaseOrder ────────────────────────────────────────────────────────────

class PurchaseOrder(Base):
    """Procurement purchase order — the central entity under risk review."""

    __tablename__ = "purchase_orders"

    id: Mapped[str] = mapped_column(
        String(50), primary_key=True, comment="e.g. PO-001",
    )
    supplier_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("suppliers.id"), nullable=False,
    )
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(
        String(10), nullable=False, default="CNY",
    )
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending_review",
        comment="pending_review | approved | rejected | escalated | frozen",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False,
    )

    # ── relationships ────────────────────────────────────────────────────
    supplier: Mapped["Supplier"] = relationship(back_populates="purchase_orders")
    risk_signals: Mapped[list["RiskSignal"]] = relationship(
        back_populates="purchase_order", lazy="selectin",
    )
    approval_tasks: Mapped[list["ApprovalTask"]] = relationship(
        back_populates="purchase_order", lazy="selectin",
    )
    agent_runs: Mapped[list["AgentRun"]] = relationship(
        back_populates="purchase_order", lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<PurchaseOrder(id={self.id!r}, status={self.status!r})>"


# ── RiskSignal ───────────────────────────────────────────────────────────────

class RiskSignal(Base):
    """A risk indicator detected on a specific purchase order."""

    __tablename__ = "risk_signals"

    id: Mapped[str] = mapped_column(
        String(50), primary_key=True, comment="e.g. risk_001",
    )
    order_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("purchase_orders.id"), nullable=False,
    )
    signal_type: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="high_amount | blacklisted_supplier | missing_document | abnormal_frequency",
    )
    severity: Mapped[str] = mapped_column(
        String(20), nullable=False, default="medium",
        comment="low | medium | high | critical",
    )
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False,
    )

    # ── relationships ────────────────────────────────────────────────────
    purchase_order: Mapped["PurchaseOrder"] = relationship(
        back_populates="risk_signals",
    )

    def __repr__(self) -> str:
        return f"<RiskSignal(id={self.id!r}, type={self.signal_type!r}, severity={self.severity!r})>"


# ── PolicyChunk ──────────────────────────────────────────────────────────────

class PolicyChunk(Base):
    """A reusable policy fragment used as evidence by agents and the runtime.

    PolicyChunks are NOT directly linked to orders via foreign keys.  Instead,
    agents reference them in ``evidence_ids`` (a JSON array of policy IDs).
    """

    __tablename__ = "policy_chunks"

    id: Mapped[str] = mapped_column(
        String(50), primary_key=True, comment="e.g. policy_001",
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    policy_type: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="amount_threshold | supplier_compliance | approval_rule | document_rule",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False,
    )

    def __repr__(self) -> str:
        return f"<PolicyChunk(id={self.id!r}, title={self.title!r})>"


# ── ApprovalTask ─────────────────────────────────────────────────────────────

class ApprovalTask(Base):
    """A human or system approval task attached to a purchase order."""

    __tablename__ = "approval_tasks"

    id: Mapped[str] = mapped_column(
        String(50), primary_key=True, comment="e.g. task_001",
    )
    order_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("purchase_orders.id"), nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="open",
        comment="open | approved | rejected | escalated | frozen",
    )
    assignee: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False,
    )

    # ── relationships ────────────────────────────────────────────────────
    purchase_order: Mapped["PurchaseOrder"] = relationship(
        back_populates="approval_tasks",
    )

    def __repr__(self) -> str:
        return f"<ApprovalTask(id={self.id!r}, status={self.status!r})>"


# ── AgentRun ─────────────────────────────────────────────────────────────────

class AgentRun(Base):
    """Immutable record of an LLM agent's analysis on a purchase order.

    **Design constraint:**  AgentRun stores the agent's *suggestion* only.
    It MUST NOT directly modify PurchaseOrder.status or any other business
    object.  All state transitions are executed by the Action Runtime, which
    writes corresponding ActionAuditLog entries.
    """

    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(
        String(50), primary_key=True, comment="e.g. agent_run_001",
    )
    order_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("purchase_orders.id"), nullable=False,
    )
    risk_level: Mapped[str | None] = mapped_column(
        String(20), nullable=True,
    )
    suggested_action: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_ids: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="JSON array of policy IDs",
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="success",
        comment="success | fallback | error",
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False,
    )

    # ── relationships ────────────────────────────────────────────────────
    purchase_order: Mapped["PurchaseOrder"] = relationship(
        back_populates="agent_runs",
    )

    def __repr__(self) -> str:
        return f"<AgentRun(id={self.id!r}, action={self.suggested_action!r}, status={self.status!r})>"


# ── ActionAuditLog ───────────────────────────────────────────────────────────

class ActionAuditLog(Base):
    """Immutable audit trail for every state-changing action.

    This is the core of the audit closed-loop and traceable query system
    (审计闭环与可追溯查询).  Every successful AND failed action is recorded.

    Fields marked with ★ are hard requirements from the interview task spec.
    """

    __tablename__ = "action_audit_logs"

    id: Mapped[str] = mapped_column(
        String(50), primary_key=True, comment="e.g. audit_001",
    )
    # ★ action_type
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # ★ object_id — the target entity ID (e.g. PurchaseOrder.id)
    object_id: Mapped[str] = mapped_column(String(50), nullable=False)
    # ★ actor
    actor: Mapped[str] = mapped_column(String(100), nullable=False)
    # ★ reason
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # ★ evidence_ids — JSON string of referenced policy IDs / risk signal IDs
    evidence_ids: Mapped[str | None] = mapped_column(
        Text, nullable=True,
    )
    # ★ before_state
    before_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    # ★ after_state
    after_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    # ★ timestamp
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False,
    )
    # ★ success
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # ★ error_message
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<ActionAuditLog(id={self.id!r}, action={self.action_type!r}, success={self.success})>"
