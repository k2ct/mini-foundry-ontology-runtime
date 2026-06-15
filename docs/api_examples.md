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

## 6. Swagger UI（交互式测试）

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
