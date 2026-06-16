"""
Test: freeze_order action execution.

Verifies that:
1. freeze_order transitions pending_review → frozen
2. Approved orders can be frozen (new transition: approved → frozen)
3. Blacklisted suppliers trigger freeze
4. Critical risk signals trigger freeze
5. Audit logs are written correctly
"""

from tests.conftest import (
    seed_supplier,
    seed_order,
    seed_risk_signal,
    seed_policy,
)


class TestFreezeOrder:
    """Tests for the freeze_order action."""

    def test_freeze_blacklisted_supplier_order(self, client, db_session):
        """An order from a blacklisted supplier should be frozen."""
        seed_supplier(
            db_session,
            id="supplier_f1",
            name="Blacklisted Corp",
            risk_level="critical",
            status="blacklisted",
        )
        order = seed_order(
            db_session,
            id="PO-F01",
            supplier_id="supplier_f1",
            amount=80000.0,
            status="pending_review",
        )
        risk = seed_risk_signal(
            db_session,
            id="risk_f01",
            order_id=order.id,
            signal_type="blacklisted_supplier",
            severity="critical",
            description="Supplier is on the blacklist",
        )
        policy = seed_policy(
            db_session,
            id="policy_f01",
            title="Blacklisted Supplier Policy",
            content="Orders from blacklisted suppliers must be frozen immediately.",
            policy_type="supplier_compliance",
        )
        db_session.commit()

        response = client.post("/actions/execute", json={
            "action_type": "freeze_order",
            "order_id": "PO-F01",
            "actor": "user:compliance_officer",
            "reason": "Supplier is blacklisted — immediate freeze required",
            "evidence_ids": ["risk_f01", "policy_f01"],
        })

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["success"] is True
        assert data["before_state"] == "pending_review"
        assert data["after_state"] == "frozen"

        # Verify order status
        db_session.refresh(order)
        assert order.status == "frozen"

    def test_freeze_approved_order_succeeds(self, client, db_session):
        """An approved order can be frozen if issues are found (new transition)."""
        seed_supplier(db_session, id="supplier_f1b")
        seed_risk_signal(
            db_session, id="risk_f1b", order_id="PO-F1B",
            signal_type="blacklisted_supplier", severity="critical",
        )
        seed_policy(db_session, id="policy_f1b", title="p", content="c", policy_type="supplier_compliance")
        order = seed_order(
            db_session, id="PO-F1B", supplier_id="supplier_f1b",
            amount=50000.0, status="approved",
        )
        db_session.commit()

        # approved → frozen is now valid
        response = client.post("/actions/execute", json={
            "action_type": "freeze_order",
            "order_id": "PO-F1B",
            "actor": "user:compliance",
            "reason": "Post-approval issue discovered — must freeze",
            "evidence_ids": ["risk_f1b", "policy_f1b"],
        })

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["success"] is True
        assert data["before_state"] == "approved"
        assert data["after_state"] == "frozen"

        db_session.refresh(order)
        assert order.status == "frozen"

    def test_freeze_critical_risk_order(self, client, db_session):
        """An order with critical risk signals should be frozen."""
        seed_supplier(db_session, id="supplier_f2")
        order = seed_order(
            db_session,
            id="PO-F02",
            supplier_id="supplier_f2",
            amount=500000.0,
            status="pending_review",
        )
        risk = seed_risk_signal(
            db_session,
            id="risk_f02",
            order_id=order.id,
            signal_type="abnormal_frequency",
            severity="critical",
            description="Abnormal purchasing frequency detected",
        )
        policy = seed_policy(
            db_session,
            id="policy_f02",
            title="Fraud Detection Policy",
            content="Critical risk signals require immediate freeze.",
            policy_type="approval_rule",
        )
        db_session.commit()

        response = client.post("/actions/execute", json={
            "action_type": "freeze_order",
            "order_id": "PO-F02",
            "actor": "system:fraud_detection",
            "reason": "Critical risk: abnormal frequency detected",
            "evidence_ids": ["risk_f02", "policy_f02"],
        })

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["success"] is True
        assert data["after_state"] == "frozen"

    def test_freeze_already_frozen_order_fails(self, client, db_session):
        """Cannot freeze an order that is already frozen (terminal state)."""
        seed_supplier(db_session, id="supplier_f3")
        seed_risk_signal(
            db_session, id="risk_f03", order_id="PO-F03",
            signal_type="critical", severity="critical",
        )
        seed_policy(db_session, id="policy_f03", title="p", content="c", policy_type="supplier_compliance")
        order = seed_order(
            db_session,
            id="PO-F03",
            supplier_id="supplier_f3",
            amount=100000.0,
            status="frozen",
        )
        db_session.commit()

        response = client.post("/actions/execute", json={
            "action_type": "freeze_order",
            "order_id": "PO-F03",
            "actor": "user:admin",
            "reason": "Try to freeze again",
            "evidence_ids": ["risk_f03", "policy_f03"],
        })

        assert response.status_code == 422
        db_session.refresh(order)
        assert order.status == "frozen"

    def test_freeze_order_from_rejected_fails(self, client, db_session):
        """Cannot freeze a rejected order (terminal state)."""
        seed_supplier(db_session, id="supplier_f4")
        seed_risk_signal(
            db_session, id="risk_f04", order_id="PO-F04",
            signal_type="missing_document", severity="high",
        )
        seed_policy(db_session, id="policy_f04", title="p", content="c", policy_type="document_rule")
        order = seed_order(
            db_session,
            id="PO-F04",
            supplier_id="supplier_f4",
            amount=100000.0,
            status="rejected",
        )
        db_session.commit()

        response = client.post("/actions/execute", json={
            "action_type": "freeze_order",
            "order_id": "PO-F04",
            "actor": "user:admin",
            "reason": "Try to freeze a rejected order",
            "evidence_ids": ["risk_f04", "policy_f04"],
        })

        assert response.status_code == 422
        db_session.refresh(order)
        assert order.status == "rejected"

    def test_freeze_failure_writes_audit_log(self, client, db_session):
        """Failed freeze attempts must still write an audit log."""
        seed_risk_signal(
            db_session, id="risk_f05", order_id="PO-001",
            signal_type="critical", severity="critical",
        )
        seed_policy(db_session, id="policy_f05", title="p", content="c", policy_type="supplier_compliance")
        db_session.commit()

        response = client.post("/actions/execute", json={
            "action_type": "freeze_order",
            "order_id": "PO-NONEXISTENT",
            "actor": "user:admin",
            "reason": "Should fail — order does not exist",
            "evidence_ids": ["risk_f05", "policy_f05"],
        })

        assert response.status_code == 422

        from app.ontology.models import ActionAuditLog
        logs = (
            db_session.query(ActionAuditLog)
            .filter(ActionAuditLog.object_id == "PO-NONEXISTENT")
            .all()
        )
        assert len(logs) >= 1
        assert logs[0].success is False
