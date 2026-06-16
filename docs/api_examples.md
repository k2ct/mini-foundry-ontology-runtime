# API 调用示例

> 所有示例基于 `http://127.0.0.1:8000`，启动服务后可以直接在浏览器或终端测试。

---

## 前置条件

```powershell
cd F:\mini-foundry-ontology-runtime
conda activate .\.conda
python scripts\reset_db.py
python scripts\seed_data.py
uvicorn app.main:app --reload
```

---

## 1. Health Check

### GET /health

```bash
curl -s http://127.0.0.1:8000/health | python -m json.tool
```

**Response:**
```json
{
    "status": "ok",
    "service": "mini-foundry-ontology-runtime"
}
```

---

## 2. 供应商

### GET /suppliers — 供应商列表

```bash
curl -s http://127.0.0.1:8000/suppliers | python -m json.tool
```

**Response:**
```json
[
    {
        "id": "supplier_001",
        "name": "恒信办公设备有限公司",
        "risk_level": "low",
        "status": "active",
        "created_at": "2026-06-15T10:00:00"
    },
    {
        "id": "supplier_002",
        "name": "云擎数据中心解决方案",
        "risk_level": "medium",
        "status": "active",
        "created_at": "2026-06-15T10:00:00"
    },
    {
        "id": "supplier_003",
        "name": "鑫达原材料供应链",
        "risk_level": "high",
        "status": "blacklisted",
        "created_at": "2026-06-15T10:00:00"
    },
    {
        "id": "supplier_004",
        "name": "快捷办公用品批发",
        "risk_level": "medium",
        "status": "active",
        "created_at": "2026-06-15T10:00:00"
    }
]
```

### GET /suppliers/{supplier_id} — 单个供应商

```bash
curl -s http://127.0.0.1:8000/suppliers/supplier_003 | python -m json.tool
```

**Response:**
```json
{
    "id": "supplier_003",
    "name": "鑫达原材料供应链",
    "risk_level": "high",
    "status": "blacklisted",
    "created_at": "2026-06-15T10:00:00"
}
```

---

## 3. 采购订单

### GET /orders — 订单列表

```bash
# 全部订单
curl -s http://127.0.0.1:8000/orders | python -m json.tool

# 按状态过滤
curl -s "http://127.0.0.1:8000/orders?status=pending_review" | python -m json.tool
curl -s "http://127.0.0.1:8000/orders?status=frozen" | python -m json.tool
```

**Response（全部订单）:**
```json
[
    {
        "id": "PO-001",
        "supplier_id": "supplier_001",
        "amount": 50000.0,
        "currency": "CNY",
        "description": "办公设备采购 — 笔记本电脑及显示器",
        "status": "pending_review",
        "created_at": "2026-06-15T10:00:00",
        "updated_at": "2026-06-15T10:00:00"
    },
    {
        "id": "PO-002",
        "supplier_id": "supplier_002",
        "amount": 150000.0,
        "currency": "CNY",
        "description": "服务器设备采购 — 机架式服务器及网络交换机",
        "status": "pending_review",
        "created_at": "2026-06-15T10:00:00",
        "updated_at": "2026-06-15T10:00:00"
    }
]
```

### GET /orders/{order_id} — 订单详情（含嵌套数据）

```bash
# PO-001：低风险订单（用于测试 approve_order）
curl -s http://127.0.0.1:8000/orders/PO-001 | python -m json.tool

# PO-002：高金额订单（用于测试 escalate_order）
curl -s http://127.0.0.1:8000/orders/PO-002 | python -m json.tool

# PO-003：黑名单供应商订单（用于测试 freeze_order）
curl -s http://127.0.0.1:8000/orders/PO-003 | python -m json.tool

# PO-004：资料缺失订单（用于测试 reject_order）
curl -s http://127.0.0.1:8000/orders/PO-004 | python -m json.tool

# PO-005：已冻结订单（用于测试非法状态变更）
curl -s http://127.0.0.1:8000/orders/PO-005 | python -m json.tool
```

**Response（PO-002，高金额订单）:**
```json
{
    "id": "PO-002",
    "supplier_id": "supplier_002",
    "amount": 150000.0,
    "currency": "CNY",
    "description": "服务器设备采购 — 机架式服务器及网络交换机",
    "status": "pending_review",
    "created_at": "2026-06-15T10:00:00",
    "updated_at": "2026-06-15T10:00:00",
    "supplier": {
        "id": "supplier_002",
        "name": "云擎数据中心解决方案",
        "risk_level": "medium",
        "status": "active",
        "created_at": "2026-06-15T10:00:00"
    },
    "risk_signals": [
        {
            "id": "risk_002",
            "order_id": "PO-002",
            "signal_type": "high_amount",
            "severity": "high",
            "description": "订单金额 150000 元，超过 100000 元升级审批阈值",
            "created_at": "2026-06-15T10:00:00"
        }
    ],
    "approval_tasks": [
        {
            "id": "task_PO-002",
            "order_id": "PO-002",
            "status": "open",
            "assignee": null,
            "created_at": "2026-06-15T10:00:00",
            "updated_at": "2026-06-15T10:00:00"
        }
    ],
    "agent_runs": []
}
```

