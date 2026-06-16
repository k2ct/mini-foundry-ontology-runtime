# Phase 2 Test Cases

> 6 个测试类，共 34 个测试用例，覆盖 Agent、Action Runtime、Audit Log、状态机全部核心模块。

---

## 测试环境

- **数据库**: 内存 SQLite（`conftest.py` 中 `StaticPool` 保证隔离）
- **Agent**: MockLLMAgent（基于规则的 mock，不依赖 DeepSeek API）
- **客户端**: FastAPI `TestClient`（无需启动 uvicorn）
- **隔离**: 每个测试函数独立创建 schema，teardown 自动销毁

---

## 1. test_action_approve.py — 批准订单

### 1.1 test_approve_pending_order_succeeds

| 项目 | 内容 |
|------|------|
| **目标** | `PO-001` 可以 `approve_order`，状态 `pending_review → approved` |
| **输入** | `action_type=approve_order`, `order_id=PO-A01`, `actor=user:admin`, `evidence_ids=["risk_a01","policy_a01"]` |
| **预期状态变化** | `pending_review` → `approved` |
| **预期审计日志** | `success=True`, `action_type=approve_order`, `object_id=PO-A01`, `before_state` 含 `pending_review`, `after_state` 含 `approved` |
| **依赖** | `app/actions/runtime.py`, `app/actions/validators.py` |
| **DeepSeek 依赖** | 否（测试 Action Runtime，不涉及 Agent） |

### 1.2 test_approve_without_evidence_fails

| 项目 | 内容 |
|------|------|
| **目标** | `evidence_ids` 为空时拒绝请求 |
| **输入** | `evidence_ids=[]` |
| **预期状态变化** | 无（状态保持 `pending_review`） |
| **预期审计日志** | 可能写入 `success=False` 审计日志（取决于校验在哪个层级失败） |
| **依赖** | `app/actions/validators.py` |

### 1.3 test_approve_already_approved_order_fails

| 项目 | 内容 |
|------|------|
| **目标** | 已 `approved` 的订单不可再次 `approve_order` |
| **输入** | 订单状态 `approved`, `action_type=approve_order` |
| **预期状态变化** | 无（保持 `approved`） |
| **预期审计日志** | `success=False` |
| **依赖** | `app/actions/state_machine.py` |

### 1.4 test_approve_failure_writes_audit_log

| 项目 | 内容 |
|------|------|
| **目标** | 失败操作必须写入审计日志 |
| **输入** | 订单状态 `rejected`（terminal）, `action_type=approve_order` |
| **预期状态变化** | 无（保持 `rejected`） |
| **预期审计日志** | `success=False`, `error_message` 非空 |
| **依赖** | `app/actions/runtime.py` |

### 1.5 test_approve_nonexistent_order_fails

| 项目 | 内容 |
|------|------|
| **目标** | 不存在的订单 ID 返回 422 + 审计日志 |
| **输入** | `order_id=PO-NONEXISTENT` |
| **预期状态变化** | N/A |
| **预期审计日志** | `success=False`, `object_id=PO-NONEXISTENT` |
| **依赖** | `app/actions/runtime.py` |

### 1.6 test_agent_actor_cannot_execute_actions

| 项目 | 内容 |
|------|------|
| **目标** | `agent:*` 前缀的 actor 不能执行状态变更 |
| **输入** | `actor=agent:deepseek` |
| **预期状态变化** | 无（保持 `pending_review`） |
| **预期审计日志** | N/A（在 Actor 校验层拒绝） |
| **依赖** | `app/actions/validators.py` |

---

## 2. test_action_escalate.py — 升级审批

### 2.1 test_escalate_pending_order_succeeds

| 项目 | 内容 |
|------|------|
| **目标** | `PO-002` 可 `escalate_order`，状态 `pending_review → escalated` |
| **输入** | `action_type=escalate_order`, `order_id=PO-E01`, `actor=system:deepseek_agent`, `evidence_ids=["risk_e01","policy_e01"]` |
| **预期状态变化** | `pending_review` → `escalated` |
| **预期审计日志** | `success=True`, `after_state` 含 `escalated` |
| **依赖** | `app/actions/runtime.py` |
| **DeepSeek 依赖** | 否 |

