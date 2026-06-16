"""
Test: AgentRun MUST NOT modify PurchaseOrder.status.

This is a hard design constraint (硬性要求):
The agent produces suggestions stored in AgentRun records.
Only the Action Runtime can change order status.
"""

from tests.conftest import (
    seed_supplier,
    seed_order,
    seed_risk_signal,
    seed_policy,
)


class TestAgentCannotModifyOrder:
    """Tests verifying that agent analysis does not mutate order status."""

    def test_agent_analyze_does_not_change_order_status(self, client, db_session):
        """POST /agent/analyze/{order_id} should NOT change PurchaseOrder.status."""
        supplier = seed_supplier(db_session, id="supplier_g1")
        order = seed_order(
            db_session, id="PO-G01", supplier_id=supplier.id,
            amount=150000.0, status="pending_review",
        )
        seed_risk_signal(
            db_session, id="risk_g01", order_id=order.id,
            signal_type="high_amount", severity="high",
        )
        seed_policy(
            db_session, id="policy_g01",
            title="Escalation Threshold",
            content="Orders over 100,000 CNY must be escalated.",
            policy_type="amount_threshold",
        )
        db_session.commit()

        original_status = order.status

        # Run agent analysis (uses MockLLMAgent since DEEPSEEK_API_KEY is empty)
        response = client.post(f"/agent/analyze/{order.id}")

        assert response.status_code == 200, response.text
        data = response.json()

        # Verify the agent produced a suggestion
        assert data["agent_run_id"] is not None
        assert data["suggested_action"] is not None

        # CRITICAL: order_status_unchanged must be True
        assert data["order_status_unchanged"] is True, (
            "Agent MUST NOT change order status! order_status_unchanged should be True"
        )

        # Verify order status in DB is unchanged
        db_session.refresh(order)
        assert order.status == original_status, (
            f"Agent changed order status from '{original_status}' to '{order.status}'! "
            "This is a hard constraint violation."
        )

    def test_mock_agent_suggests_escalate_for_high_amount(self, client, db_session):
        """Mock agent should suggest escalate_order for amounts > 100,000 CNY."""
        supplier = seed_supplier(db_session, id="supplier_g2")
        order = seed_order(
            db_session, id="PO-G02", supplier_id=supplier.id,
            amount=150000.0, status="pending_review",
        )
        seed_risk_signal(
            db_session, id="risk_g02", order_id=order.id,
            signal_type="high_amount", severity="high",
        )
        seed_policy(
            db_session, id="policy_g02",
            title="Escalation Threshold",
            content="Orders over 100,000 CNY must be escalated.",
            policy_type="amount_threshold",
        )
        db_session.commit()

        response = client.post(f"/agent/analyze/{order.id}")
        assert response.status_code == 200, response.text
        data = response.json()

        # Mock agent rule: amount > 100k → escalate_order
        assert data["suggested_action"] == "escalate_order", (
            f"Expected 'escalate_order' but got '{data['suggested_action']}'"
        )

    def test_mock_agent_suggests_freeze_for_blacklisted(self, client, db_session):
        """Mock agent should suggest freeze_order for blacklisted suppliers."""
        supplier = seed_supplier(
            db_session, id="supplier_g3",
            name="Blacklisted Vendor", status="blacklisted",
        )
        order = seed_order(
            db_session, id="PO-G03", supplier_id=supplier.id,
            amount=50000.0, status="pending_review",
        )
        seed_risk_signal(
            db_session, id="risk_g03", order_id=order.id,
            signal_type="blacklisted_supplier", severity="critical",
        )
        seed_policy(
            db_session, id="policy_g03",
            title="Blacklist Policy",
            content="Blacklisted suppliers must be frozen.",
            policy_type="supplier_compliance",
        )
        db_session.commit()

        response = client.post(f"/agent/analyze/{order.id}")
        assert response.status_code == 200, response.text
        data = response.json()

        # Mock agent rule: blacklisted → freeze_order
        assert data["suggested_action"] == "freeze_order", (
            f"Expected 'freeze_order' but got '{data['suggested_action']}'"
        )

    def test_agent_run_is_persisted(self, client, db_session):
        """The agent analysis result should be persisted as an AgentRun record."""
        supplier = seed_supplier(db_session, id="supplier_g4")
        order = seed_order(
            db_session, id="PO-G04", supplier_id=supplier.id,
            amount=30000.0, status="pending_review",
        )
        seed_risk_signal(
            db_session, id="risk_g04", order_id=order.id,
            signal_type="low_amount", severity="low",
        )
        seed_policy(
            db_session, id="policy_g04",
            title="Low Risk Approve",
            content="Low risk orders can be approved.",
            policy_type="approval_rule",
        )
        db_session.commit()

        response = client.post(f"/agent/analyze/{order.id}")
        assert response.status_code == 200, response.text
        data = response.json()

        # Verify AgentRun exists in DB
        from app.ontology.models import AgentRun
        agent_run = db_session.query(AgentRun).filter(
            AgentRun.id == data["agent_run_id"]
        ).first()
        assert agent_run is not None
        assert agent_run.order_id == order.id
        assert agent_run.suggested_action is not None

    def test_agent_analyze_nonexistent_order_returns_404(self, client, db_session):
        """Analyzing a non-existent order should return 404."""
        response = client.post("/agent/analyze/PO-NONEXISTENT")
        assert response.status_code == 404
