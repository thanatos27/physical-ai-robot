# ADR 0003: Use JSONL Pipe for Phase 0.5 Runtime Input

* Status: Accepted
* Date: 2026-09-21
* Phase: 0.5

## Context

Edge AI PipelineとRobot Runtimeを疎結合にした上で、Phase 0.5で両者を接続するTransportを決める必要がある。

将来的にはUnix Socket、IPC、MQTT、Event Bus、ROS 2 Topic等も候補になり得るが、Phase 0.5ではRobot Runtime基本ループの成立を優先する。

## Decision

Phase 0.5ではJSON Linesをstdin/stdout pipeでRobot Runtimeへ入力する。

```text
detection_logger
      ↓ JSONL
stdin/stdout pipe
      ↓
Robot Runtime
```

Robot Runtime自身はrpicam-appsをsubprocessとして起動しない。プロセス接続はShell側の責務とする。

stdin/stdout pipeはPhase 0.5のTransportであり、Runtimeの恒久的な通信方式とはしない。

## Rationale

- 既存のJSON Lines出力をそのまま利用できる
- 構成が単純でPhase 0.5の目的に十分
- 保存済みJSONLを同じ入力経路でReplayできる
- Runtime単体テストをCamera / Hailoなしで行える
- 将来Transportを交換する余地を残せる

## Consequences

Runtime内部ではstdinへ直接依存する範囲をInputSourceへ限定する。

将来Transport要件が変わった場合は新しいADRで再評価する。
