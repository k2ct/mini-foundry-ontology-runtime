# Mini Foundry Ontology Action Runtime

> 企业采购风险审核 — Ontology 建模 + 智能体分析 + Action 校验 + 审计追溯

**Version:** 0.1.0  
**Status:** Phase 1 — Seed Data & Basic Query APIs

---

## 项目简介

Mini Foundry Ontology Action Runtime 是一个面向企业采购风险审核场景的轻量级智能运行时。系统围绕 **采购订单（PurchaseOrder）** 构建 Ontology 知识模型，结合 LLM Agent 分析和 Action Runtime 状态机，实现从数据导入到审计追溯的完整闭环。

### 核心业务流程

```text
数据导入 → Ontology 建模 → 智能体分析 → Action 校验 → 状态变更 → 审计记录 → 可追溯查询
```

---

## 技术栈

| 组件 | 技术 |
|------|------|
| Web 框架 | FastAPI 0.100+ |
| ORM | SQLAlchemy 2.0+ |
| 数据校验 | Pydantic 2.0+ |
| 数据库 | SQLite（开发阶段），可平滑迁移至 PostgreSQL |
| LLM 集成 | DeepSeek API（预留） |
| 异步服务器 | Uvicorn |
| 测试 | pytest + httpx |

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

## 当前已实现功能（Phase 1）

### 基础查询 API

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

### 数据模型（7 个实体）

`Supplier` → `PurchaseOrder` → `RiskSignal` / `ApprovalTask` / `AgentRun` / `ActionAuditLog` + `PolicyChunk`

---

## 后续模块规划

| 阶段 | 模块 | 说明 |
|------|------|------|
| Phase 2 | Agent Analyzer | DeepSeek LLM 智能体分析订单风险，生成 AgentRun 建议 |
| Phase 3 | Action Runtime | 状态机 + 校验器，执行 approve / reject / freeze / escalate 动作 |
| Phase 4 | ActionAuditLog | 审计日志闭环，记录每次状态变更的 before/after 快照 |
| Phase 5 | Timeline Query | 按订单查询完整审计时间线 |
| Phase 6 | Integration Tests | 端到端测试覆盖所有场景 |
| Phase 7 | Production Hardening | PostgreSQL 迁移、鉴权、限流、Docker 部署 |

---

## 项目结构

```text
mini-foundry-ontology-runtime/
├── app/
│   ├── main.py              # FastAPI 入口
│   ├── config.py            # 配置管理
│   ├── database.py          # SQLAlchemy 引擎 & 会话
│   ├── deps.py              # FastAPI 依赖注入
│   ├── api/                 # API 路由层
│   │   ├── suppliers.py
│   │   ├── orders.py
│   │   ├── risks.py
│   │   └── policies.py
│   ├── ontology/            # 数据模型 & Schema
│   │   ├── models.py        # SQLAlchemy ORM 模型（7 实体）
│   │   ├── schemas.py       # Pydantic v2 序列化
│   │   └── relations.py     # 实体关系文档
│   ├── agent/               # LLM Agent 模块（Phase 2）
│   ├── actions/             # Action Runtime（Phase 3）
│   ├── audit/               # 审计日志（Phase 4）
│   └── services/            # 业务服务层（预留）
├── data/                    # 数据库 & Seed 数据
│   ├── seed_suppliers.json
│   ├── seed_orders.json
│   ├── seed_risk_signals.json
│   └── seed_policy_chunks.json
├── scripts/
│   ├── init_db.py
│   ├── reset_db.py
│   └── seed_data.py
├── docs/
│   ├── api_examples.md
│   ├── architecture_diagram.md
│   └── ontology_design.md
├── tests/
├── requirements.txt
├── .env.example
└── README.md
```
