# ADR 0004: Separate Detection Event from Runtime Observation

* Status: Accepted
* Date: 2026-09-21
* Phase: 0.5

## Context

Phase 0.5の外部入力はYOLOv8 Detection結果だが、将来はToF、IMU、Encoder、LiDAR等の情報をRobot Runtimeで扱う予定である。

外部Detection JSONをそのままRuntime内部の世界表現として使用すると、Perception固有フォーマットがRuntime全体へ広がる。

## Decision

外部モデル `DetectionEvent` とRuntime内部モデル `Observation` を分離し、`ObservationAdapter` で変換する。

```text
DetectionEvent
      ↓
ObservationAdapter
      ↓
Observation
```

Phase 0.5のObservationは主にtimestampとobjectsを保持する。

## Rationale

- 外部I/Oフォーマットと内部モデルを分離できる
- Hailo / YOLOv8固有情報の波及を抑えられる
- 将来Sensor情報をObservationへ統合しやすい
- 保存済みEventや別InputSourceからも同じRuntimeモデルへ変換できる

## Consequences

DetectionEventとObservationの間に変換処理が必要となる。

両モデルが似ていてもPhase 0.5では同一モデルに統合しない。
