# Mini Foundry Ontology Action Runtime

> 企业采购风险审核 — Ontology 建模 + 智能体分析 + Action 校验 + 审计追溯

**Version:** 0.2.0  
**Status:** Phase 2 — Agent Analyzer + Action Runtime + Audit Logger + Timeline Query

---

## 项目简介

Mini Foundry Ontology Action Runtime 是一个面向企业采购风险审核场景的轻量级智能运行时。系统围绕 **采购订单（PurchaseOrder）** 构建 Ontology 知识模型，结合 LLM Agent 分析和 Action Runtime 状态机，实现从数据导入到审计追溯的完整闭环。

### 核心业务流程

```text
数据导入 → Ontology 建模 → 智能体分析 → Action 校验 → 状态变更 → 审计记录 → 可追溯查询
```

---

## Quick Verification（面试官最快验收）

项目提供**两类验收方式**，面试官可根据是否有 DeepSeek API Key 自由选择：

### 核心离线验收（无需 API Key，推荐首选）

在配置好环境后，运行以下三条命令即可完成全部核心验收：

```powershell
cd F:\mini-foundry-ontology-runtime
conda activate .\.conda

python scripts\verify_phase2.py
pytest
python scripts\run_demo.py
```

**预期结果：**

```text
=== PHASE 2 VERIFICATION PASSED ===  (53/53 checks)
=== pytest ===                        (34 passed)
=== Demo ===                          (7/7 PASS)
```

> 三条命令均使用内存数据库，**不需要启动服务**，**不依赖 DeepSeek API Key**，可在无网络环境下运行。

### 可选真实 LLM 验收（需要 DeepSeek API Key）

如果希望验证真实 DeepSeek LLM 接入效果，可额外运行：

```powershell
python scripts\test_deepseek_llm.py
```