---

## 4. 风险信号

### GET /risk-signals — 风险信号列表

```bash
# 全部风险信号
curl -s http://127.0.0.1:8000/risk-signals | python -m json.tool

# 按订单过滤
curl -s "http://127.0.0.1:8000/risk-signals?order_id=PO-002" | python -m json.tool

# 按严重程度过滤
curl -s "http://127.0.0.1:8000/risk-signals?severity=critical" | python -m json.tool
```

**Response（按 severity=critical 过滤）:**
```json
[
    {
        "id": "risk_003",
        "order_id": "PO-003",
        "signal_type": "blacklisted_supplier",
        "severity": "critical",
        "description": "供应商 supplier_003 已被列入黑名单",
        "created_at": "2026-06-15T10:00:00"
    },
    {
        "id": "risk_005",
        "order_id": "PO-005",
        "signal_type": "critical",
        "severity": "critical",
        "description": "订单已被冻结，存在严重合规风险",
        "created_at": "2026-06-15T10:00:00"
    }
]
```

### GET /risk-signals/{risk_id} — 单个风险信号

```bash
curl -s http://127.0.0.1:8000/risk-signals/risk_003 | python -m json.tool
```

---

## 5. 政策片段

### GET /policies — 政策片段列表

```bash
# 全部政策
curl -s http://127.0.0.1:8000/policies | python -m json.tool

# 按类型过滤
curl -s "http://127.0.0.1:8000/policies?policy_type=amount_threshold" | python -m json.tool
curl -s "http://127.0.0.1:8000/policies?policy_type=supplier_compliance" | python -m json.tool
```

**Response:**
```json
[
    {
        "id": "policy_001",
        "title": "高金额订单升级审批规则",
        "content": "金额超过 100000 元的采购订单需要升级审批...",
        "policy_type": "amount_threshold",
        "created_at": "2026-06-15T10:00:00"
    },
    {
        "id": "policy_002",
        "title": "黑名单供应商冻结规则",
        "content": "黑名单供应商相关的采购订单必须立即冻结...",
        "policy_type": "supplier_compliance",
        "created_at": "2026-06-15T10:00:00"
    }
]
```

### GET /policies/{policy_id} — 单个政策片段

```bash
curl -s http://127.0.0.1:8000/policies/policy_001 | python -m json.tool
```

---

## 6. Agent 智能体分析（Phase 2）

### POST /agent/analyze/{order_id} — 分析订单风险

```bash
# 分析 PO-002（高金额订单 → 建议 escalate_order）
curl -s -X POST http://127.0.0.1:8000/agent/analyze/PO-002 | python -m json.tool
```

**Response（Mock Agent）:**
```json
{
    "agent_run_id": "agent_run_a1b2c3d4",
    "order_id": "PO-002",
    "risk_level": "high",
    "suggested_action": "escalate_order",
    "reason": "订单金额 150000 元，超过 100000 元升级审批阈值，需要升级审批。",
    "evidence_ids": ["risk_002", "policy_001", "policy_002", "policy_003", "policy_004"],
    "confidence": 0.95,
    "status": "success",
    "error_message": null,
    "order_status_unchanged": true,
    "model": "mock"
}
```

> **关键约束**: `order_status_unchanged: true` 确认 Agent 没有修改 PurchaseOrder.status。

### Response Variations（真实 LLM vs Fallback）

**有 DeepSeek API Key 时（status=success，真实 LLM 调用）:**

```json
{
    "agent_run_id": "agent_run_x1y2z3w4",
    "order_id": "PO-002",
    "risk_level": "medium",
    "suggested_action": "escalate_order",
    "reason": "订单金额为150,000元，超过100,000元阈值，建议升级审批。",
    "evidence_ids": ["risk_002", "policy_001"],
    "confidence": 0.85,
    "status": "success",
    "error_message": null,
    "order_status_unchanged": true,
    "model": "deepseek-v4-flash"
}
```

**无 API Key 或 API 不可达时（status=fallback，自动降级到规则分析器）:**

