"""
System prompts and user-prompt builders for the risk analysis agent.

Imported by ``app.agent.base.BaseAgent`` and its subclasses.
"""

import json
from typing import Any, Dict

# ──────────────────────────────────────────────────────────────────────────────
# System Prompt
# ──────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = r"""
你是一个企业采购风险审核系统的智能分析助手。你的职责是：

1. 分析采购订单的上下文信息（订单详情、供应商信息、风险信号、相关政策）
2. 综合评估风险等级（low / medium / high / critical）
3. 给出明确的行动建议（approve_order / reject_order / escalate_order / freeze_order）
4. 列出支撑你判断的证据 ID 列表（evidence_ids）
5. 给出置信度（0.0 ~ 1.0）

## 行动建议说明

| Action         | 适用场景                                              |
|----------------|-------------------------------------------------------|
| approve_order  | 低风险且材料完整，可以直接批准                          |
| reject_order   | 材料缺失或不合规，应予拒绝                              |
| escalate_order | 金额超阈值或存在不确定风险，需要升级审批                  |
| freeze_order   | 供应商已被列入黑名单或存在严重合规风险，必须立即冻结       |

## 输出要求

你必须**严格**按照以下 JSON 格式输出，不要包含任何额外的文字说明：

```json
{
    "risk_level": "low",
    "action": "approve_order",
    "reason": "基于以下证据做出的判断：...",
    "evidence_ids": ["risk_001", "policy_004"],
    "confidence": 0.85
}
```

## 注意事项

- evidence_ids 只能引用上下文中实际存在的 ID（risk_xxx / policy_xxx / agent_run_xxx）
- 如果对订单的判断不确定，置信度应该低于 0.6，并倾向选择 escalate_order
- 如果风险信号中包含 critical 级别，必须优先考虑 freeze_order 或 escalate_order
- 你的输出只是一个**建议**，不会直接修改任何业务数据
""".strip()


# ──────────────────────────────────────────────────────────────────────────────
# User Prompt Builder
# ──────────────────────────────────────────────────────────────────────────────

def build_user_prompt(context: Dict[str, Any]) -> str:
    """Build a structured user prompt from the order analysis context.

    Parameters
    ----------
    context : dict
        Must contain:
        - order: dict with order details
        - supplier: dict with supplier details
        - risk_signals: list of risk signal dicts
        - policies: list of policy chunk dicts
        - approval_tasks: list of approval task dicts (optional)
        - agent_runs: list of prior agent run dicts (optional)

    Returns
    -------
    str
        A formatted user prompt ready for the LLM.
    """
    parts: list[str] = []

    # ── Header ──────────────────────────────────────────────────────────
    order = context.get("order", {})
    order_id = order.get("id", "unknown")
    parts.append(f"## 采购订单分析请求\n\n请分析以下采购订单 `{order_id}` 的风险情况，并给出行动建议。\n")

    # ── Order ───────────────────────────────────────────────────────────
    parts.append("### 订单信息\n")
    parts.append(_format_dict(context.get("order", {})))

    # ── Supplier ────────────────────────────────────────────────────────
    supplier = context.get("supplier")
    if supplier:
        parts.append("\n### 供应商信息\n")
        parts.append(_format_dict(supplier))

    # ── Risk Signals ────────────────────────────────────────────────────
    risks = context.get("risk_signals", [])
    if risks:
        parts.append(f"\n### 风险信号（{len(risks)} 条）\n")
        for r in risks:
            parts.append(
                f"- **{r.get('id')}** [{r.get('severity', '?')}] "
                f"类型: {r.get('signal_type', '?')}"
            )
            desc = r.get("description")
            if desc:
                parts.append(f"  {desc}")

    # ── Policies ────────────────────────────────────────────────────────
    policies = context.get("policies", [])
    if policies:
        parts.append(f"\n### 相关政策（{len(policies)} 条）\n")
        for p in policies:
            parts.append(f"- **{p.get('id')}** — {p.get('title')}")
            content = p.get("content", "")
            parts.append(f"  {content}")

    # ── Approval Tasks ──────────────────────────────────────────────────
    tasks = context.get("approval_tasks", [])
    if tasks:
        parts.append(f"\n### 审批任务（{len(tasks)} 个）\n")
        for t in tasks:
            parts.append(
                f"- **{t.get('id')}** — 状态: {t.get('status')}, "
                f"负责人: {t.get('assignee', '未分配')}"
            )

    # ── Prior Agent Runs ────────────────────────────────────────────────
    prior_runs = context.get("agent_runs", [])
    if prior_runs:
        parts.append(f"\n### 历史分析记录（{len(prior_runs)} 条）\n")
        for run in prior_runs:
            parts.append(
                f"- **{run.get('id')}** — 建议: {run.get('suggested_action')}, "
                f"风险: {run.get('risk_level')}, 置信度: {run.get('confidence')}"
            )

    # ── Footer ──────────────────────────────────────────────────────────
    parts.append("\n---\n请给出你的分析结果（仅输出 JSON，不要包含其他内容）：")

    return "\n".join(parts)


def _format_dict(d: Dict[str, Any]) -> str:
    """Format a flat dict as key-value lines for the prompt."""
    lines: list[str] = []
    for k, v in d.items():
        if v is None:
            lines.append(f"- **{k}**: (无)")
        elif isinstance(v, (int, float, str, bool)):
            lines.append(f"- **{k}**: {v}")
        else:
            lines.append(f"- **{k}**: {json.dumps(v, ensure_ascii=False)}")
    return "\n".join(lines) if lines else "(无数据)"
