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

## Development Workflow

開発プロセス、役割分担、Acceptance Criteria、実機確認、Phase完了条件については以下を参照する。

`docs/development/workflow.md`

AI Agentは実装開始前に、対象Phase・機能のSpecification、ADR、Acceptance Criteriaを確認する。

特に以下を守る。

- Acceptance Criteriaを実装目標として扱う
- Automated Test成功とReal-device Verification成功を区別する
- 仕様だけでは決められない設計判断を独自に確定しない
- 新しい設計判断が必要な場合は実装を拡大せず、設計側へ戻す
- 未確認事項を推測でPassまたは完了扱いにしない

## Development Principles

### 1. Preserve Verified Configurations

実機で動作確認済みの構成を優先する。

既存の正常動作している構成を、明確な理由なく置き換えない。

変更が必要な場合は、変更理由、期待するメリット、既存構成への影響、検証方法を明確にする。

### 2. Prefer Evidence Over Assumptions

ハードウェア・OS・ドライバ・ライブラリ等について、以下の順に優先する。

1. 現在の実機環境
2. 実機で確認した結果
3. 公式ドキュメント・公式仕様
4. その他の情報

不明な環境情報を推測で補完しない。

### 3. Raspberry Pi Executability

Raspberry Pi向けのコマンドやコードは、可能な限りそのまま実行できる形式で提示・実装する。

現在の実機環境については以下を参照。

`docs/progress/phase-0.5-progress.md`

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

## Documentation

ドキュメントの役割と更新タイミングは `docs/development/workflow.md` に従う。

主要な保存先：

```text
docs/specs/        これから作るもの
docs/decisions/    なぜそうしたか
docs/progress/     実際にできたもの
docs/development/  開発プロセス・運用ルール
```

重要な技術判断はADRとして記録し、未実装・未確認の内容を完了済みのprogressとして記録しない。

## Current Phase

現在：

```text
Phase 0.5 — Robot Runtime
```

Observe → Reason → Action → Log の基本ループは実機動作確認済み。

Observeパイプライン（ソースとビルド手順は `edge/detection_logger/`）：

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

Robot Runtime（実装は `runtime/`、実機動作確認済み）：

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

`docs/progress/phase-0.5-progress.md`

## Working With Other Agents

他のAI Agentが作成したコードや設計を、既存仕様を確認せずに置き換えない。

変更前に、少なくとも対象に関連する以下を確認する。

```text
README.md
AGENTS.md
docs/development/
docs/specs/
docs/decisions/
docs/progress/
```

既存の判断と異なる提案を行う場合は、既存案との差分と変更理由を示す。

## Generated Data

ログ、動画、モデル出力、一時ファイル等の大容量データは原則としてGitへコミットしない。

必要なデータ形式や再現手順のみドキュメント化する。

## Safety

モーター等の物理Actuatorを扱うPhaseでは、安全性を機能追加より優先する。

将来的に以下を考慮する。

- Emergency Stop
- Motor output limits
- Command timeout
- Watchdog
- Fail-safe state
- Manual override

AI Agentの判断だけで安全制約を無効化しない。
