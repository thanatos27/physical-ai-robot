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

以下の Observe → Reason → Action → Log の基本ループは実機で動作確認済み。

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
Robot Runtime
        ↓
Observation → Reason → Action → Log
```

Detection JSONをObservationとして受け取る Robot Runtime は `runtime/`、Detection JSONを出力する `detection_logger` は `edge/detection_logger/` にある。次の課題は `docs/progress/phase-0.5-progress.md` の第19章を参照。

詳細な進捗：

`docs/progress/phase-0.5-progress.md`

### Robot Runtime の実行(開発中)

リポジトリルートで、Detection JSONL を標準入力から与える。

```bash
# 保存済みJSONL(fixture)の再生
python3 -m runtime.robot_runtime < tests/fixtures/detections_sample.jsonl

# Raspberry Pi 上でカメラ入力を接続
rpicam-hello -t 10000 \
  --post-process-file ~/detection-logger/hailo_yolov8_logger.json \
  --nopreview | python3 -m runtime.robot_runtime
```

* Robot Data Log は既定で `logs/robot-data-<UTC日時>.jsonl` に保存される(`--log-path` で変更可)
* Application Log は stderr、Actionのコンソール出力は stdout
* テスト: `python3 -m unittest discover -s tests -t .`

Raspberry Pi 5 実機での E2E 確認(`docs/specs/phase-0.5-robot-runtime.md` の AC-08)は完了している。結果は `docs/progress/phase-0.5-progress.md` の第14章を参照。

## Raspberry Pi 実機の操作

ホスト名は `pi5.local`、ユーザーは `kei`。リポジトリは Pi 上の `~/physical-ai-robot`。

### 接続

```bash
ssh kei@pi5.local
```

### 電源

```bash
sudo poweroff   # シャットダウン(完了後に電源を抜く)
sudo reboot     # 再起動
```

Robot Runtime の実行中は、先に Ctrl+C で止めてから電源を切る。

### コードの転送

基本は Pi 上で `git pull`。未コミットの変更を試すときは、開発PC(PowerShell)から `scp` で転送する。

```powershell
# runtime/ 全体
scp -r runtime kei@pi5.local:~/physical-ai-robot/

# detection_logger のソースとビルド手順(ファイルを指定して転送)
scp edge/detection_logger/detection_logger.cpp edge/detection_logger/build.sh kei@pi5.local:~/physical-ai-robot/edge/detection_logger/
```

* `edge/` は `-r` で丸ごと送らない(Pi 側のビルド結果 `build/` や `.so` を上書きし得るため)

転送後は、上の「Robot Runtime の実行」と `edge/detection_logger/README.md` の手順で実行・ビルドする。

### ログの回収

Robot Data Log は Pi 上の `~/physical-ai-robot/logs/` に保存される(Git 管理外)。開発PC(PowerShell)へ取り出すには、次のようにする。

```powershell
scp kei@pi5.local:~/physical-ai-robot/logs/<ファイル名> .
```

ファイル名は、Pi 上で `ls -l ~/physical-ai-robot/logs/` を実行して確認する。

### 状態確認

Pi 上で実行する。

```bash
rpicam-hello --list-cameras      # カメラ (imx708_wide が表示される)
hailortcli fw-control identify   # Hailo-10H (Device Architecture: HAILO10H が表示される)
```

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
├── decisions/     # Architecture Decision Records (ADR)
└── specs/         # 実装仕様
```

### Documentation Update Rules

ドキュメントは役割を分けて更新する。

- `docs/decisions/`: 今後の設計・実装に影響する重要な技術判断が確定した時点でADRを追加・更新する
- `docs/specs/`: 実装対象の設計・要求・Acceptance Criteriaが固まった時点で追加・更新する
- `docs/progress/`: 実装、テスト、実機確認などの結果として「実際にできたこと」が増えた節目で更新する

原則として `specs` は「これから作るもの」、`progress` は「実際にできたもの」、`decisions` は「なぜそうしたか」を記録する。

予定や未検証の内容を `progress` の完了実績として扱わない。

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