```json
{
    "agent_run_id": "agent_run_a1b2c3d4",
    "order_id": "PO-002",
    "risk_level": "high",
    "suggested_action": "escalate_order",
    "reason": "订单金额 150000 元，超过 100000 元升级审批阈值，需要升级审批。",
    "evidence_ids": ["risk_002", "policy_001", "policy_002", "policy_003", "policy_004"],
    "confidence": 0.95,
    "status": "fallback",
    "error_message": null,
    "order_status_unchanged": true,
    "model": "mock"
}
```

> **关键区别：** `status` 字段区分 `"success"`（真实 LLM）和 `"fallback"`（规则降级）；`model` 字段区分 `"deepseek-v4-flash"` 和 `"mock"`。两种情况下 `suggested_action` 均为 `escalate_order`，`order_status_unchanged` 均为 `true`——Agent 的行为边界在两种模式下完全一致。

### GET /agent/runs — 查询分析历史

```bash
# 查询 PO-002 的所有分析记录
curl -s "http://127.0.0.1:8000/agent/runs?order_id=PO-002" | python -m json.tool
```

### GET /agent/runs/{run_id} — 查询单条分析

```bash
curl -s http://127.0.0.1:8000/agent/runs/agent_run_a1b2c3d4 | python -m json.tool
```

---

## 7. Action 执行（Phase 2）

### POST /actions/execute — 执行状态变更

**这是 PurchaseOrder.status 的唯一变更入口。**

```bash
# 执行 escalate_order
curl -s -X POST http://127.0.0.1:8000/actions/execute \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": "PO-002",
    "action_type": "escalate_order",
    "actor": "user:risk_manager",
    "reason": "订单金额超 100000 元升级阈值，Agent 建议升级审批。",
    "evidence_ids": ["risk_002", "policy_001"]
  }' | python -m json.tool
```

**Response（成功）:**
```json
{
    "success": true,
    "action_type": "escalate_order",
    "order_id": "PO-002",
    "before_state": "pending_review",
    "after_state": "escalated",
    "audit_log_id": "audit_PO-002_20260615230000000000",
    "message": "Action 'escalate_order' executed on 'PO-002': pending_review → escalated"
}
```

**Response（失败 — 非法状态变更）:**
```json
{
    "detail": "Cannot execute 'approve_order' on order 'PO-005': current status is 'frozen'. Status 'frozen' is terminal — no actions allowed."
}
```

### Actor 约束

- `user:*` 前缀 — 人类用户操作（如 `user:risk_manager`）
- `system:*` 前缀 — 系统自动化操作（如 `system:fraud_detection`）
- `agent:*` 前缀 — **禁止**（Agent 只能建议，不能执行）

```bash
# 以下请求会被拒绝（agent 不能执行 Action）
curl -s -X POST http://127.0.0.1:8000/actions/execute \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": "PO-001",
    "action_type": "approve_order",
    "actor": "agent:deepseek",
    "reason": "Agent trying to change state",
    "evidence_ids": ["risk_001"]
  }'
# → 422: Actor 'agent:deepseek' is forbidden
```

### 四个 Action 对应关系

| Action | 允许从 | 目标状态 |
|--------|--------|----------|
| `approve_order` | `pending_review`, `escalated` | `approved` |
| `reject_order` | `pending_review`, `escalated` | `rejected` |
| `escalate_order` | `pending_review` | `escalated` |
| `freeze_order` | `pending_review`, `escalated`, `approved` | `frozen` |

---

## 8. 审计日志查询（Phase 2）

### GET /audit-logs — 审计日志列表

```bash
# 全部审计日志
curl -s http://127.0.0.1:8000/audit-logs | python -m json.tool

# 按订单过滤
curl -s "http://127.0.0.1:8000/audit-logs?order_id=PO-002" | python -m json.tool

# 只看失败的
curl -s "http://127.0.0.1:8000/audit-logs?success=false" | python -m json.tool

# 按 action 类型过滤
curl -s "http://127.0.0.1:8000/audit-logs?action_type=freeze_order" | python -m json.tool
```

**Response:**
```json
[
    {
        "id": "audit_PO-002_20260615230000000000",
        "action_type": "escalate_order",
        "object_id": "PO-002",
        "actor": "user:risk_manager",
        "reason": "订单金额超 100000 元升级阈值...",
        "evidence_ids": ["risk_002", "policy_001"],
        "before_state": "{\"status\": \"pending_review\"}",
        "after_state": "{\"status\": \"escalated\"}",
        "timestamp": "2026-06-15T23:00:00.000000",
        "success": true,
        "error_message": null
    }
]
```

### GET /audit-logs/{id} — 单条审计日志

```bash
curl -s http://127.0.0.1:8000/audit-logs/audit_PO-002_20260615230000000000 | python -m json.tool
```

---

