# Physical AI Robot

Raspberry Pi 5を中心とした自律ロボットを開発する長期プロジェクト。

実世界から情報を取得し、判断・行動・記録する以下のループを基本アーキテクチャとする。

```text
Observe → Reason → Action → Log
   ↑                         ↓
   └──── Learning / Update ──┘
```

## Goal

最終的には以下の技術領域へ発展させる。

* Edge AI
* Robot Runtime
* AI Agent
* SLAM
* Digital Twin
* Behavior Cloning / Reinforcement Learning
* Sim2Real

ロボットが収集した観測・行動ログを学習へ還流し、改善されたPolicyを再び実機へ展開できるPhysical AIシステムを目指す。

## Current Phase

### Phase 0.5 — Robot Runtime

現在は Raspberry Pi 5 + AI HAT+ 2 + Camera Module 3 Wide を使用。

以下のObserveパイプラインは実機で動作確認済み。

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
        ↓
Robot Runtime ← NEXT
```

次の開発対象は、Detection JSONをObservationとして受け取る **Robot Runtime / Reason層**。

詳細な進捗：

`docs/progress/phase-0.5.md`

## Development Principles

* 実機で動作確認済みの構成を尊重する
* 既存構成を変更する場合は理由を明確にする
* 推測より実機確認・公式仕様・現在の環境を優先する
* 重要な技術判断はADRとして記録する
* 開発の節目で進捗ドキュメントを更新する
* Raspberry Pi上で再現可能なコマンド・手順を残す

## Documentation

```text
docs/
├── progress/      # 各Phaseの進捗・実機確認結果
└── decisions/     # Architecture Decision Records (ADR)
```

AI Agent向けの共通開発ルールは `AGENTS.md` を参照。

## Roadmap

```text
Phase 0.5  Edge AI / Robot Runtime
    ↓
Phase 0.8  Stationary AI Robot
    ↓
Phase 1    Mobile Robot
    ↓
Phase 2    LiDAR / SLAM
    ↓
Phase 3    Digital Twin
    ↓
Phase 4    Learning / Sim2Real
```
