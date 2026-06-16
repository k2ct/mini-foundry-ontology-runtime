"""
Test: Invalid state changes are rejected.

Verifies that:
1. Terminal states (rejected, frozen) cannot be changed
2. Approved orders cannot be approved/rejected/escalated (only frozen)
3. Escalated orders cannot be escalated again (only approved/rejected/frozen)
4. Invalid action types are rejected
5. PO-005 (pre-frozen) cannot be changed
"""

from tests.conftest import (
    seed_supplier,
    seed_order,
    seed_risk_signal,
    seed_policy,
)


class TestInvalidStateChange:
    """Tests for invalid state transitions."""

    def test_cannot_change_approved_order_except_freeze(self, client, db_session):
        """An approved order can only be frozen, not approved/rejected/escalated."""
        seed_supplier(db_session, id="supplier_inv1")
        seed_risk_signal(
            db_session, id="risk_inv1", order_id="PO-INV1",
            signal_type="low_amount", severity="low",
        )
        seed_policy(db_session, id="policy_inv1", title="p", content="c", policy_type="approval_rule")
        order = seed_order(
            db_session, id="PO-INV1", supplier_id="supplier_inv1",
            amount=30000.0, status="approved",
        )
        db_session.commit()

        # These should fail on approved
        for action in ["approve_order", "reject_order", "escalate_order"]:
            response = client.post("/actions/execute", json={
                "action_type": action,
                "order_id": "PO-INV1",
                "actor": "user:admin",
                "reason": f"Try {action} on approved order",
                "evidence_ids": ["risk_inv1", "policy_inv1"],
            })
            assert response.status_code == 422, (
                f"Expected 422 for '{action}' on approved order, got {response.status_code}"
            )

        # But freeze should work on approved
        response = client.post("/actions/execute", json={
            "action_type": "freeze_order",
            "order_id": "PO-INV1",
            "actor": "user:admin",
            "reason": "Freeze approved order after issue found",
            "evidence_ids": ["risk_inv1", "policy_inv1"],
        })
        assert response.status_code == 200, f"Expected 200 for freeze on approved, got {response.status_code}"

    def test_cannot_change_rejected_order(self, client, db_session):
        """A rejected order cannot be transitioned (terminal)."""
        seed_supplier(db_session, id="supplier_inv2")
        seed_risk_signal(
            db_session, id="risk_inv2", order_id="PO-INV2",
            signal_type="missing_document", severity="high",
        )
        seed_policy(db_session, id="policy_inv2", title="p", content="c", policy_type="document_rule")
        order = seed_order(
            db_session, id="PO-INV2", supplier_id="supplier_inv2",
            amount=30000.0, status="rejected",
        )
        db_session.commit()

        response = client.post("/actions/execute", json={
            "action_type": "approve_order",
            "order_id": "PO-INV2",
            "actor": "user:admin",
            "reason": "Try to approve a rejected order",
            "evidence_ids": ["risk_inv2", "policy_inv2"],
        })

        assert response.status_code == 422
        db_session.refresh(order)
        assert order.status == "rejected"

    def test_cannot_escalate_already_escalated_order(self, client, db_session):
        """An escalated order can be approved/rejected/frozen but not escalated again."""
        seed_supplier(db_session, id="supplier_inv3")
        seed_risk_signal(
            db_session, id="risk_inv3", order_id="PO-INV3",
            signal_type="high_amount", severity="high",
        )
        seed_policy(db_session, id="policy_inv3", title="p", content="c", policy_type="amount_threshold")
        order = seed_order(
            db_session, id="PO-INV3", supplier_id="supplier_inv3",
            amount=30000.0, status="escalated",
        )
        db_session.commit()

        # escalate_order should fail on escalated
        response = client.post("/actions/execute", json={
            "action_type": "escalate_order",
            "order_id": "PO-INV3",
            "actor": "user:admin",
            "reason": "Try to escalate an escalated order",
            "evidence_ids": ["risk_inv3", "policy_inv3"],
        })

        assert response.status_code == 422
        db_session.refresh(order)
        assert order.status == "escalated"

        # But approve should work on escalated
        response2 = client.post("/actions/execute", json={
            "action_type": "approve_order",
            "order_id": "PO-INV3",
            "actor": "user:director",
            "reason": "After escalation review, approved",
            "evidence_ids": ["risk_inv3", "policy_inv3"],
        })
        assert response2.status_code == 200
        db_session.refresh(order)
        assert order.status == "approved"

    def test_cannot_change_frozen_order(self, client, db_session):
        """A frozen order cannot be transitioned (terminal, PO-005 scenario)."""
        seed_supplier(db_session, id="supplier_inv4")
        seed_risk_signal(
            db_session, id="risk_inv4", order_id="PO-INV4",
            signal_type="critical", severity="critical",
        )
        seed_policy(db_session, id="policy_inv4", title="p", content="c", policy_type="supplier_compliance")
        order = seed_order(
            db_session, id="PO-INV4", supplier_id="supplier_inv4",
            amount=200000.0, status="frozen",
        )
        db_session.commit()

        # All actions should fail on frozen order
        for action in ["approve_order", "reject_order", "escalate_order", "freeze_order"]:
            response = client.post("/actions/execute", json={
                "action_type": action,
                "order_id": "PO-INV4",
                "actor": "user:admin",
                "reason": f"Try {action} on frozen order",
                "evidence_ids": ["risk_inv4", "policy_inv4"],
            })
            assert response.status_code == 422, (
                f"Expected 422 for '{action}' on frozen order, got {response.status_code}"
            )

        db_session.refresh(order)
        assert order.status == "frozen"

    def test_invalid_action_type_rejected(self, client, db_session):
        """An unknown action type should be rejected with 422."""
        seed_supplier(db_session, id="supplier_inv5")
        seed_risk_signal(
            db_session, id="risk_inv5", order_id="PO-INV5",
            signal_type="low_amount", severity="low",
        )
        seed_policy(db_session, id="policy_inv5", title="p", content="c", policy_type="approval_rule")
        order = seed_order(
            db_session, id="PO-INV5", supplier_id="supplier_inv5",
            amount=30000.0, status="pending_review",
        )
        db_session.commit()

        response = client.post("/actions/execute", json={
            "action_type": "delete_order",  # not a valid action
            "order_id": "PO-INV5",
            "actor": "user:admin",
            "reason": "Invalid action type test",
            "evidence_ids": ["risk_inv5", "policy_inv5"],
        })

        assert response.status_code == 422, (
            f"Expected 422 for invalid action type, got {response.status_code}"
        )

    def test_invalid_evidence_prefix_rejected(self, client, db_session):
        """Evidence IDs with invalid prefixes should be rejected."""
        seed_supplier(db_session, id="supplier_inv6")
        order = seed_order(
            db_session, id="PO-INV6", supplier_id="supplier_inv6",
            amount=30000.0, status="pending_review",
        )
        db_session.commit()

        response = client.post("/actions/execute", json={
            "action_type": "approve_order",
            "order_id": "PO-INV6",
            "actor": "user:admin",
            "reason": "Test",
            "evidence_ids": ["invalid_prefix_123"],
        })

        # Should fail validation — evidence_ids must start with risk_/policy_/agent_run_
        assert response.status_code == 422

    def test_frozen_order_remains_unchanged_after_rejected_actions(self, client, db_session):
        """Simulate PO-005: pre-frozen order rejects all state change attempts."""
        seed_supplier(
            db_session,
            id="supplier_inv7",
            name="PO-005 Supplier",
            risk_level="critical",
        )
        seed_risk_signal(
            db_session, id="risk_inv7", order_id="PO-005",
            signal_type="critical", severity="critical",
        )
        seed_policy(db_session, id="policy_inv7", title="p", content="c", policy_type="supplier_compliance")
        order = seed_order(
            db_session, id="PO-005", supplier_id="supplier_inv7",
            amount=200000.0, status="frozen",
        )
        db_session.commit()

        # Try all 4 actions on frozen PO-005
        for action in ["approve_order", "reject_order", "escalate_order", "freeze_order"]:
            response = client.post("/actions/execute", json={
                "action_type": action,
                "order_id": "PO-005",
                "actor": "user:admin",
                "reason": f"Attempt {action} on pre-frozen PO-005",
                "evidence_ids": ["risk_inv7", "policy_inv7"],
            })
            assert response.status_code == 422, (
                f"PO-005: expected 422 for '{action}' on frozen order, got {response.status_code}"
            )

        # PO-005 must still be frozen
        db_session.refresh(order)
        assert order.status == "frozen"
