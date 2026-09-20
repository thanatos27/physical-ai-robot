# ADR 0001: Use rpicam-apps Post Processing Plugin for Detection Metadata

* Status: Accepted
* Date: 2026-09-21
* Phase: 0.5

## Context

Phase 0.5では、Raspberry Pi 5 + AI HAT+ 2 + Camera Module 3 Wideによる物体検出結果をRobot Runtimeへ渡す必要がある。

以下のパイプラインは実機で動作確認済み。

```text
Camera Module 3 Wide
        ↓
rpicam-apps
        ↓
Hailo-10H
        ↓
YOLOv8
```

映像上へのBounding Box描画だけではRobot Runtimeから利用しにくいため、YOLOv8のDetection Metadataを構造化データとして取得する必要があった。

## Considered Options

### Option 1: Python + GStreamer

GStreamerのPad ProbeからHailo Metadataを取得する方式を検討した。

Hailo Python APIには以下が存在する。

```text
HailoROI
HailoDetection
get_roi_from_buffer
get_hailo_detections
```

一方、現在のRaspberry Pi環境では以下を実行すると、

```bash
gst-inspect-1.0 libcamerasrc
```

`libcamerasrc` が利用できない状態だった。

この方式を採用する場合、既に正常動作している `rpicam-apps` ベースのCamera → Hailoパイプラインとは別のCamera Pipelineを構築する必要がある。

### Option 2: rpicam-apps Post Processing Plugin

`rpicam-apps` のPost Processing Metadataを調査した結果、Detection結果が以下のMetadata Tagに格納されていることを確認した。

```text
object_detect.results
```

型は以下。

```cpp
std::vector<Detection>
```

このMetadataを読み取る独自Post Processing Stageを追加することで、既存パイプラインを維持したままDetection結果を外部へ出力できる。

## Decision

Phase 0.5では **rpicam-apps Post Processing Plugin方式を採用する**。

パイプラインは以下とする。

```text
Camera
  ↓
rpicam-apps
  ↓
Hailo YOLO inference
  ↓
object_detect.results
  ↓
detection_logger
  ↓
JSON Lines
  ↓
Robot Runtime
```

独自Stage `detection_logger` が `object_detect.results` を取得し、Detection MetadataをJSON Linesとして標準出力へ出力する。

## Rationale

主な理由は以下。

* 既に実機で動作確認済みの `rpicam-apps` パイプラインを維持できる
* Camera Pipelineを新たに構築する必要がない
* Hailo推論結果を直接 `object_detect.results` から取得できる
* Robot RuntimeとHailo固有実装の境界をJSON Linesで分離できる
* Phase 0.5の目的に対して構成変更を最小限にできる

## Consequences

### Positive

Robot RuntimeはHailo APIや `rpicam-apps` 内部構造を直接扱う必要がなくなる。

```text
Hailo / rpicam-apps
        ↓
     JSON Lines
        ↓
   Robot Runtime
```

これによりPerception実装とRobot Runtimeの結合度を下げられる。

また、既存のCamera / Hailo推論パイプラインを維持できる。

### Negative

`detection_logger` はC++による独自Post Processing Pluginとして管理する必要がある。

また、`object_detect.results` など `rpicam-apps` の内部インターフェースへの依存が存在するため、将来のバージョン変更時には互換性確認が必要となる。

## Verification

以下の構成で実機動作を確認済み。

```text
Camera Module 3 Wide
        ↓
rpicam-apps
        ↓
Hailo-10H
        ↓
YOLOv8
        ↓
object_detect.results
        ↓
detection_logger
        ↓
JSON Lines
```

Detection出力例：

```json
{"timestamp":1789762879207,"detections":[{"class":"person","category":1,"confidence":0.901203,"bbox":{"x":3,"y":2,"width":1242,"height":1044}},{"class":"clock","category":75,"confidence":0.435167,"bbox":{"x":940,"y":502,"width":235,"height":373}}]}
```

## Future Considerations

GStreamerを恒久的に不採用とする判断ではない。

将来、以下のような要件が発生した場合は再評価する。

* 複数Camera Pipeline
* より複雑なMedia Pipeline
* GStreamerベースの他コンポーネントとの統合
* `rpicam-apps` では満たせない映像処理要件

その場合は新しいADRを作成し、本ADRをSupersededとする。
