"""
Agent module — DeepSeek LLM integration for purchase order risk analysis.

Submodules:
    base           — LLMClient abstract + BaseAgent + AgentAnalysisResult
    deepseek_llm   — DeepSeekLLMClient (httpx-based, OpenAI-compatible)
    prompts        — System prompt templates for risk analysis
    mock_llm       — Deterministic mock LLM for testing / fallback
    analyzer       — Core pipeline: extract_json, validate, fallback, analyze_order
"""

from app.agent.base import BaseAgent, AgentAnalysisResult, LLMClient
from app.agent.deepseek_llm import (
    DeepSeekLLMClient,
    DeepSeekAPIError,
    DeepSeekTimeoutError,
    DeepSeekConnectionError,
)
from app.agent.mock_llm import MockLLMAgent
from app.agent.analyzer import (
    DeepSeekAgent,
    extract_json_from_text,
    validate_agent_output,
    fallback_analysis,
    analyze_order,
)

__all__ = [
    # Abstract
    "LLMClient",
    "BaseAgent",
    "AgentAnalysisResult",
    # DeepSeek
    "DeepSeekLLMClient",
    "DeepSeekAPIError",
    "DeepSeekTimeoutError",
    "DeepSeekConnectionError",
    # Mock
    "MockLLMAgent",
    # Analyzer
    "DeepSeekAgent",
    "extract_json_from_text",
    "validate_agent_output",
    "fallback_analysis",
    "analyze_order",
]
