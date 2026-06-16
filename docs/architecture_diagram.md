# 系统架构图

> Mini Foundry Ontology Action Runtime — Enterprise Procurement Risk Review

---

## 整体架构（Mermaid）

```mermaid
graph TD
    %% ── Style definitions ───────────────────────────────────────────
    classDef done fill:#4caf50,stroke:#2e7d32,color:#fff
    classDef planned fill:#90a4ae,stroke:#546e7a,color:#fff
    classDef external fill:#ff9800,stroke:#e65100,color:#fff
    classDef storage fill:#2196f3,stroke:#0d47a1,color:#fff

    %% ── External ─────────────────────────────────────────────────────
    Client["API Client
    (browser / curl / pytest)"]
    class Client external

    DeepSeek["DeepSeek LLM
    (deepseek-v4-flash)
    External API"]
    class DeepSeek external

    FallbackAnalyzer["Fallback Rule Analyzer
    (app/agent/mock_llm.py)
    No API key needed"]
    class FallbackAnalyzer done

    %% ── FastAPI Layer ─────────────────────────────────────────────────
    FastAPI["FastAPI Application
    (app.main:app)
    GET /health /suppliers /orders /risk-signals /policies"]
    class FastAPI done

    %% ── Ontology DB ──────────────────────────────────────────────────
    OntologyDB[("Ontology DB
    (SQLite → PostgreSQL)
    7 Tables:
    suppliers
    purchase_orders
    risk_signals
    policy_chunks
    approval_tasks
    agent_runs
    action_audit_logs")]
    class OntologyDB storage

    %% ── LLM Agent Analyzer ───────────────────────────────────────────
    AgentAnalyzer["LLM Agent Analyzer
    (app/agent/analyzer.py)
    Read orders + risks + policies
    → Produce AgentRun (suggestion ONLY)
    Priority: DeepSeek → Fallback"]
    class AgentAnalyzer done

    %% ── AgentRun ─────────────────────────────────────────────────────
    AgentRunRecord["AgentRun
    (Read-Only Suggestion)
    risk_level / suggested_action
    / reason / evidence_ids / confidence"]
    class AgentRunRecord done

    %% ── Action Runtime ───────────────────────────────────────────────
    ActionRuntime["Action Runtime
    (app/actions/runtime.py)
    Validators → State Machine
    approve / reject / freeze / escalate"]
    class ActionRuntime done

    %% ── State Change ─────────────────────────────────────────────────
    StateChange["PurchaseOrder State Change
    pending_review
    → approved / rejected / escalated / frozen"]
    class StateChange done

    %% ── Audit Log ────────────────────────────────────────────────────
    ActionAuditLog["ActionAuditLog
    (app/audit/logger.py)
    ★ action_type ★ object_id
    ★ actor ★ reason ★ evidence_ids
    ★ before_state ★ after_state
    ★ timestamp ★ success"]
    class ActionAuditLog done

    %% ── Timeline Query ───────────────────────────────────────────────
    TimelineQuery["Timeline Query API
    GET /orders/{id}/timeline
    Full audit trace per order"]
    class TimelineQuery done

    %% ── Edges ────────────────────────────────────────────────────────
    Client --> FastAPI
    FastAPI --> OntologyDB

    AgentAnalyzer --> OntologyDB
    AgentAnalyzer --> DeepSeek
    AgentAnalyzer --> FallbackAnalyzer
    AgentAnalyzer --> AgentRunRecord
    AgentRunRecord --> OntologyDB

    ActionRuntime --> AgentRunRecord
    ActionRuntime --> OntologyDB
    ActionRuntime --> StateChange
    StateChange --> OntologyDB

    ActionRuntime --> ActionAuditLog
    ActionAuditLog --> OntologyDB

    TimelineQuery --> OntologyDB

    %% ── Legend ───────────────────────────────────────────────────────
    subgraph Legend
        L1["🟢 Phase 1 & 2 — Done"]:::done
        L2["🔵 Database / Storage"]:::storage
        L3["⚪ Phase 3+ — Planned"]:::planned
        L4["🟠 External Service"]:::external
    end
```

---

## 数据流说明

### Phase 1（已实现）

```text
Client ──GET──▶ FastAPI ──Query──▶ Ontology DB
                    │
                    ▼
              JSON Response
         (SupplierRead / OrderDetail / RiskSignalRead / PolicyChunkRead)
```

### Phase 2（已实现）

```text
1. Agent Analyzer 读取订单 + 风险信号 + 政策
2. 优先调用 DeepSeek LLM 生成分析建议
3. 若 DeepSeek 不可用（无 Key / 网络故障 / 超时 / 格式异常）→ 自动降级到 Fallback Rule Analyzer
4. 写入 AgentRun（READ-ONLY，不可直接修改订单状态）
5. Action Runtime 读取 AgentRun 建议
6. 执行校验器 → 状态机判定
7. 写入 PurchaseOrder 新状态 + ActionAuditLog（before/after 快照）
8. Timeline Query 按 order_id 查询完整审计链路
```

---

## 关键设计约束

| 约束 | 说明 |
|------|------|
| **AgentRun 只读** | Agent 只能写入 `agent_runs` 表，**禁止**直接修改 `purchase_orders.status` |
| **Action Runtime 唯一写入口** | 所有状态变更必须通过 Action Runtime 执行 |
| **审计闭环** | 每次状态变更写入 `action_audit_logs`，包含 before/after 快照 |
| **幂等 Seed** | `scripts/seed_data.py` 可重复运行，已有记录自动跳过 |

---

## 实体关系

```text
Supplier (1) ────< (N) PurchaseOrder
PurchaseOrder (1) ────< (N) RiskSignal
PurchaseOrder (1) ────< (N) ApprovalTask
PurchaseOrder (1) ────< (N) AgentRun
PolicyChunk ──(via evidence_ids)──▶ AgentRun / ActionAuditLog
ActionAuditLog ──(via object_id)──▶ PurchaseOrder
```