### 2.2 test_escalate_with_invalid_evidence_fails

| 项目 | 内容 |
|------|------|
| **目标** | 虚假 `evidence_ids` 被拒绝，写入失败审计日志 |
| **输入** | `evidence_ids=["risk_fake_999","policy_nonexistent"]` |
| **预期状态变化** | 无 |
| **预期审计日志** | `success=False` |
| **依赖** | `app/actions/validators.py` |

### 2.3 test_escalate_already_escalated_order_fails

| 项目 | 内容 |
|------|------|
| **目标** | 已 `escalated` 的订单不可再次 `escalate_order` |
| **输入** | 状态 `escalated`, `action_type=escalate_order` |
| **预期状态变化** | 无 |
| **预期审计日志** | `success=False` |
| **依赖** | `app/actions/state_machine.py` |

### 2.4 test_escalate_syncs_approval_tasks

| 项目 | 内容 |
|------|------|
| **目标** | 升级时同步关闭关联审批任务 |
| **输入** | 含 `open` 状态 ApprovalTask 的订单 |
| **预期状态变化** | 订单 → `escalated`, 任务 `open` → `escalated` |
| **预期审计日志** | `success=True` |
| **依赖** | `app/actions/runtime.py` |

### 2.5 test_escalate_failure_writes_audit_log

| 项目 | 内容 |
|------|------|
| **目标** | terminal 状态订单升级失败写入审计日志 |
| **输入** | 状态 `rejected`, `action_type=escalate_order` |
| **预期审计日志** | `success=False` |
| **依赖** | `app/actions/runtime.py` |

### 2.6 test_escalated_order_can_be_approved

| 项目 | 内容 |
|------|------|
| **目标** | 已升级订单经审核后可批准（新状态机规则） |
| **输入** | 状态 `escalated`, `action_type=approve_order` |
| **预期状态变化** | `escalated` → `approved` |
| **预期审计日志** | `success=True` |
| **依赖** | `app/actions/state_machine.py` |

---

## 3. test_action_freeze.py — 冻结订单

### 3.1 test_freeze_blacklisted_supplier_order

| 项目 | 内容 |
|------|------|
| **目标** | `PO-003`（黑名单供应商）可 `freeze_order`，状态 → `frozen` |
| **输入** | `supplier.status=blacklisted`, `risk.severity=critical` |
| **预期状态变化** | `pending_review` → `frozen` |
| **预期审计日志** | `success=True` |
| **依赖** | `app/actions/runtime.py` |
| **DeepSeek 依赖** | 否 |

### 3.2 test_freeze_approved_order_succeeds

| 项目 | 内容 |
|------|------|
| **目标** | 已批准的订单可冻结（新状态机：approved → frozen） |
| **输入** | 状态 `approved`, `action_type=freeze_order` |
| **预期状态变化** | `approved` → `frozen` |
| **预期审计日志** | `success=True` |
| **依赖** | `app/actions/state_machine.py` |

### 3.3 test_freeze_critical_risk_order

| 项目 | 内容 |
|------|------|
| **目标** | `severity=critical` 的风险信号触发冻结 |
| **输入** | `risk.signal_type=abnormal_frequency`, `severity=critical` |
| **预期状态变化** | `pending_review` → `frozen` |
| **预期审计日志** | `success=True` |
| **依赖** | `app/actions/runtime.py` |

### 3.4 test_freeze_already_frozen_order_fails

| 项目 | 内容 |
|------|------|
| **目标** | `frozen` 是 terminal 状态，不可再次冻结 |
| **输入** | 状态 `frozen`, `action_type=freeze_order` |
| **预期状态变化** | 无 |
| **预期审计日志** | `success=False` |
| **依赖** | `app/actions/state_machine.py` |

### 3.5 test_freeze_order_from_rejected_fails

| 项目 | 内容 |
|------|------|
| **目标** | `rejected` 是 terminal 状态，不可冻结 |
| **输入** | 状态 `rejected`, `action_type=freeze_order` |
| **预期状态变化** | 无 |
| **预期审计日志** | `success=False` |
| **依赖** | `app/actions/state_machine.py` |

### 3.6 test_freeze_failure_writes_audit_log

