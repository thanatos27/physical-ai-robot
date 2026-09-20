# ADR 0007: Use Synchronous Sequential Runtime in Phase 0.5

* Status: Accepted
* Date: 2026-09-21
* Phase: 0.5

## Context

将来的なMobile RobotではCamera、LiDAR、IMU、Encoder、Motor等を並行して扱う可能性がある。

一方、Phase 0.5の目的はDetection EventからObserve → Reason → Action → Logの基本ループを成立させることである。

## Decision

Phase 0.5のRobot Runtimeはsingle-processの同期・逐次処理とする。

```text
Event N
  ↓
Observe
  ↓
Reason
  ↓
Action
  ↓
Log
  ↓
Event N+1
```

async、multiprocessing、Event Bus、ROS 2はPhase 0.5では導入しない。

## Rationale

- 現在の要件では並行処理を必要としない
- Runtime Loopの挙動を理解・テストしやすい
- 不要なFrameworkや運用複雑性を避けられる
- 将来の並行処理要件が具体化してから適切な方式を選択できる

## Consequences

Phase 0.5ではEvent処理中に次Eventを並行処理しない。

複数SensorやActuatorのリアルタイム要件が発生した時点でRuntime実行モデルを再評価する。
