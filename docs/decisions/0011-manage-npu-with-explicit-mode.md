# ADR 0011: Manage NPU Ownership with an Explicit Mode in Phase 0.8

* Status: Accepted
* Date: 2026-10-02
* Phase: 0.8
* Decision record: Issue #9

## Context

Milestone 8 で、Phase 0.5 の Vision pipeline (rpicam-apps + `hailo_yolov8_logger.json`、未変更) と VLM の共存を実機で確認した (`docs/progress/phase-0.8-progress.md` #7)。

- rpicam-apps の Hailo stage は `VDevice::create()` を既定パラメータで呼ぶ。HailoRT の既定 group_id は `"UNIQUE"` で、NPU を専有する
- プロセス間で共有するには `multi_process_service` (HailoRT service) が必要だが、この環境には HailoRT service が無い
- YOLO 実行中に VLM をロードすると `HAILO_OUT_OF_PHYSICAL_DEVICES` で失敗する
- VLM が NPU を保持している間に YOLO を起動すると、rpicam-hello は正常終了のまま、全フレーム `"detections":[]` を出し続ける。VLM が NPU を解放しても、**再起動するまで復帰しない**
- カメラも専有で、YOLO 実行中の `rpicam-still` は失敗する (YOLO には影響しない)
- 常駐 worker / model resident は、待機中も NPU を専有するため連続 YOLO と両立しない

現在の Runtime は Vision process を所有していない (シェルの pipe で stdin から受け取る) ため、Runtime から Vision を停止・再開できない。

## Decision

Phase 0.8 では、Vision が動作している間は AI Job を実行しない排他ポリシーとし、NPU の利用を**起動時に明示したモード**で管理する。

```text
--npu-mode vision (既定)   NPU を VISION として予約し、AI Job は worker を起動せず理由付きで拒否する
--npu-mode ai              Vision を使わず、AI Job が NPU を排他的に使う
                           FREE -> EXCLUSIVE_AI -> FREE (worker の回収後に FREE)
```

- NPU の状態は Detection JSONL の到着間隔から推定しない
- 状態遷移は Application Log、拒否理由は Robot Event Log (AI Result `REJECTED`) から追跡できるようにする
- `EXCLUSIVE_AI` の間は、Job Type が異なる Job も拒否する
- `NpuArbiter` は OS / HailoRT レベルのロックではなく、Runtime 管理下の NPU Job に対する admission control / resource visibility とする

次は Phase 0.8 では実装しない。

- Vision process の lifecycle 管理 (停止 / 再開 / health check)
- Vision と AI の自動モード切替
- HailoRT service / multi-process sharing
- rpicam-apps の Hailo stage の置き換え
- Priority scheduling / preemption

## Rationale

- 実機確認済みの Vision pipeline を変更せずに、Runtime 管理下の NPU Job の無制御な同時実行を防げる (AC-NPU-01)
- NPU の利用状況を推定ではなく明示されたモードで決めるため、見かけだけの Lock にならない (AC-NPU-04)
- Vision 動作中の VLM 要求で、worker が約 10 秒かけて失敗する無駄が無くなる

## Consequences

- Runtime の外で手動起動された `rpicam-hello` 等による NPU の利用は防げない。AI の実行中に Vision を起動すると、Vision は検出0件を出し続け、再起動まで復帰しない
- この「気づけない故障」は、ADR 0008 で「正常な検出0件と推論失敗を区別できない」とした制限が、実際の故障モードとして現れたものである
- 将来、Vision と AI を自動で切り替える (NPU mode management: VISION → stop / release → EXCLUSIVE_AI → Vision restart + health check → VISION) には、Vision の推論状態を明示的に判定できる信号が前提になる。その導入は別の Design Issue / ADR で扱う
- 実装: `runtime/ai.py` (`NpuMode`、`NpuArbiter`)、`runtime/robot_runtime.py` (`--npu-mode`)