| 项目 | 内容 |
|------|------|
| **目标** | 不存在的订单冻结失败也写审计日志 |
| **输入** | `order_id=PO-NONEXISTENT` |
| **预期审计日志** | `success=False`, `object_id=PO-NONEXISTENT` |
| **依赖** | `app/actions/runtime.py` |

---

## 4. test_invalid_state_change.py — 非法状态变更

### 4.1 test_cannot_change_approved_order_except_freeze

| 项目 | 内容 |
|------|------|
| **目标** | `approved` 订单只能被 freeze，不能 approve/reject/escalate |
| **输入** | 状态 `approved`, 依次尝试 4 种 action |
| **预期状态变化** | approve/reject/escalate → 422；freeze → 200 |
| **依赖** | `app/actions/state_machine.py` |

### 4.2 test_cannot_change_rejected_order

| 项目 | 内容 |
|------|------|
| **目标** | `rejected`（terminal）不可被任何操作改变 |
| **输入** | 状态 `rejected`, `action_type=approve_order` |
| **预期状态变化** | 无 |
| **依赖** | `app/actions/state_machine.py` |

### 4.3 test_cannot_escalate_already_escalated_order

| 项目 | 内容 |
|------|------|
| **目标** | `escalated` 不可再次 escalate，但可 approve/reject/freeze |
| **输入** | 状态 `escalated`, 先试 `escalate_order` → 422，再试 `approve_order` → 200 |
| **预期状态变化** | escalate → 拒绝; approve → `approved` |
| **依赖** | `app/actions/state_machine.py` |

### 4.4 test_cannot_change_frozen_order

| 项目 | 内容 |
|------|------|
| **目标** | `PO-005` 初始 `frozen`，所有 4 种 Action 均被拒绝 |
| **输入** | 状态 `frozen`, 依次 4 种 action |
| **预期状态变化** | 全部 422，状态保持 `frozen` |
| **预期审计日志** | 每个失败 Action 写入 `success=False` |
| **依赖** | `app/actions/state_machine.py` |

### 4.5 test_invalid_action_type_rejected

| 项目 | 内容 |
|------|------|
| **目标** | 非法 Action 类型在 Pydantic 层被拒绝 |
| **输入** | `action_type=delete_order` |
| **预期状态变化** | 无 |
| **依赖** | `app/actions/types.py` |

### 4.6 test_invalid_evidence_prefix_rejected

| 项目 | 内容 |
|------|------|
| **目标** | 无效前缀的 evidence ID 被拒绝 |
| **输入** | `evidence_ids=["invalid_prefix_123"]` |
| **预期状态变化** | 无 |
| **依赖** | `app/actions/validators.py` |

### 4.7 test_frozen_order_remains_unchanged_after_rejected_actions

| 项目 | 内容 |
|------|------|
| **目标** | PO-005 模拟：已冻结订单拒绝所有状态变更 |
| **输入** | `order_id=PO-005`, 状态 `frozen`, 依次 4 种 action |
| **预期状态变化** | 全部 422，`status` 保持 `frozen` |
| **依赖** | `app/actions/state_machine.py` |

---

## 5. test_agent_cannot_modify_order.py — Agent 不能修改订单

### 5.1 test_agent_analyze_does_not_change_order_status

| 项目 | 内容 |
|------|------|
| **目标** | `POST /agent/analyze/PO-G01` 后 `PurchaseOrder.status` 不变 |
| **输入** | 订单状态 `pending_review`, MockLLMAgent 分析 |
| **预期状态变化** | 无（`status` 保持 `pending_review`） |
| **预期审计日志** | AgentRun 创建成功，`order_status_unchanged=True` |
| **依赖** | `app/agent/mock_llm.py`, `app/api/agent_runs.py` |
| **DeepSeek 依赖** | 否（使用 MockLLMAgent） |

### 5.2 test_mock_agent_suggests_escalate_for_high_amount

| 项目 | 内容 |
|------|------|
| **目标** | 金额 > 100k 时 Mock Agent 建议 `escalate_order` |
| **输入** | `amount=150000`, `risk.signal_type=high_amount` |
| **预期 Agent 输出** | `suggested_action=escalate_order` |
| **DeepSeek 依赖** | 否 |

