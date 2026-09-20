# ADR 0006: Use JSONL Robot Data Log Behind a Logger Boundary

* Status: Accepted
* Date: 2026-09-21
* Phase: 0.5

## Context

Physical AI RobotではObserve → Reason → Action → Logの各Loopを後から追跡可能にする必要がある。

将来的にはBehavior Cloning / RLや分析用途でRobot Dataを利用する可能性があり、保存先もDatabaseやData Lakeへ変化する可能性がある。

## Decision

Phase 0.5では1 Runtime Loopを1 `RobotLoopRecord` としてJSON Linesへ保存する。

RobotLoopRecordは最低限以下を持つ。

```text
schema_version
loop_id
timestamp
observation
decision
action
result
```

Runtime本体はJSONL writerへ直接依存せず、`RobotDataLogger` 境界を介して保存する。

Application LogとRobot Data Logは分離する。

## Rationale

- JSONLは単純で確認・Replay・後処理が容易
- 1 Loop = 1 Recordとして扱いやすい
- schema_versionにより将来の形式変更を管理できる
- RobotDataLogger境界により将来DB等へ交換できる

## Consequences

Phase 0.5ではDatabaseを導入しない。

RobotDataLoggerの保存失敗はObserve → Reason → Action → Logループが成立しないためRuntime障害として扱う。
