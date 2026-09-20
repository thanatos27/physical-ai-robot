# ADR 0005: Separate Reason, Action Planning, and Execution

* Status: Accepted
* Date: 2026-09-21
* Phase: 0.5

## Context

将来Robot RuntimeではReasoning方式と物理Actuatorの双方が変化する。

ReasonerがMotor Driver等を直接操作すると、判断ロジックとハードウェア制御が密結合になる。

## Decision

Runtimeを以下の責務に分離する。

```text
Observation
    ↓
Reasoner
    ↓
Decision
    ↓
ActionPlanner
    ↓
Action
    ↓
Executor
    ↓
ActionResult
```

Reasonerは「何をしたいか」をDecisionとして出力し、ActionPlannerが具体的なActionへ変換する。

ExecutorはActionの実行のみを担当する。

Phase 0.5ではRule-based ReasonerとConsoleExecutorを使用する。

## Rationale

- Reasoning方式とActuator実装を独立して交換できる
- Reasonerがハードウェア詳細を知る必要がない
- 将来VLM / LLM / Learned PolicyをReasoner側へ導入しやすい
- Motor / Display / Speaker等のExecutor追加に対応しやすい

## Consequences

Phase 0.5では単純な処理に対して複数の責務境界が存在する。

ただし将来交換する理由が明確な境界のみを設け、不要なFramework化は行わない。
