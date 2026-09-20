# AGENTS.md

## Project

Physical AI Robot

Raspberry Pi 5を中心とした自律ロボット開発プロジェクト。

基本ループ：

```text
Observe → Reason → Action → Log
   ↑                         ↓
   └──── Learning / Update ──┘
```

将来的にEdge AI、Robot Runtime、AI Agent、SLAM、Digital Twin、Behavior Cloning / RL、Sim2Realへ発展させる。

## Source of Truth

GitHubリポジトリをプロジェクトのSource of Truthとする。

設計、実装、技術判断、進捗は可能な限りリポジトリ内に記録する。

AI Agentは既存ドキュメントとコードを確認してから変更を行うこと。

## Development Principles

### 1. Preserve Verified Configurations

実機で動作確認済みの構成を優先する。

既存の正常動作している構成を、明確な理由なく置き換えない。

変更が必要な場合は以下を明確にする。

* 変更理由
* 期待するメリット
* 既存構成への影響
* 検証方法

### 2. Prefer Evidence Over Assumptions

ハードウェア・OS・ドライバ・ライブラリ等について、推測より以下を優先する。

1. 現在の実機環境
2. 実機で確認した結果
3. 公式ドキュメント・公式仕様
4. その他の情報

不明な環境情報を推測で補完しない。

### 3. Raspberry Pi Executability

Raspberry Pi向けのコマンドやコードは、可能な限りそのまま実行できる形式で提示・実装する。

現在の実機環境については以下を参照。

`docs/progress/phase-0.5.md`

### 4. Keep Architecture Boundaries

以下の責務境界を維持する。

```text
Observe
  ↓
Reason
  ↓
Action
  ↓
Log
```

将来センサー、モーター、SLAM、AI Agent等が追加されても、この境界を不用意に結合しない。

### 5. Record Technical Decisions

重要なアーキテクチャ変更や技術選定はADR（Architecture Decision Record）として記録する。

保存先：

```text
docs/decisions/
```

特に以下の場合はADRを検討する。

* 主要ライブラリ・フレームワークの選択
* Runtime構成の変更
* データフォーマットの決定
* ハードウェア構成の重要な変更
* 既存の動作確認済み方式を別方式へ置き換える場合

### 6. Update Progress Documentation

開発の節目では以下を整理する。

* 現在の構成
* 実機で成功した手順
* 動作確認結果
* 技術判断
* 未解決事項
* 次の課題

Phaseごとの記録は以下に保存する。

```text
docs/progress/
```

## Current Phase

現在：

```text
Phase 0.5 — Robot Runtime
```

Observeパイプラインは実機動作確認済み。

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

次の開発対象：

```text
JSON Lines
    ↓
Robot Runtime
    ↓
Observation
    ↓
Reason
    ↓
Action
    ↓
Log
```

詳細は以下を参照。

`docs/progress/phase-0.5.md`

## Working With Other Agents

他のAI Agentが作成したコードや設計を、既存仕様を確認せずに置き換えない。

変更前に関連する以下を確認する。

```text
README.md
AGENTS.md
docs/progress/
docs/decisions/
```

既存の判断と異なる提案を行う場合は、既存案との差分と変更理由を示す。

## Generated Data

ログ、動画、モデル出力、一時ファイル等の大容量データは原則としてGitへコミットしない。

必要なデータ形式や再現手順のみドキュメント化する。

## Safety

モーター等の物理Actuatorを扱うPhaseでは、安全性を機能追加より優先する。

将来的に以下を考慮する。

* Emergency Stop
* Motor output limits
* Command timeout
* Watchdog
* Fail-safe state
* Manual override

AI Agentの判断だけで安全制約を無効化しない。
OK