## 9. Timeline 时间线查询（Phase 2）

### GET /orders/{order_id}/timeline — 完整审计时间线

返回订单的所有事件（订单创建 → 风险检测 → Agent 分析 → Action 执行），按时间排序。

```bash
curl -s http://127.0.0.1:8000/orders/PO-002/timeline | python -m json.tool
```

**Response 结构:**
```json
{
    "order": { "id": "PO-002", "status": "escalated", ... },
    "supplier": { "id": "supplier_002", "name": "云擎数据中心解决方案", ... },
    "risk_signals": [ ... ],
    "related_policies": [ ... ],
    "agent_runs": [ ... ],
    "action_audit_logs": [ ... ],
    "approval_tasks": [ ... ],
    "timeline": [
        {
            "timestamp": "2026-06-15T15:11:04",
            "event_type": "order_created",
            "title": "订单创建",
            "description": "采购订单 PO-002 创建 — 金额 150,000.00 CNY",
            "ref_id": "PO-002",
            "details": {
                "supplier_id": "supplier_002",
                "amount": 150000.0,
                "currency": "CNY",
                "initial_status": "pending_review"
            }
        },
        {
            "timestamp": "2026-06-15T15:11:04",
            "event_type": "risk_signal",
            "title": "风险信号: high_amount",
            "description": "[high] high_amount: 订单金额 150000 元，超过 100000 元升级审批阈值",
            "ref_id": "risk_002",
            "details": {
                "risk_signal_id": "risk_002",
                "signal_type": "high_amount",
                "severity": "high"
            }
        },
        {
            "timestamp": "2026-06-15T23:49:02",
            "event_type": "agent_run",
            "title": "Agent 分析: escalate_order",
            "description": "Agent 建议 'escalate_order' (风险等级: high, 置信度: 0.95)",
            "ref_id": "agent_run_a1b2c3d4",
            "details": {
                "agent_run_id": "agent_run_a1b2c3d4",
                "suggested_action": "escalate_order",
                "risk_level": "high",
                "confidence": 0.95,
                "status": "success"
            }
        },
        {
            "timestamp": "2026-06-15T23:49:02",
            "event_type": "action_audit_log",
            "title": "Action 执行: escalate_order",
            "description": "[成功] escalate_order by user:risk_manager — 订单金额超 100000 元升级阈值...",
            "ref_id": "audit_PO-002_20260615230000000000",
            "details": {
                "audit_log_id": "audit_PO-002_20260615230000000000",
                "action_type": "escalate_order",
                "actor": "user:risk_manager",
                "success": true,
                "before_state": "{\"status\": \"pending_review\"}",
                "after_state": "{\"status\": \"escalated\"}"
            }
        }
    ]
}
```

### PolicyChunk 追溯逻辑

`related_policies` 中的 PolicyChunk 通过以下方式间接关联到订单：

1. 从 `AgentRun.evidence_ids` 中提取 `policy_xxx` ID
2. 从 `ActionAuditLog.evidence_ids` 中提取 `policy_xxx` ID
3. 查询对应的 PolicyChunk 记录返回
4. 如果没有 policy evidence，返回**全部** PolicyChunk 作为 fallback

### 容错设计

- `evidence_ids` 在数据库中存储为 JSON 字符串，但在 **API 响应中已自动解析为 `list[str]`**（数组格式）
- 数据库中的 JSON 字符串解析失败时自动跳过，不会让接口崩溃
- 如果 `AgentRun` / `ActionAuditLog` 为空，timeline 仍然返回：
  - `order`、`supplier`、`risk_signals`、`related_policies`
  - 空的 `agent_runs` / `action_audit_logs` 列表
  - 基础 `timeline_events`（至少包含 `order_created` 和风险信号事件）
- `order_id` 不存在时返回 404

---

## 10. Swagger UI（交互式测试）

启动服务后，直接访问 http://127.0.0.1:8000/docs 即可通过浏览器交互式调用所有 API，无需手动编写 curl 命令。

---

## 5 个测试场景速查

| 订单 ID | 场景 | 关键特征 | 目标 Action |
|---------|------|----------|-------------|
| `PO-001` | 普通低风险订单 | 金额 50000，供应商正常，低风险 | `approve_order` |
| `PO-002` | 高金额订单 | 金额 150000 > 100000 阈值 | `escalate_order` |
| `PO-003` | 黑名单供应商 | 供应商 supplier_003 状态 blacklisted | `freeze_order` |
| `PO-004` | 资料缺失 | 缺少供应商资质文件 | `reject_order` |
| `PO-005` | 已冻结订单 | 状态 frozen，不可执行常规操作 | 测试非法状态变更被拒绝 |
