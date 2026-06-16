"""
Action Runtime module — the single source of truth for business state transitions.

Submodules:
    types           — Action type definitions and request/response schemas
    state_machine   — Valid state transition map for PurchaseOrder
    validators      — Evidence and business rule validators
    runtime         — ActionRuntime executor (the core state-change engine)
"""

from app.actions.types import (
    ActionType,
    OrderStatus,
    ActionExecuteRequest,
    ActionExecuteResponse,
    TimelineResponse,
    TimelineItem,
)
from app.actions.state_machine import (
    validate_state_transition,
    InvalidStateTransitionError,
)
from app.actions.validators import (
    validate_evidence_ids,
    validate_action_execution,
    EvidenceValidationError,
    OrderNotFoundError,
)
from app.actions.runtime import ActionRuntime

__all__ = [
    # Types
    "ActionType",
    "OrderStatus",
    "ActionExecuteRequest",
    "ActionExecuteResponse",
    "TimelineResponse",
    "TimelineItem",
    # State machine
    "validate_state_transition",
    "InvalidStateTransitionError",
    # Validators
    "validate_evidence_ids",
    "validate_action_execution",
    "EvidenceValidationError",
    "OrderNotFoundError",
    # Runtime
    "ActionRuntime",
]
