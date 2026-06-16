"""
Test: approve_order action execution.

Verifies that:
1. approve_order transitions pending_review → approved
2. The action is recorded in action_audit_logs
3. Evidence validation works correctly
4. Failed actions (invalid state / bad evidence) write audit logs
"""

from tests.conftest import (
    seed_supplier,
    seed_order,
    seed_risk_signal,
    seed_policy,
    seed_approval_task,
)


class TestApproveOrder:
    """Tests for the approve_order action."""

    def test_approve_pending_order_succeeds(self, client, db_session):
        """A pending_review order with low risk can be approved."""
        seed_supplier(db_session, id="supplier_a1", name="Good Supplier")
        order = seed_order(
            db_session,
            id="PO-A01",
            supplier_id="supplier_a1",
            amount=30000.0,
            status="pending_review",
        )
        risk = seed_risk_signal(
            db_session,
            id="risk_a01",
            order_id=order.id,
            signal_type="low_amount",
            severity="low",
        )
        policy = seed_policy(
            db_session,
            id="policy_a01",
            title="Low Risk Approval Rule",
            content="Low risk orders can be directly approved.",
            policy_type="approval_rule",
        )
        db_session.commit()

        response = client.post("/actions/execute", json={
            "action_type": "approve_order",
            "order_id": "PO-A01",
            "actor": "user:admin",
            "reason": "Low risk, all documents complete",
            "evidence_ids": ["risk_a01", "policy_a01"],
        })

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["success"] is True
        assert data["before_state"] == "pending_review"
        assert data["after_state"] == "approved"
        assert data["audit_log_id"] != ""

        # Verify order status changed in DB
        db_session.refresh(order)
        assert order.status == "approved"

    def test_approve_without_evidence_fails(self, client, db_session):
        """Approving without evidence_ids is now rejected (evidence cannot be empty)."""
        seed_supplier(db_session, id="supplier_a2")
        order = seed_order(
            db_session,
            id="PO-A02",
            supplier_id="supplier_a2",
            amount=10000.0,
            status="pending_review",
        )
        db_session.commit()

        response = client.post("/actions/execute", json={
            "action_type": "approve_order",
            "order_id": "PO-A02",
            "actor": "user:admin",
            "reason": "Approving without evidence",
            "evidence_ids": [],
        })

        # Should fail because evidence_ids cannot be empty
        assert response.status_code == 422, response.text

        # Order status should NOT have changed
        db_session.refresh(order)
        assert order.status == "pending_review"

    def test_approve_already_approved_order_fails(self, client, db_session):
        """Cannot approve an order that is already approved."""
        seed_supplier(db_session, id="supplier_a3")
        seed_risk_signal(
            db_session, id="risk_a03", order_id="PO-A03",
            signal_type="low_amount", severity="low",
        )
        seed_policy(db_session, id="policy_a03", title="p", content="c", policy_type="approval_rule")
        order = seed_order(
            db_session,
            id="PO-A03",
            supplier_id="supplier_a3",
            amount=10000.0,
            status="approved",  # already in terminal state (only freeze allowed)
        )
        db_session.commit()

        response = client.post("/actions/execute", json={
            "action_type": "approve_order",
            "order_id": "PO-A03",
            "actor": "user:admin",
            "reason": "Trying to re-approve",
            "evidence_ids": ["risk_a03", "policy_a03"],
        })

        assert response.status_code == 422, response.text
        data = response.json()
        assert "Cannot execute" in data["detail"] or "not allowed" in str(data["detail"]).lower()

    def test_approve_failure_writes_audit_log(self, client, db_session):
        """Even failed approve attempts must write an audit log."""
        seed_supplier(db_session, id="supplier_a4")
        seed_risk_signal(
            db_session, id="risk_a04", order_id="PO-A04",
            signal_type="low_amount", severity="low",
        )
        seed_policy(db_session, id="policy_a04", title="p", content="c", policy_type="approval_rule")
        order = seed_order(
            db_session,
            id="PO-A04",
            supplier_id="supplier_a4",
            amount=10000.0,
            status="rejected",  # terminal state
        )
        db_session.commit()

        response = client.post("/actions/execute", json={
            "action_type": "approve_order",
            "order_id": "PO-A04",
            "actor": "user:admin",
            "reason": "This should fail — rejected is terminal",
            "evidence_ids": ["risk_a04", "policy_a04"],
        })

        assert response.status_code == 422

        # Verify audit log was written despite failure
        from app.ontology.models import ActionAuditLog
        logs = (
            db_session.query(ActionAuditLog)
            .filter(ActionAuditLog.object_id == "PO-A04")
            .all()
        )
        assert len(logs) >= 1
        assert logs[0].success is False

    def test_approve_nonexistent_order_fails(self, client, db_session):
        """Approving a non-existent order should fail with audit log."""
        seed_risk_signal(
            db_session, id="risk_a05", order_id="PO-001",
            signal_type="low_amount", severity="low",
        )
        seed_policy(db_session, id="policy_a05", title="p", content="c", policy_type="approval_rule")
        db_session.commit()

        response = client.post("/actions/execute", json={
            "action_type": "approve_order",
            "order_id": "PO-NONEXISTENT",
            "actor": "user:admin",
            "reason": "Should fail",
            "evidence_ids": ["risk_a05", "policy_a05"],
        })

        assert response.status_code == 422

        # Verify failure audit log
        from app.ontology.models import ActionAuditLog
        logs = (
            db_session.query(ActionAuditLog)
            .filter(ActionAuditLog.object_id == "PO-NONEXISTENT")
            .all()
        )
        assert len(logs) >= 1
        assert logs[0].success is False

    def test_agent_actor_cannot_execute_actions(self, client, db_session):
        """Actors with 'agent:' prefix are forbidden from executing actions."""
        seed_supplier(db_session, id="supplier_a6")
        seed_risk_signal(
            db_session, id="risk_a06", order_id="PO-A06",
            signal_type="low_amount", severity="low",
        )
        seed_policy(db_session, id="policy_a06", title="p", content="c", policy_type="approval_rule")
        order = seed_order(
            db_session, id="PO-A06", supplier_id="supplier_a6",
            amount=10000.0, status="pending_review",
        )
        db_session.commit()

        response = client.post("/actions/execute", json={
            "action_type": "approve_order",
            "order_id": "PO-A06",
            "actor": "agent:deepseek",  # forbidden prefix
            "reason": "Agent trying to bypass",
            "evidence_ids": ["risk_a06", "policy_a06"],
        })

        # Should fail — agent actors cannot execute state changes
        # Returns 403 (forbidden actor) instead of 422 because the actor
        # validation now happens inside the Action Runtime (which also
        # writes a failure audit log, unlike Pydantic-level validation).
        assert response.status_code == 403, (
            f"Expected 403 for agent actor, got {response.status_code}: {response.text}"
        )

        # Order status unchanged
        db_session.refresh(order)
        assert order.status == "pending_review"

        # Verify failure audit log was written for the agent attempt
        from app.ontology.models import ActionAuditLog
        logs = (
            db_session.query(ActionAuditLog)
            .filter(ActionAuditLog.object_id == "PO-A06")
            .all()
        )
        assert len(logs) >= 1
        assert logs[0].success is False
        assert logs[0].error_message is not None
        assert "agent" in (logs[0].error_message or "").lower() or "READ-ONLY" in (logs[0].error_message or "")
