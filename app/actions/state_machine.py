"""
State machine for PurchaseOrder status transitions.

Defines the complete transition table and provides:
    - get_next_state(current_status, action_type) → target_status | None
    - is_transition_allowed(current_status, action_type) → bool
    - validate_state_transition(order_id, current_status, action_type) → target_status

Transition table (the single source of truth):

============================= ================= ==============
current_status                action_type        target_status
============================= ================= ==============
pending_review                approve_order      approved
pending_review                reject_order       rejected
pending_review                escalate_order     escalated
pending_review                freeze_order       frozen
escalated                     approve_order      approved
escalated                     reject_order       rejected
escalated                     freeze_order       frozen
approved                      freeze_order       frozen
rejected                      (terminal)
frozen                        (terminal)
============================= ================= ==============

Illegal examples:
    frozen    → approve_order   ✗
    rejected  → approve_order   ✗
    approved  → reject_order    ✗
"""

from __future__ import annotations

from app.actions.types import STATE_TRANSITIONS, ALLOWED_SOURCE_STATUSES


class InvalidStateTransitionError(Exception):
    """Raised when a state transition is not allowed."""

    def __init__(self, order_id: str, current_status: str, action_type: str) -> None:
        self.order_id = order_id
        self.current_status = current_status
        self.action_type = action_type

        # Build a helpful message listing allowed actions from this status
        allowed = STATE_TRANSITIONS.get(current_status, {})
        if allowed:
            allowed_list = ", ".join(
                f"{act}→{tgt}" for act, tgt in sorted(allowed.items())
            )
            hint = f"Allowed from '{current_status}': {allowed_list}"
        else:
            hint = f"Status '{current_status}' is terminal — no actions allowed."

        super().__init__(
            f"Cannot execute '{action_type}' on order '{order_id}': "
            f"current status is '{current_status}'. {hint}"
        )


# ── Public API ────────────────────────────────────────────────────────────────


def get_next_state(current_status: str, action_type: str) -> str | None:
    """Return the target status for a given transition, or None if not allowed.

    Args:
        current_status: e.g. "pending_review", "escalated"
        action_type: e.g. "approve_order", "freeze_order"

    Returns:
        The target status string, or None if the transition is not allowed.

    Examples:
        >>> get_next_state("pending_review", "escalate_order")
        "escalated"
        >>> get_next_state("frozen", "approve_order")
        None
    """
    transitions = STATE_TRANSITIONS.get(current_status)
    if transitions is None:
        return None
    return transitions.get(action_type)


def is_transition_allowed(current_status: str, action_type: str) -> bool:
    """Check whether a state transition is allowed.

    Args:
        current_status: e.g. "pending_review"
        action_type: e.g. "approve_order"

    Returns:
        True if the transition is valid, False otherwise.

    Examples:
        >>> is_transition_allowed("pending_review", "approve_order")
        True
        >>> is_transition_allowed("frozen", "approve_order")
        False
    """
    transitions = STATE_TRANSITIONS.get(current_status)
    if transitions is None:
        return False
    return action_type in transitions


def validate_state_transition(
    order_id: str,
    current_status: str,
    action_type: str,
) -> str:
    """Validate that *action_type* can be applied to *current_status*.

    Args:
        order_id: The PurchaseOrder ID (for error messages).
        current_status: The current status of the PurchaseOrder.
        action_type: One of approve_order | reject_order | escalate_order | freeze_order.

    Returns:
        The target status (e.g. "approved", "rejected", …).

    Raises:
        InvalidStateTransitionError: If the transition is not allowed.
    """
    target_status = get_next_state(current_status, action_type)
    if target_status is None:
        raise InvalidStateTransitionError(order_id, current_status, action_type)
    return target_status