> 该测试需要本地 `.env` 中配置 `DEEPSEEK_API_KEY`，详见下方 [Optional: Test Real DeepSeek LLM](#optional-test-real-deepseek-llm) 小节。

---

## 技术栈

| 组件 | 技术 |
|------|------|
| Web 框架 | FastAPI 0.100+ |
| ORM | SQLAlchemy 2.0+ |
| 数据校验 | Pydantic 2.0+ |
| 数据库 | SQLite（开发阶段），可平滑迁移至 PostgreSQL |
| LLM 集成 | DeepSeek API（Mock fallback 可用） |
| 异步服务器 | Uvicorn |
| 测试 | pytest + httpx |

---

## Design Highlights（设计亮点）

1. **Ontology-first 建模**：将供应商、订单、风险信号、政策、审批任务、AgentRun、ActionAuditLog 组织成可追溯的业务对象网络。每个实体有明确的状态枚举和关系映射，不是简单的 CRUD 表集合。

2. **Agent / Action 分层**：Agent 只生成 `AgentRun`（建议记录），**不能直接修改 `PurchaseOrder.status`**。状态变更的唯一入口是 Action Runtime。这一分层从根本上杜绝了 LLM 幻觉导致业务数据错误的风险。

3. **Action Runtime 统一入口**：所有状态变更必须经过 `POST /actions/execute`，经过 **Action 白名单 → 状态机 → Actor 校验 → Evidence 校验** 四层防线。

4. **审计闭环**：成功、失败、越权的 Action 全部写入 `ActionAuditLog`（append-only），包含 `before_state` / `after_state` 完整快照。失败时审计日志在返回错误前 commit，确保不被事务回滚丢失。

5. **可扩展性**：DeepSeek API 已封装，缺失 API Key 时自动 fallback 到规则分析器，不中断主链路。架构支持通过 Adapter / Connector / Webhook / Message Queue 对接真实 ERP / OA / 采购系统。

---

## 环境创建

项目使用 **Conda 独立环境**，环境目录为 `.conda/`。

### 1. 创建环境

```powershell
cd F:\mini-foundry-ontology-runtime

conda create --prefix .\.conda python=3.11 -y
```

### 2. 激活环境

```powershell
conda activate .\.conda
```

### 3. 安装依赖

```powershell
python -m pip install --upgrade pip

pip install -r requirements.txt
```

---

## 环境变量配置

```powershell
copy .env.example .env
```

编辑 `.env`，填入实际配置（开发阶段使用默认值即可）：

```env
DATABASE_URL=sqlite:///./data/mini_foundry.db
DEEPSEEK_API_KEY=your_api_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
APP_ENV=development
```

> ⚠️ **请勿在 `.env` 中提交真实 API Key。**

---

## Local Service Run（本地服务启动）

以下三条命令即可完成数据库初始化、示例数据导入和服务启动：

```powershell
cd F:\mini-foundry-ontology-runtime
conda activate .\.conda

python scripts\reset_db.py
python scripts\seed_data.py
uvicorn app.main:app --reload
```

启动后 API 文档入口：

| 入口 | URL |
|------|-----|
| Swagger UI | http://127.0.0.1:8000/docs |
| ReDoc | http://127.0.0.1:8000/redoc |
| OpenAPI JSON | http://127.0.0.1:8000/openapi.json |
| Health Check | http://127.0.0.1:8000/health |

> ⚠️ **如果 `/docs` 因 Swagger UI CDN 资源加载异常出现白屏，可使用 `/redoc` 或 `/openapi.json` 作为备用 API 文档入口。** 这不是系统问题，而是 Swagger UI 依赖的 CDN 静态资源在某些网络环境下无法加载。

各步骤的详细说明见下方。

---

## 初始化数据库

### 重置并重建数据库（推荐首次使用）

```powershell
python scripts\reset_db.py
```

### 仅初始化（如果数据库不存在）

```powershell
python scripts\init_db.py
```

---

## 导入示例数据

```powershell
python scripts\seed_data.py
```

示例数据包括：
- **4 个供应商**（含 1 个黑名单供应商）
- **5 个采购订单**（覆盖批准、升级、冻结、拒绝、非法状态变更场景）
- **5 条风险信号**（高金额、黑名单供应商、资料缺失、严重风险等）
- **4 条政策片段**（金额阈值、供应商合规、文件规则、批准规则）
- **每个待审核订单自动创建 1 个审批任务**

重复运行安全：已存在的记录会被自动跳过。

---

## 启动服务

### 日常启动

```powershell
cd F:\mini-foundry-ontology-runtime

conda activate .\.conda

uvicorn app.main:app --reload
```

### 备用启动（无需 Conda 激活）

```powershell
.\.conda\python.exe -m uvicorn app.main:app --reload
```

启动后访问：

- **Swagger UI:** http://127.0.0.1:8000/docs
- **ReDoc:** http://127.0.0.1:8000/redoc
- **Health Check:** http://127.0.0.1:8000/health

---

## 当前已实现功能（Phase 1 + Phase 2）

### Phase 1 — 基础查询 API

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/health` | 健康检查 |
| `GET` | `/suppliers` | 供应商列表 |
| `GET` | `/suppliers/{id}` | 供应商详情 |
| `GET` | `/orders` | 订单列表（支持 `?status=` 过滤） |
| `GET` | `/orders/{id}` | 订单详情（含供应商、风险信号、审批任务） |
| `GET` | `/risk-signals` | 风险信号列表（支持 `?order_id=` `?severity=` 过滤） |
| `GET` | `/risk-signals/{id}` | 风险信号详情 |
| `GET` | `/policies` | 政策片段列表（支持 `?policy_type=` 过滤） |
| `GET` | `/policies/{id}` | 政策片段详情 |

### Phase 2 — Agent 分析 + Action 执行 + 审计追溯

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/agent/analyze/{order_id}` | LLM 智能体分析订单风险（DeepSeek / Mock fallback） |
| `GET` | `/agent/runs` | 查询 AgentRun 历史记录（支持 `?order_id=` 过滤） |
| `GET` | `/agent/runs/{run_id}` | 查询单个 AgentRun 记录 |
| `POST` | `/actions/execute` | 执行 Action（approve / reject / escalate / freeze） |
| `GET` | `/orders/{order_id}/timeline` | 查询订单完整审计时间线 |
| `GET` | `/audit-logs` | 查询审计日志（支持 `?order_id=` `?action_type=` `?success=` 过滤） |
| `GET` | `/audit-logs/{id}` | 查询单个审计日志条目 |

### 数据模型（7 个实体）

`Supplier` → `PurchaseOrder` → `RiskSignal` / `ApprovalTask` / `AgentRun` / `ActionAuditLog` + `PolicyChunk`

---

## Recommended Demo Scenario: PO-002（推荐演示场景）

**PO-002** 是本系统的最佳演示订单，完整覆盖从风险检测到审计追溯的全链路。

### 场景说明

PO-002 是一个高金额采购订单（¥150,000），初始状态为 `pending_review`。其关联供应商为"云擎数据中心解决方案"（risk_level: medium），触发高金额风险信号（risk_002）。Agent 分析后建议 `escalate_order`（真实 LLM 与 fallback 均会识别为需要进一步审批），Action Runtime 执行后订单状态从 `pending_review` 变为 `escalated`，Timeline 可以追溯风险信号、政策依据、AgentRun 和 ActionAuditLog。

> **关于 risk_level 的说明：** 真实 DeepSeek LLM 可能返回 `risk_level: "medium"`，Mock Fallback 可能返回 `risk_level: "high"`。两者均不影响 Action Runtime 的状态控制——无论 risk_level 如何，核心建议 `escalate_order` 保持一致，订单状态变更路径不变。这是 Agent/Action 分层设计的优势：LLM 判断的细微差异不会传导到业务状态层。

### 推荐演示路径

| 步骤 | API | 说明 | 预期结果 |
|------|-----|------|----------|
| 1 | `GET /orders/PO-002` | 查看订单详情 | 含供应商、风险信号、审批任务 |
| 2 | `POST /agent/analyze/PO-002` | Agent 分析订单风险 | 建议 `escalate_order`，`order_status_unchanged: true` |
| 3 | `POST /actions/execute` | 执行 `escalate_order` | 状态 `pending_review → escalated`，写入审计日志 |
| 4 | `GET /orders/PO-002/timeline` | 查看完整审计时间线 | 风险信号 → Agent 建议 → Action 执行 |
| 5 | `GET /audit-logs?object_id=PO-002` | 查看 PO-002 所有审计日志 | 成功日志含 before/after 快照 |

### 关键验证点

- ✅ Agent 分析后 `order_status_unchanged: true` — Agent 不直接修改状态
- ✅ Action 执行后状态 `pending_review → escalated` — 唯一的合法状态变更路径
- ✅ Timeline 可追溯 risk_002（风险信号）→ policy_001（政策依据）→ AgentRun → ActionAuditLog
- ✅ 审计日志包含完整的 before/after 快照

---

## Phase 2 Demo（主链路验证）

### 1. 重置数据库并导入种子数据

```powershell
python scripts\reset_db.py
python scripts\seed_data.py
```

### 2. 启动服务

```powershell
uvicorn app.main:app --reload
```

### 3. 运行 Demo

在另一个终端中运行：

```powershell
python scripts\run_demo.py
```

> **注意：** Demo 脚本已升级为使用内存数据库，不依赖启动服务，也不依赖 DeepSeek API Key。

Demo 将自动执行以下主链路：

```text
POST /agent/analyze/PO-002
→ 保存 AgentRun
→ Agent 建议 escalate_order
→ PurchaseOrder.status 不变

POST /actions/execute
→ 执行 escalate_order
→ PurchaseOrder.status: pending_review → escalated
→ 写入 ActionAuditLog

GET /orders/PO-002/timeline
→ 返回 supplier / order / risk_signals / policies / agent_runs / action_audit_logs
```

### 4. 手动 API 测试

打开 Swagger UI 进行交互式测试：

```
http://127.0.0.1:8000/docs
```

### Phase 2 关键约束验证

| 约束 | 验证方式 |
|------|----------|
| Agent 不能修改 PurchaseOrder.status | Demo Step 3 验证 |
| Action Runtime 是唯一状态变更入口 | 仅 `/actions/execute` 可改状态 |
| 成功和失败都必须写 ActionAuditLog | 测试用例覆盖 |
| evidence_ids 必须可追溯 | 伪造 ID 会被拒绝 |
| LLM 失败时 fallback 不崩溃 | 无 API Key 时自动使用 Mock Agent |

---

## Phase 2 验收

### 自动验收脚本

```powershell
python scripts\verify_phase2.py
```

该脚本使用内存数据库，**不需要启动服务**，自动完成：

1. Reset DB + Seed Data
2. `/health`、`/openapi.json`、`/redoc` 检查
3. 基础数据查询（suppliers ≥ 4, orders ≥ 5, risks ≥ 5, policies ≥ 4）
4. `POST /agent/analyze/PO-002` — Agent 分析（Mock fallback）
5. Agent 不改变 PurchaseOrder.status 确认
6. `POST /actions/execute` escalate_order — PO-002 成功升级
7. `POST /actions/execute` approve_order on PO-005 — 失败 + 审计日志
8. `POST /actions/execute` agent:deepseek bypass — 失败 + 审计日志
9. `GET /orders/PO-002/timeline` — 完整审计时间线
10. `GET /audit-logs` — 审计日志查询

**通过时输出：**

```text
PHASE 2 VERIFICATION PASSED
```

**失败时输出具体失败项和修复建议。**

---
## API 文档入口

- **Swagger UI:** http://127.0.0.1:8000/docs
- **ReDoc:** http://127.0.0.1:8000/redoc
- **OpenAPI JSON:** http://127.0.0.1:8000/openapi.json

> ⚠️ **如果 `/docs` 因 Swagger UI CDN 资源加载异常出现白屏，可以使用 `/redoc` 或 `/openapi.json` 作为备用 API 文档入口。** 这不是系统问题，而是 Swagger UI 依赖的 CDN 静态资源在某些网络环境下无法加载。

---
## Optional: Test Real DeepSeek LLM

系统默认使用 **Mock Fallback**（规则引擎）运行，不依赖外部 API。如需验证真实 DeepSeek LLM 接入，按以下步骤操作：

### 1. 创建本地 .env 并配置 API Key

从 `.env.example` 复制并编辑项目根目录 `.env` 文件：

```powershell
copy .env.example .env
```

编辑 `.env`，填入完整配置：

```env
DATABASE_URL=sqlite:///./data/mini_foundry.db
DEEPSEEK_API_KEY=your_real_api_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
APP_ENV=development
```

> ⚠️ **`.env` 已被 `.gitignore` 忽略，请勿将真实 API Key 提交到 Git 仓库。**

### 2. 运行连通性测试

```powershell
python scripts\test_deepseek_llm.py
```

**有 Key 且网络可达时，预期输出：**

```text
DEEPSEEK CONNECTIVITY TEST PASSED
Test 1 Minimal LLM call: PASS
Test 2 analyze_order PO-002: PASS
Test 3 Fallback works: PASS
```

**如果未配置 API Key 或网络不可达：**

```text
DEEPSEEK CONNECTIVITY TEST FAILED
Fallback still works: true
```

### 3. 启动服务验证

```powershell
uvicorn app.main:app --reload
```

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/agent/analyze/PO-002" -Method POST
```

有 Key 时 `status=success`，无 Key 时 `status=fallback`。**系统在任何情况下都不会崩溃，主链路始终可用。**

### 说明

- 该测试需要真实 DeepSeek API Key，**不纳入 pytest**（pytest 始终使用 Mock Fallback）
- 主系统运行时有 Key 则调用真实 LLM，无 Key 则自动 Fallback
- `scripts/test_deepseek_llm.py` 使用内存数据库，不依赖启动服务

---
## 运行测试

```powershell
# 运行全部测试
pytest tests/ -v

# 运行特定测试
pytest tests/test_action_escalate.py -v
pytest tests/test_agent_cannot_modify_order.py -v
pytest tests/test_audit_log.py -v
pytest tests/test_invalid_state_change.py -v
```

测试使用 **内存中的 SQLite 数据库**，无需额外的数据库配置。
测试使用 **MockLLMAgent**（基于规则的 mock），不需要 DeepSeek API Key。

---

## DeepSeek / Fallback 说明

系统已封装 DeepSeek LLM Client（[app/agent/deepseek_llm.py](app/agent/deepseek_llm.py)），支持通过环境变量配置：

```env
DEEPSEEK_API_KEY=sk-your-api-key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
```

### 调用优先级

系统**优先使用 DeepSeek LLM** 进行智能分析。只有在以下情况才自动降级：

1. `DEEPSEEK_API_KEY` 未配置（空字符串）
2. DeepSeek API 不可达（网络故障、超时）
3. API 返回错误响应或格式异常

降级后自动使用 Fallback 规则分析器，不中断业务流程。

### Fallback 机制

当以下任一情况发生时，系统自动 fallback 到规则分析器（[app/agent/mock_llm.py](app/agent/mock_llm.py)）：

- 未配置 `DEEPSEEK_API_KEY`
- DeepSeek API 不可达（网络故障、超时）
- API 返回错误响应

### Fallback 行为保证

| 保证 | 说明 |
|------|------|
| **不中断主链路** | Agent 分析仍然完成，AgentRun 正常写入数据库 |
| **不影响订单状态** | Fallback 与真实 LLM 调用一样，Agent 只能生成 AgentRun 建议，不能直接修改 `PurchaseOrder.status` |
| **状态变更唯一入口不变** | 无论使用真实 LLM 还是 fallback，状态变更必须通过 Action Runtime（`POST /actions/execute`） |
| **标记模型来源** | AgentRun 中的 `model` 字段区分 `"deepseek-v4-flash"` 和 `"mock"`，便于追踪 |
| **测试友好** | 所有 34 个 pytest 测试使用 MockLLMAgent，无需 DeepSeek API Key |

> Fallback 不是缺陷，而是**稳健性设计**：确保系统在外部 LLM 服务不可用时仍能正常运行，不会丢失 AgentRun 记录或中断业务流程。

---

## 面试任务要求对照表

| 面试要求 | 项目实现 | 位置 |
|----------|----------|------|
| 数据导入 | `scripts/seed_data.py` — 4 供应商 + 5 订单 + 5 风险信号 + 4 政策片段 | [scripts/seed_data.py](scripts/seed_data.py) |
| Ontology 建模 | 7 实体：`Supplier` / `PurchaseOrder` / `RiskSignal` / `PolicyChunk` / `ApprovalTask` / `AgentRun` / `ActionAuditLog` | [app/ontology/models.py](app/ontology/models.py) |
| 智能体分析 | `POST /agent/analyze/{order_id}` — LLM Agent 分析 + fallback | [app/agent/analyzer.py](app/agent/analyzer.py) |
| Action 校验 | Action 白名单 + 状态机 + Actor 校验 + Evidence 校验，四层防线 | [app/actions/validators.py](app/actions/validators.py) |
| 状态变更 | Action Runtime 统一入口，`STATE_TRANSITIONS` 定义合法状态转换 | [app/actions/runtime.py](app/actions/runtime.py) |
| 审计记录 | `ActionAuditLog` — append-only，含 before/after 快照、actor、evidence | [app/audit/logger.py](app/audit/logger.py) |
| 可追溯查询 | `GET /orders/{order_id}/timeline` — 完整审计时间线 | [app/audit/trace.py](app/audit/trace.py) |
| 四类 Action | `approve_order` / `reject_order` / `escalate_order` / `freeze_order` | [app/actions/types.py](app/actions/types.py) |
| Agent 不能直接改状态 | Agent 只写 `AgentRun`，`agent:*` actor 在 Action Runtime 层被拒绝 | [tests/test_agent_cannot_modify_order.py](tests/test_agent_cannot_modify_order.py) |
| 至少 5 个测试 | 当前 `pytest` 为 **34 个测试**通过（6 个测试文件） | [tests/](tests/) |

---

## 面试任务 — 5 个核心问题

### 1. 如何理解 Ontology 在系统中的作用？

Ontology（本体）在这个系统中是**业务对象、关系、状态、证据和规则的统一结构化表达**。

它不是简单的数据表集合，而是构建了一个**可查询、可追溯、可控制**的业务知识图谱：

- **实体建模**：`Supplier`（供应商）、`PurchaseOrder`（采购订单）、`RiskSignal`（风险信号）、`PolicyChunk`（政策片段）、`ApprovalTask`（审批任务）、`AgentRun`（智能体分析）、`ActionAuditLog`（审计日志）—— 7 个实体覆盖了采购审核领域的核心概念
- **关系映射**：Supplier → PurchaseOrder（一对多），PurchaseOrder → RiskSignal / ApprovalTask / AgentRun / ActionAuditLog（一对多关联），PolicyChunk 作为独立证据池被 Agent 和 Action Runtime 引用
- **状态建模**：每个实体都有明确的状态枚举（如 PurchaseOrder 的 5 种状态：pending_review / approved / rejected / escalated / frozen），状态转换由 STATE_TRANSITIONS 表统一定义
- **证据链**：evidence_ids 字段将 RiskSignal、PolicyChunk、AgentRun 串联成可追溯的证据链，形成审计闭环

Ontology 的价值在于：**让数据库不再是零散的表，而是一个有语义、有约束、有追溯能力的业务图谱**。

### 2. 为什么智能体（Agent）不能直接修改业务对象？

LLM 智能体（Agent）不能直接修改 PurchaseOrder.status 等业务对象，核心原因有三：

1. **LLM 不可靠性**：大语言模型存在幻觉（hallucination）、误判、输出不稳定的固有问题。如果让 Agent 直接修改订单状态，一次错误的 `freeze_order` 可能导致业务中断，一次错误的 `approve_order` 可能造成资金损失。

2. **越权风险**：Agent 的角色是**分析者和建议者**，不是决策者和执行者。在真实企业场景中，审批权限属于人类角色或系统规则，Agent 不应越权。本系统中通过 Actor 校验强制实施此边界：`agent:*` 前缀的 actor 在 Action Runtime 层被直接拒绝（ActorValidationError）。

3. **审计不可控**：如果 Agent 可以任意修改状态，审计日志将无法区分"Agent 自行决定的变更"和"经过审批流程的合规变更"，审计闭环失效。

**本系统的设计**：Agent 只能生成 `AgentRun`（只读建议记录），通过 `order_status_unchanged: true` 强约束验证。所有状态变更必须经过 Action Runtime，Action Runtime 记录完整的 before/after 快照到 ActionAuditLog。

### 3. Action Runtime 如何保证业务状态变更可控？

Action Runtime 通过**五层防线**保证状态变更的可控性：

1. **统一入口**：`POST /actions/execute` 是 PurchaseOrder.status 的**唯一变更入口**。系统中没有任何其他代码路径可以直接修改订单状态。

2. **Action 类型白名单**：只允许 4 种 Action（approve_order / reject_order / escalate_order / freeze_order），Pydantic 层和业务层双重校验。

3. **状态机校验**：通过 `STATE_TRANSITIONS` 表定义所有合法状态转换。例如：
   - `pending_review` → approve / reject / escalate / freeze
   - `escalated` → approve / reject / freeze（但不能再次 escalate）
   - `approved` → freeze（但不能 approve / reject / escalate）
   - `rejected` / `frozen` → terminal（不可变更）

4. **Actor 校验**：必须是 `user:*` 或 `system:*` 前缀。`agent:*` 前缀被明确禁止（Agent 执行边界）。

5. **Evidence 校验**：evidence_ids 不能为空，且每个 ID 必须可追踪到 RiskSignal、PolicyChunk 或 AgentRun 实体。

6. **双重审计**：成功和失败的操作都写入 ActionAuditLog，包含 before_state / after_state 快照、actor、reason、evidence_ids、timestamp。失败时审计日志在返回错误前 commit，确保不被事务回滚丢失。

### 4. 审计日志（ActionAuditLog）为什么重要？

审计日志是系统**合规性、可追溯性和可治理性**的基石：

1. **合规审计**：记录"**谁**（actor）在**什么时候**（timestamp）基于**什么证据**（evidence_ids）以**什么理由**（reason）执行了**什么操作**（action_type），以及操作的**前后状态**（before_state / after_state）。这是企业审计和合规检查的核心需求。

2. **责任追溯**：当出现问题时（如错误冻结了订单），可以通过审计日志精确定位到操作者、操作时间和依据的证据，实现"可追溯查询"（traceable query）。

3. **错误排查**：即使是失败的操作也记录在案（success=False + error_message），帮助运维和开发团队定位系统问题。

4. **复盘与治理**：通过 Timeline API（GET /orders/{order_id}/timeline），可以按时间线查看订单的完整生命周期——从风险检测、Agent 分析到 Action 执行，形成端到端的**审计闭环**。

5. **不可变性**：审计日志是 append-only 的，不会被修改或删除，保证了审计数据的完整性。

### 5. 如果接入真实 ERP / OA / 采购系统，如何扩展？

系统的模块化设计支持通过以下方式对接真实企业系统：

1. **Adapter / Connector 模式**：
   - 在 `app/` 下新增 `connectors/` 模块，封装与外部系统的通信
   - 例如 `ERPConnector`、`OAConnector`、`SRMConnector`（供应商关系管理）
   - 通过 Dependency Injection 注入到 Action Runtime，在状态变更后回调外部系统

2. **事件驱动集成**：
   - 通过 Webhook / Message Queue（如 Kafka、RabbitMQ）接收外部采购事件
   - `POST /webhooks/purchase-order-created` 接收 ERP 新建订单事件，自动创建 PurchaseOrder + 初始 RiskSignal
   - `POST /webhooks/supplier-status-changed` 接收 SRM 供应商状态变更

3. **身份与权限对接**：
   - 通过 RBAC（基于角色的访问控制）映射企业组织架构
   - 通过 SSO / OAuth2 / LDAP 接入企业统一身份认证
   - actor 字段从当前的 `user:xxx` 扩展为 `user:{employee_id}:{role}`

4. **状态写回**：
   - Action Runtime 执行成功后，通过 Connector 将最终状态写回 ERP/OA
   - 写回失败时保持本地状态不变，并通过重试队列保证最终一致性
   - 审计日志保留跨系统操作的完整链路（本系统状态变更 + 外部系统写回结果）

5. **数据库升级**：
   - 从 SQLite 迁移到 PostgreSQL，利用其 JSONB、全文搜索和事务隔离能力
   - 增加数据库连接池（如 asyncpg + SQLAlchemy async）

6. **部署与运维**：
   - Docker 容器化 + Kubernetes 编排
   - 通过 Prometheus + Grafana 监控 Action 执行指标
   - 通过 ELK / Loki 集中管理审计日志

**关键原则**：无论外部系统多复杂，Action Runtime 始终是本地状态变更的**唯一权威入口**，审计日志始终记录**完整操作链路**。

---

## 后续模块规划

| 阶段 | 模块 | 说明 | 状态 |
|------|------|------|------|
| Phase 1 | Seed Data & Basic APIs | 7 实体 ORM + 种子数据 + 基础查询 API | ✅ 完成 |
| Phase 2 | Agent + Action + Audit | DeepSeek LLM 智能体 + Action Runtime + 审计日志 + 时间线查询 | ✅ 完成 |
| Phase 3 | Production Hardening | PostgreSQL 迁移、鉴权、限流、Docker 部署 | 📋 规划中 |

---

## 项目结构

```text
mini-foundry-ontology-runtime/
├── app/
│   ├── main.py              # FastAPI 入口（注册 7 个 Router）
│   ├── config.py            # 配置管理（环境变量 + .env）
│   ├── database.py          # SQLAlchemy 引擎 & 会话
│   ├── deps.py              # FastAPI 依赖注入
│   ├── api/                 # API 路由层
│   │   ├── suppliers.py     # GET /suppliers
│   │   ├── orders.py        # GET /orders
│   │   ├── risks.py         # GET /risk-signals
│   │   ├── policies.py      # GET /policies
│   │   ├── agent_runs.py    # POST /agent/analyze/{order_id}
│   │   ├── actions.py       # POST /actions/execute
│   │   └── traces.py        # GET /audit-logs
│   ├── ontology/            # 数据模型 & Schema
│   │   ├── models.py        # SQLAlchemy ORM 模型（7 实体）
│   │   ├── schemas.py       # Pydantic v2 序列化
│   │   └── relations.py     # 实体关系文档
│   ├── agent/               # LLM Agent 模块
│   │   ├── base.py          # 抽象基类 + AgentAnalysisResult
│   │   ├── prompts.py       # 系统提示词 + 用户提示词构建
│   │   ├── mock_llm.py      # 规则引擎 Mock（测试 / fallback）
│   │   ├── deepseek_llm.py  # DeepSeek HTTP 客户端（httpx）
│   │   └── analyzer.py      # 完整分析管线（LLM → parse → validate → save）
│   ├── actions/             # Action Runtime 模块
│   │   ├── types.py         # ActionType / OrderStatus 枚举 + 请求/响应 Schema
│   │   ├── state_machine.py # 状态转换验证
│   │   ├── validators.py    # 证据 ID 验证 + 前置校验
│   │   └── runtime.py       # ActionRuntime 执行器（核心）
│   ├── audit/               # 审计日志模块
│   │   ├── logger.py        # AuditLogger（成功 / 失败日志写入）
│   │   └── trace.py         # TimelineBuilder（时间线查询）
│   └── services/            # 业务服务层
│       ├── order_service.py # 订单服务 + Agent 上下文装配
│       ├── supplier_service.py
│       ├── risk_service.py
│       └── policy_service.py
├── data/                    # 数据库 & Seed 数据
│   ├── seed_suppliers.json
│   ├── seed_orders.json
│   ├── seed_risk_signals.json
│   └── seed_policy_chunks.json
├── scripts/
│   ├── init_db.py           # 建表
│   ├── reset_db.py          # 重建数据库
│   ├── seed_data.py         # 导入种子数据
│   ├── run_demo.py          # Phase 2 主链路 Demo
│   └── verify_phase2.py     # Phase 2 自动验收脚本
├── tests/
│   ├── conftest.py                  # 共享 fixtures（内存数据库 + TestClient）
│   ├── test_action_approve.py       # 批准订单测试
│   ├── test_action_escalate.py      # 升级审批测试
│   ├── test_action_freeze.py        # 冻结订单测试
│   ├── test_agent_cannot_modify_order.py  # Agent 不修改状态验证
│   ├── test_audit_log.py            # 审计日志完整性验证
│   └── test_invalid_state_change.py # 非法状态变更拒绝测试
├── docs/
│   ├── api_examples.md
│   ├── architecture_diagram.md
│   └── test_cases.md
├── requirements.txt
├── .env.example
└── README.md
```