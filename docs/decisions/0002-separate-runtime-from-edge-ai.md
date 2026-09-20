# ADR 0002: Separate Robot Runtime from Edge AI Pipeline

* Status: Accepted
* Date: 2026-09-21
* Phase: 0.5

## Context

Phase 0.5では、実機動作確認済みのCamera / Hailo-10H / YOLOv8パイプラインから得られるDetection結果をRobot Runtimeへ入力する。

Robot RuntimeをHailo API、YOLOv8、rpicam-apps内部Metadataへ直接結合すると、将来Perception方式を変更した際にRuntime側へ影響が波及する。

## Decision

Edge AI PipelineとRobot Runtimeを別プロセス・別責務として分離する。

```text
Camera / Hailo / YOLOv8
        ↓
detection_logger
        ↓
DetectionEvent
        ↓
Robot Runtime
```

Robot RuntimeはHailo APIや `object_detect.results` を直接扱わない。

Phase 0.5では `detection_logger` が出力するJSON Linesを境界とする。

## Rationale

- 実機動作確認済みのPerception Pipelineを維持できる
- RuntimeをHailo固有実装から分離できる
- 保存済みDetection EventをRuntimeへ再入力できる
- 将来Perception実装を交換しやすくなる

## Consequences

Robot Runtimeには外部Detection Eventを内部Observationへ変換する境界が必要となる。

PerceptionとRuntimeのプロセス管理・接続方法は別途定義する。
