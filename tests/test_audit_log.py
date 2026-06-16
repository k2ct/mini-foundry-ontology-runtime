"""
Test: ActionAuditLog integrity.

Verifies that:
1. Every successful action writes an audit log with correct before/after state
2. Every failed action writes an audit log with success=False
3. Audit logs are immutable and append-only
4. All required fields (★ fields from spec) are populated
"""

import json

from tests.conftest import (
    seed_supplier,
    seed_order,
    seed_risk_signal,
    seed_policy,
)


class TestAuditLog:
    """Tests for ActionAuditLog integrity."""

    def test_successful_action_writes_complete_audit_log(self, client, db_session):
        """A successful action must produce a complete audit log entry."""
        seed_supplier(db_session, id="supplier_aud1")
        order = seed_order(
            db_session, id="PO-AUD1", supplier_id="supplier_aud1",
            amount=30000.0, status="pending_review",
        )
        risk = seed_risk_signal(
            db_session, id="risk_aud1", order_id=order.id,
            signal_type="low_amount", severity="low",
        )
        policy = seed_policy(
            db_session, id="policy_aud1",
            title="Test Policy", content="Test policy content.",
            policy_type="approval_rule",
        )
        db_session.commit()

        response = client.post("/actions/execute", json={
            "action_type": "approve_order",
            "order_id": "PO-AUD1",
            "actor": "user:test_actor",
            "reason": "Testing audit log completeness",
            "evidence_ids": ["risk_aud1", "policy_aud1"],
        })

        assert response.status_code == 200, response.text
        data = response.json()
        audit_log_id = data["audit_log_id"]

        # Verify audit log in DB
        from app.ontology.models import ActionAuditLog
        log = db_session.query(ActionAuditLog).filter(
            ActionAuditLog.id == audit_log_id
        ).first()
        assert log is not None

        # Check all required fields (★ fields from spec)
        assert log.action_type == "approve_order"
        assert log.object_id == "PO-AUD1"
        assert log.actor == "user:test_actor"
        assert log.reason is not None
        assert log.evidence_ids is not None
        assert log.before_state is not None
        assert log.after_state is not None
        assert log.timestamp is not None
        assert log.success is True
        assert log.error_message is None

        # Verify before/after states are correct
        before = json.loads(log.before_state)
        after = json.loads(log.after_state)
        assert before.get("status") == "pending_review"
        assert after.get("status") == "approved"

        # Verify evidence IDs are preserved
        evidence = json.loads(log.evidence_ids)
        assert "risk_aud1" in evidence
        assert "policy_aud1" in evidence

    def test_failed_action_writes_audit_log_with_error(self, client, db_session):
        """A failed action must write an audit log with success=False and error message."""
        seed_supplier(db_session, id="supplier_aud2")
        seed_risk_signal(
            db_session, id="risk_aud2", order_id="PO-AUD2",
            signal_type="low_amount", severity="low",
        )
        seed_policy(db_session, id="policy_aud2", title="p", content="c", policy_type="approval_rule")
        order = seed_order(
            db_session, id="PO-AUD2", supplier_id="supplier_aud2",
            amount=30000.0, status="rejected",  # terminal state
        )
        db_session.commit()

        response = client.post("/actions/execute", json={
            "action_type": "approve_order",
            "order_id": "PO-AUD2",
            "actor": "user:test_actor",
            "reason": "This should fail — rejected is terminal",
            "evidence_ids": ["risk_aud2", "policy_aud2"],
        })

        assert response.status_code == 422, response.text

        # Verify failure audit log exists
        from app.ontology.models import ActionAuditLog
        logs = (
            db_session.query(ActionAuditLog)
            .filter(ActionAuditLog.object_id == "PO-AUD2")
            .order_by(ActionAuditLog.timestamp.desc())
            .all()
        )
        assert len(logs) >= 1

        failure_log = logs[0]
        assert failure_log.success is False
        assert failure_log.action_type == "approve_order"
        assert failure_log.actor == "user:test_actor"
        assert failure_log.error_message is not None
        assert len(failure_log.error_message) > 0

    def test_audit_logs_are_append_only(self, client, db_session):
        """Multiple actions on the same order should produce multiple audit logs with unique IDs."""
        seed_supplier(db_session, id="supplier_aud3")
        seed_risk_signal(
            db_session, id="risk_aud3a", order_id="PO-AUD3",
            signal_type="low_amount", severity="low",
        )
        seed_policy(db_session, id="policy_aud3a", title="p", content="c", policy_type="approval_rule")
        order = seed_order(
            db_session, id="PO-AUD3", supplier_id="supplier_aud3",
            amount=10000.0, status="pending_review",
        )
        db_session.commit()

        # First: a successful approve
        resp1 = client.post("/actions/execute", json={
            "action_type": "approve_order",
            "order_id": "PO-AUD3",
            "actor": "user:manager",
            "reason": "Approve low-risk order",
            "evidence_ids": ["risk_aud3a", "policy_aud3a"],
        })
        assert resp1.status_code == 200

        # Now freeze the approved order
        seed_risk_signal(
            db_session, id="risk_aud3b", order_id="PO-AUD3",
            signal_type="critical", severity="critical",
        )
        seed_policy(db_session, id="policy_aud3b", title="p", content="c", policy_type="supplier_compliance")
        db_session.commit()

        resp2 = client.post("/actions/execute", json={
            "action_type": "freeze_order",
            "order_id": "PO-AUD3",
            "actor": "user:compliance",
            "reason": "Issue found, must freeze",
            "evidence_ids": ["risk_aud3b", "policy_aud3b"],
        })
        assert resp2.status_code == 200

        # Check accumulated logs
        from app.ontology.models import ActionAuditLog
        logs = (
            db_session.query(ActionAuditLog)
            .filter(ActionAuditLog.object_id == "PO-AUD3")
            .order_by(ActionAuditLog.timestamp.asc())
            .all()
        )

        assert len(logs) >= 2

        # Audit log IDs should be unique
        audit_ids = [log.id for log in logs]
        assert len(audit_ids) == len(set(audit_ids)), "Audit log IDs must be unique"

        # First log: approve from pending_review
        assert logs[0].action_type == "approve_order"
        assert logs[0].success is True

        # Second log: freeze from approved
        assert logs[1].action_type == "freeze_order"
        assert logs[1].success is True

    def test_timeline_includes_audit_logs(self, client, db_session):
        """The timeline endpoint should include all audit logs."""
        seed_supplier(db_session, id="supplier_aud4")
        order = seed_order(
            db_session, id="PO-AUD4", supplier_id="supplier_aud4",
            amount=30000.0, status="pending_review",
        )
        seed_risk_signal(
            db_session, id="risk_aud4", order_id=order.id,
            signal_type="low_amount", severity="low",
        )
        seed_policy(
            db_session, id="policy_aud4", title="Test Policy",
            content="Test content.", policy_type="approval_rule",
        )
        db_session.commit()

        # Execute an action
        client.post("/actions/execute", json={
            "action_type": "approve_order",
            "order_id": "PO-AUD4",
            "actor": "user:admin",
            "reason": "Approve for timeline test",
            "evidence_ids": ["risk_aud4", "policy_aud4"],
        })

        # Query timeline
        response = client.get(f"/orders/PO-AUD4/timeline")
        assert response.status_code == 200, response.text
        data = response.json()

        # Timeline should include audit logs
        assert "action_audit_logs" in data
        assert len(data["action_audit_logs"]) >= 1

        # The audit log in the timeline should have the correct fields
        audit_log = data["action_audit_logs"][0]
        assert audit_log["action_type"] == "approve_order"
        assert audit_log["success"] is True

        # The unified timeline should include an action_audit_log event
        events = data.get("timeline", [])
        action_events = [e for e in events if e["event_type"] == "action_audit_log"]
        assert len(action_events) >= 1
        # Verify the event has the enhanced fields (title, ref_id)
        event = action_events[0]
        assert "title" in event, "Timeline event should have 'title'"
        assert "ref_id" in event, "Timeline event should have 'ref_id'"
        assert event["title"] == "Action 执行: approve_order"
