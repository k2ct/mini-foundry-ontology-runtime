"""
Test: escalate_order action execution.

Verifies that:
1. escalate_order transitions pending_review → escalated
2. High-amount orders can be escalated
3. Evidence validation works (empty / fake IDs rejected)
4. Audit logs are written for both success and failure
5. Approval tasks are synced
"""

from tests.conftest import (
    seed_supplier,
    seed_order,
    seed_risk_signal,
    seed_policy,
)


class TestEscalateOrder:
    """Tests for the escalate_order action."""

    def test_escalate_pending_order_succeeds(self, client, db_session):
        """A pending_review order with high amount should be escalated."""
        seed_supplier(db_session, id="supplier_e1")
        order = seed_order(
            db_session,
            id="PO-E01",
            supplier_id="supplier_e1",
            amount=150000.0,
            status="pending_review",
        )
        risk = seed_risk_signal(
            db_session,
            id="risk_e01",
            order_id=order.id,
            signal_type="high_amount",
            severity="high",
            description="Amount exceeds 100k threshold",
        )
        policy = seed_policy(
            db_session,
            id="policy_e01",
            title="Amount Threshold Policy",
            content="Orders over 100,000 CNY must be escalated.",
            policy_type="amount_threshold",
        )
        db_session.commit()

        response = client.post("/actions/execute", json={
            "action_type": "escalate_order",
            "order_id": "PO-E01",
            "actor": "system:deepseek_agent",
            "reason": "Amount 150000 exceeds escalation threshold of 100000",
            "evidence_ids": ["risk_e01", "policy_e01"],
        })

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["success"] is True
        assert data["before_state"] == "pending_review"
        assert data["after_state"] == "escalated"
        assert data["audit_log_id"] != ""

        # Verify order status changed
        db_session.refresh(order)
        assert order.status == "escalated"

    def test_escalate_with_invalid_evidence_fails(self, client, db_session):
        """Escalating with non-existent evidence IDs should fail."""
        seed_supplier(db_session, id="supplier_e2")
        order = seed_order(
            db_session,
            id="PO-E02",
            supplier_id="supplier_e2",
            amount=200000.0,
            status="pending_review",
        )
        db_session.commit()

        response = client.post("/actions/execute", json={
            "action_type": "escalate_order",
            "order_id": "PO-E02",
            "actor": "user:admin",
            "reason": "Should fail due to fake evidence",
            "evidence_ids": ["risk_fake_999", "policy_nonexistent"],
        })

        assert response.status_code == 422, response.text
        data = response.json()
        assert "evidence" in str(data["detail"]).lower() or "exist" in str(data["detail"]).lower()

        # Order status should NOT have changed
        db_session.refresh(order)
        assert order.status == "pending_review"

        # Failure audit log should have been written
        from app.ontology.models import ActionAuditLog
        logs = (
            db_session.query(ActionAuditLog)
            .filter(ActionAuditLog.object_id == "PO-E02")
            .all()
        )
        assert len(logs) >= 1
        assert logs[0].success is False

    def test_escalate_already_escalated_order_fails(self, client, db_session):
        """Cannot escalate an order that is already escalated (escalate_order not allowed from escalated)."""
        seed_supplier(db_session, id="supplier_e3")
        seed_risk_signal(
            db_session, id="risk_e03", order_id="PO-E03",
            signal_type="high_amount", severity="high",
        )
        seed_policy(db_session, id="policy_e03", title="p", content="c", policy_type="amount_threshold")
        order = seed_order(
            db_session,
            id="PO-E03",
            supplier_id="supplier_e3",
            amount=150000.0,
            status="escalated",
        )
        db_session.commit()

        response = client.post("/actions/execute", json={
            "action_type": "escalate_order",
            "order_id": "PO-E03",
            "actor": "user:admin",
            "reason": "Try to escalate again",
            "evidence_ids": ["risk_e03", "policy_e03"],
        })

        # escalate_order is not allowed from escalated state
        assert response.status_code == 422

        # Order status unchanged
        db_session.refresh(order)
        assert order.status == "escalated"

    def test_escalate_syncs_approval_tasks(self, client, db_session):
        """Escalating an order should close open approval tasks."""
        seed_supplier(db_session, id="supplier_e4")
        order = seed_order(
            db_session,
            id="PO-E04",
            supplier_id="supplier_e4",
            amount=120000.0,
            status="pending_review",
        )
        seed_risk_signal(db_session, id="risk_e04", order_id=order.id, signal_type="high_amount", severity="high")
        seed_policy(db_session, id="policy_e04", title="p", content="c", policy_type="amount_threshold")
        from tests.conftest import seed_approval_task
        task = seed_approval_task(
            db_session,
            id="task_e04",
            order_id=order.id,
            status="open",
        )
        db_session.commit()

        response = client.post("/actions/execute", json={
            "action_type": "escalate_order",
            "order_id": "PO-E04",
            "actor": "user:admin",
            "reason": "Escalate with task sync",
            "evidence_ids": ["risk_e04", "policy_e04"],
        })

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["success"] is True

        # Check task was synced
        db_session.refresh(task)
        assert task.status == "escalated"

    def test_escalate_failure_writes_audit_log(self, client, db_session):
        """Even failed escalate attempts must write an audit log."""
        seed_supplier(db_session, id="supplier_e5")
        seed_risk_signal(
            db_session, id="risk_e05", order_id="PO-E05",
            signal_type="low_amount", severity="low",
        )
        seed_policy(db_session, id="policy_e05", title="p", content="c", policy_type="amount_threshold")
        order = seed_order(
            db_session,
            id="PO-E05",
            supplier_id="supplier_e5",
            amount=10000.0,
            status="rejected",  # terminal state
        )
        db_session.commit()

        response = client.post("/actions/execute", json={
            "action_type": "escalate_order",
            "order_id": "PO-E05",
            "actor": "user:admin",
            "reason": "This should fail — rejected is terminal",
            "evidence_ids": ["risk_e05", "policy_e05"],
        })

        assert response.status_code == 422

        from app.ontology.models import ActionAuditLog
        logs = (
            db_session.query(ActionAuditLog)
            .filter(ActionAuditLog.object_id == "PO-E05")
            .all()
        )
        assert len(logs) >= 1
        assert logs[0].success is False

    def test_escalated_order_can_be_approved(self, client, db_session):
        """An escalated order can be approved after review (new transition)."""
        seed_supplier(db_session, id="supplier_e6")
        seed_risk_signal(
            db_session, id="risk_e06", order_id="PO-E06",
            signal_type="high_amount", severity="medium",
        )
        seed_policy(db_session, id="policy_e06", title="p", content="c", policy_type="approval_rule")
        order = seed_order(
            db_session,
            id="PO-E06",
            supplier_id="supplier_e6",
            amount=150000.0,
            status="escalated",
        )
        db_session.commit()

        # escalated → approved is now valid
        response = client.post("/actions/execute", json={
            "action_type": "approve_order",
            "order_id": "PO-E06",
            "actor": "user:director",
            "reason": "After escalation review, approved",
            "evidence_ids": ["risk_e06", "policy_e06"],
        })

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["success"] is True
        assert data["after_state"] == "approved"

        db_session.refresh(order)
        assert order.status == "approved"
