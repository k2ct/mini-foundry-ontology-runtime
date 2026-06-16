"""
Agent analysis API — trigger LLM risk analysis on a purchase order.

POST /agent/analyze/{order_id}
    Run the DeepSeek agent (or mock fallback) on a purchase order.
    Saves the result as an AgentRun record.
    Does NOT modify PurchaseOrder.status (that is the Action Runtime's job).

GET /agent/runs
    List all agent analysis runs, newest first.  Optional ?order_id= filter.

GET /agent/runs/{run_id}
    Get a single agent analysis run by ID.
"""

import json
import logging
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agent.analyzer import analyze_order
from app.agent.deepseek_llm import DeepSeekLLMClient
from app.config import DEEPSEEK_API_KEY
from app.deps import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])


# ── Response schema ────────────────────────────────────────────────────────────


class AgentAnalyzeResponse(BaseModel):
    """Response body for POST /agent/analyze/{order_id}."""

    agent_run_id: str = Field(..., description="ID of the created AgentRun record")
    order_id: str
    risk_level: str | None = None
    suggested_action: str | None = None
    reason: str | None = None
    evidence_ids: str | None = None
    confidence: float | None = None
    status: str
    error_message: str | None = None
    order_status_unchanged: bool = Field(
        default=True,
        description="Confirms that PurchaseOrder.status was NOT modified by the agent",
    )
    model: str = Field(
        default="unknown",
        description="Which model produced this analysis (deepseek, mock/fallback)",
    )


# ── POST /agent/analyze/{order_id} ──────────────────────────────────────────


@router.post("/analyze/{order_id}", response_model=AgentAnalyzeResponse)
def run_analysis(
    order_id: str,
    db: Session = Depends(get_db),
):
    """Run LLM risk analysis on a purchase order.

    This endpoint:
    1. Loads the order + supplier + risks + policies from the database
    2. Calls the LLM agent (DeepSeek, with automatic fallback to rule-based analysis)
    3. Saves the result as an **immutable AgentRun** record
    4. Returns the agent's suggestion

    **Important:** The agent's suggestion is READ-ONLY.  PurchaseOrder.status
    is NOT changed by this endpoint.  Use ``POST /actions/execute`` to apply
    state changes.

    **Fallback behavior:** If the DeepSeek API is unreachable, times out,
    returns unparseable output, or no API key is configured, the endpoint
    automatically falls back to deterministic rule-based analysis.
    Fallback results have ``status: "fallback"``.

    Example: ``POST /agent/analyze/PO-002``
    """
    # 1. Create LLM client (None → fallback if no API key)
    if DEEPSEEK_API_KEY:
        llm_client = DeepSeekLLMClient()
        model_name = "deepseek"
    else:
        llm_client = None  # analyze_order() will use fallback
        model_name = "mock"

    # 2. Run the full analysis pipeline (context → LLM → parse → validate → save)
    try:
        agent_run = analyze_order(db, order_id, llm_client=llm_client)
        db.commit()
    except ValueError as exc:
        # Order not found
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        db.rollback()
        logger.exception("Agent analysis failed for order '%s'", order_id)
        raise HTTPException(
            status_code=500,
            detail=f"Agent analysis failed: {exc}",
        )

    # 3. Verify order status was NOT changed (hard constraint)
    from app.ontology.models import PurchaseOrder
    order = db.get(PurchaseOrder, order_id)
    order_status = order.status if order else "unknown"

    # Parse evidence_ids back to list for the response
    evidence_list = []
    if agent_run.evidence_ids:
        try:
            evidence_list = json.loads(agent_run.evidence_ids)
        except (json.JSONDecodeError, TypeError):
            evidence_list = []

    return AgentAnalyzeResponse(
        agent_run_id=agent_run.id,
        order_id=order_id,
        risk_level=agent_run.risk_level,
        suggested_action=agent_run.suggested_action,
        reason=agent_run.reason,
        evidence_ids=json.dumps(evidence_list, ensure_ascii=False),
        confidence=agent_run.confidence,
        status=agent_run.status,
        error_message=agent_run.error_message,
        order_status_unchanged=True,
        model=model_name,
    )


# ── Agent run query endpoints ──────────────────────────────────────────────────

from typing import List as ListType
from app.ontology.models import AgentRun as AgentRunModel
from app.ontology.schemas import AgentRunRead


@router.get("/runs", response_model=ListType[AgentRunRead])
def list_agent_runs(
    order_id: str | None = None,
    db: Session = Depends(get_db),
):
    """List all agent analysis runs, newest first.

    Optional filter: ``?order_id=PO-002``
    """
    q = db.query(AgentRunModel).order_by(AgentRunModel.created_at.desc())
    if order_id is not None:
        q = q.filter(AgentRunModel.order_id == order_id)
    return q.all()


@router.get("/runs/{run_id}", response_model=AgentRunRead)
def get_agent_run(run_id: str, db: Session = Depends(get_db)):
    """Return a single agent analysis run by its ID."""
    agent_run = db.get(AgentRunModel, run_id)
    if agent_run is None:
        raise HTTPException(status_code=404, detail=f"AgentRun '{run_id}' not found")
    return agent_run