### 5.3 test_mock_agent_suggests_freeze_for_blacklisted

| 项目 | 内容 |
|------|------|
| **目标** | 黑名单供应商时 Mock Agent 建议 `freeze_order` |
| **输入** | `supplier.status=blacklisted`, `risk.severity=critical` |
| **预期 Agent 输出** | `suggested_action=freeze_order` |
| **DeepSeek 依赖** | 否 |

### 5.4 test_agent_run_is_persisted

| 项目 | 内容 |
|------|------|
| **目标** | Agent 分析结果持久化为 AgentRun 记录 |
| **输入** | 低风险订单 |
| **预期** | AgentRun 写入数据库，字段完整 |
| **DeepSeek 依赖** | 否 |

### 5.5 test_agent_analyze_nonexistent_order_returns_404

| 项目 | 内容 |
|------|------|
| **目标** | 不存在的订单返回 404 |
| **输入** | `order_id=PO-NONEXISTENT` |
| **预期** | HTTP 404 |
| **DeepSeek 依赖** | 否 |

---

## 6. test_audit_log.py — 审计日志完整性

### 6.1 test_successful_action_writes_complete_audit_log

| 项目 | 内容 |
|------|------|
| **目标** | 成功 Action 写入字段完整的审计日志 |
| **预期字段** | `action_type`, `object_id`, `actor`, `reason`, `evidence_ids`, `before_state`, `after_state`, `timestamp`, `success=True`, `error_message=null` |
| **依赖** | `app/actions/runtime.py` |

### 6.2 test_failed_action_writes_audit_log_with_error

| 项目 | 内容 |
|------|------|
| **目标** | 失败 Action 写入 `success=False` 且含 `error_message` |
| **输入** | 状态 `rejected`, `action_type=approve_order` |
| **预期** | `success=False`, `error_message` 非空 |
| **依赖** | `app/actions/runtime.py` |

### 6.3 test_audit_logs_are_append_only

| 项目 | 内容 |
|------|------|
| **目标** | 多次操作产生多条审计日志，ID 唯一 |
| **输入** | 先 approve，再 freeze |
| **预期** | 2 条审计日志，ID 不同 |
| **依赖** | `app/actions/runtime.py` |

### 6.4 test_timeline_includes_audit_logs

| 项目 | 内容 |
|------|------|
| **目标** | Timeline API 返回的 `action_audit_logs` 和 `timeline` 包含审计日志 |
| **预期** | `action_audit_logs` 数组非空，`timeline` 中有 `action_executed` 事件 |
| **依赖** | `app/audit/trace.py` |

---

## 运行测试

```powershell
cd F:\mini-foundry-ontology-runtime
conda activate .\.conda

# 运行全部测试
pytest tests/ -v

# 运行特定测试类
pytest tests/test_action_approve.py -v
pytest tests/test_agent_cannot_modify_order.py -v

# 查看覆盖率
pytest tests/ -v --tb=short
```

## DeepSeek 依赖说明

| 测试文件 | DeepSeek 依赖 |
|----------|---------------|
| `test_action_approve.py` | 否（测试 Action Runtime） |
| `test_action_escalate.py` | 否（测试 Action Runtime） |
| `test_action_freeze.py` | 否（测试 Action Runtime） |
| `test_invalid_state_change.py` | 否（测试状态机） |
| `test_agent_cannot_modify_order.py` | 否（使用 MockLLMAgent） |
| `test_audit_log.py` | 否（测试 AuditLogger） |

所有 `pytest` 测试均**不依赖真实 DeepSeek API**，可在无网络环境中运行。

### 可选真实 LLM 连通性测试

`scripts/test_deepseek_llm.py` 是**可选**的真实 DeepSeek LLM 连通性测试，**不纳入 pytest**：

```powershell
python scripts\test_deepseek_llm.py
```

该测试需要本地 `.env` 中配置 `DEEPSEEK_API_KEY`，验证：
- 最小化 LLM 调用（Test 1）
- 完整 analyze_order 流程（Test 2）
- Fallback 机制（Test 3）

> `verify_phase2.py`、`pytest`、`run_demo.py` 均不依赖真实 API Key，保证面试官即使没有 API Key 也能完整验收系统主链路。
