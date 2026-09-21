# ADR 0008: Normalize Missing Detection Metadata as Zero Detections in Phase 0.5

* Status: Accepted
* Date: 2026-09-21
* Phase: 0.5

## Context

Robot Runtimeは`detection_logger`のJSONLをstdinから受信し、Detection 0件を正常なObservationとして`NO_PERSON`へ処理する。

実機確認では、カメラを覆ってDetection 0件の状態で実行した場合、`detection_logger`からJSONLが出力されなかった。

現在の`detection_logger`は`object_detect.results`を取得できない場合に何も出力せず終了する。一方、`hailo_yolo_inference`ではDetection 0件のフレームで`object_detect.results`自体が設定されない場合がある。

また、`detection_logger`から見た「`object_detect.results`が存在しない」という状態だけでは、Phase 0.5の現在のインターフェース上、以下を厳密に区別できない。

- 正常に推論した結果、Detection 0件
- 推論処理が成立していない
- 推論結果を取得できなかった

## Decision

Phase 0.5では`detection_logger`をEdge AI PipelineとRobot Runtimeの正規化境界とする。

`object_detect.results`を取得できないフレームについても、`detection_logger`は空のDetection EventをJSONLとして出力する。

```json
{"timestamp":123456789,"detections":[]}
```

Robot Runtimeはこれを正常なDetectionEventとして受け取り、

```text
detections: []
      ↓
Observation(objects=[])
      ↓
NO_PERSON
```

として処理する。

この正規化はPythonのRobot Runtime内部ではなく、Runtimeへ入力するJSONLを生成する`detection_logger`側で行う。

## Rationale

- Phase 0.5の目的であるObserve → Reason → Action → Logの基本ループ成立を優先できる
- Runtime側で「入力が来ない」と「Detection 0件」を混同しない
- Detection JSONLをフレーム単位の観測結果として扱える
- 既存のHailo / rpicam-apps実装へパッチを入れず、自作の`detection_logger`だけで対応できる
- Robot RuntimeをHailoや`object_detect.results`の内部仕様から引き続き分離できる

## Consequences

Phase 0.5では、正常なDetection 0件と推論失敗・結果取得失敗をRobot Runtimeから区別できない。

したがって、`detections: []`は「正常な推論が完了したこと」を保証するものではない。

将来、自律走行、センサー健全性監視、障害復旧等でこの区別が必要になった場合は、推論状態を表すメタデータや`inference_status`等を導入し、新しいADRで再評価する。

Phase 0.5ではその追加実装は行わない。
