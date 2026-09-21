# Development Workflow

Physical AI Robot プロジェクトにおける標準開発フローを定義する。

本プロジェクトはソフトウェアだけでなく、Raspberry Pi、Edge AI、センサー、
アクチュエータ等の実ハードウェアを含む。

そのため、コードの実装完了や自動テスト成功だけを「完成」とせず、
設計、実装、自動テスト、実機確認を明確に分離して管理する。

---

## 1. 基本方針

開発は以下の流れを基本とする。

```text
Goal / Scope
    ↓
Architecture
    ↓
Technical Decisions
    ↓
Specification
    ↓
Acceptance Criteria
    ↓
Implementation
    ↓
Automated Verification
    ↓
Real-device Verification
    ↓
Acceptance Criteria Review
    ↓
Progress Update
    ↓
Phase Complete
```

特に Acceptance Criteria は、原則として実装開始前に定義する。

「何を実装するか」だけでなく、
「何を確認できれば完成と判断するか」を先に決める。

---

## 2. 役割分担

### 2.1 ChatGPT Project

ChatGPT Project は、プロジェクト全体の設計・技術判断を担当する。

主な役割:

- Phase の Goal / Scope の整理
- アーキテクチャ設計
- コンポーネント責務の整理
- ハードウェア構成の検討
- 技術選定
- 実機結果の分析
- 技術課題の整理
- ADR に残すべき技術判断
- 実装仕様の策定
- Acceptance Criteria の策定
- Acceptance Criteria の最終レビュー
- Phase 完了判断
- 次 Phase の課題整理

実装中に新しい設計判断が必要になった場合も、
原則としてここへ戻して判断する。

### 2.2 Coding Agent

Coding Agent は、確定した仕様に基づく実装を担当する。

主な役割:

- Repository の既存コード・ドキュメント調査
- Specification / ADR / Acceptance Criteria の確認
- 実装
- Unit Test / Integration Test
- リファクタリング
- ビルド手順の整備
- 実装に直接関係するドキュメント更新
- 実装結果の報告

Coding Agent は、設計上重要な判断を独自に確定しない。

仕様だけでは判断できない問題が発生した場合は、
実装を拡大して解決するのではなく、設計側へ戻す。

### 2.3 Raspberry Pi / Real Device

実機環境は、ハードウェアを含む最終的な動作確認を担当する。

例:

- Build / Install
- Camera / NPU / Sensor / Actuator の確認
- 実ハードウェア固有の挙動確認
- End-to-End Test
- 性能・タイミング確認
- 異常系確認

自動テスト成功と実機確認成功は別の結果として扱う。

---

## 3. GitHub を Source of Truth とする

プロジェクトの確定情報は GitHub Repository に保存する。

チャット履歴だけを正式な仕様・判断記録として扱わない。

主要ドキュメントの役割:

```text
README.md
    プロジェクト概要
    現在地
    基本的な利用・実行方法

AGENTS.md
    AI Agent が開発するときの共通ルール

docs/specs/
    これから作るもの
    要求・設計・Acceptance Criteria

docs/decisions/
    なぜその設計・技術を選択したか
    Architecture Decision Records

docs/progress/
    実際にできたもの
    テスト・実機確認結果

docs/development/
    プロジェクト共通の開発プロセス・運用ルール
```

基本原則:

```text
spec     = これから作るもの
decision = なぜそうしたか
progress = 実際にできたもの
```

未実装・未確認の内容を progress に完了事項として記録しない。

---

## 4. Phase 開発フロー

### Step 1: Goal

Phase で実現する目的を定義する。

「何を作るか」より先に、
「この Phase が終わったとき何が可能になるか」を明確にする。

### Step 2: Scope

この Phase で実施することと、実施しないことを定義する。

過剰な先行実装を避ける。

### Step 3: Architecture

既存システムとの関係を整理する。

特に以下を確認する。

- 既存コンポーネントとの境界
- データフロー
- 依存方向
- Hardware / Edge AI / Runtime / Agent の責務
- 将来拡張を妨げないか

既に実機で動作確認済みの構成は尊重する。

変更する場合は理由を明確にする。

### Step 4: Technical Decisions

将来の設計・実装に影響する重要な判断は ADR として記録する。

例:

- コンポーネント境界
- 通信方式
- データ形式
- Runtime の実行モデル
- ハードウェア依存部分の配置
- 重要なトレードオフ

### Step 5: Specification

Coding Agent が実装可能なレベルまで仕様を具体化する。

必要に応じて以下を定義する。

- Module / Component
- Data Model
- Interface
- Processing Flow
- Error Handling
- Lifecycle
- Logging
- Constraints
- Out of Scope

### Step 6: Acceptance Criteria

実装開始前に Acceptance Criteria を定義する。

詳細は「5. Acceptance Criteria」を参照。

### Step 7: Implementation

Coding Agent が Specification / ADR / Acceptance Criteria に基づいて実装する。

既存の動作確認済み構成を不用意に変更しない。

### Step 8: Automated Verification

可能な範囲を自動テストする。

例:

- Unit Test
- Integration Test
- Fixture / Replay Data を使ったテスト
- Error / Edge Case Test

ハードウェアがなくても検証できるロジックは、
可能な限り自動テスト可能にする。

### Step 9: Real-device Verification

実ハードウェアが関係する Acceptance Criteria を実機で確認する。

自動テストが成功していても、
Real-device Acceptance Criteria が残っている場合は完了扱いにしない。

### Step 10: Acceptance Criteria Review

自動テスト結果と実機確認結果を基に、
必須 Acceptance Criteria が成立したかレビューする。

未確認項目は未確認のまま明記する。

### Step 11: Progress Update

確認済みの事実を `docs/progress/` に反映する。

以下を区別して記録する。

- 実装済み
- Automated Test 済み
- Real-device Test 済み
- 未確認
- 将来課題

### Step 12: Phase Complete

必須 Acceptance Criteria が成立したことを確認して Phase を完了する。

残った課題は次 Phase または Technical Debt として明示する。

---

## 5. Acceptance Criteria

Acceptance Criteria は、
Phase または機能の「完成条件」を定義する。

実装内容ではなく、外部から確認可能な結果を中心に記述する。

### 5.1 原則

1. 原則として実装開始前に定義する
2. Coding Agent は Acceptance Criteria を実装目標として使用する
3. 自動テストと実機確認を区別する
4. 必須条件と任意条件を必要に応じて区別する
5. 確認できていない項目を推測で Pass にしない
6. Phase 完了時に Acceptance Criteria をレビューする

### 5.2 観点

必要に応じて以下から選択する。

| 観点 | 内容 |
| --- | --- |
| Functional | 期待する機能・振る舞い |
| Data | 入出力・保存データ |
| Error / Edge Case | 異常系・境界条件 |
| Automated Test | ハードウェアなしで検証可能な項目 |
| Real-device | Raspberry Pi / 実ハードウェアでの確認 |
| End-to-End | 複数コンポーネントを通した確認 |
| Lifecycle | 起動・停止・再起動 |
| Recovery / Failure | 障害時の挙動 |
| Performance | FPS、Latency、CPU等、必要な場合のみ |
| Safety | モーター等の物理動作を伴う場合 |

すべての Phase で全項目を要求するわけではない。

Phase の目的に必要な項目を選択する。

### 5.3 状態

Acceptance Criteria の確認状態を明確にする。

例:

```text
AC-01  Defined
AC-02  Automated Test Passed
AC-03  Real-device Test Passed
AC-04  Pending
AC-05  Failed
```

「実装済み」と「確認済み」を混同しない。

### 5.4 Physical AI における完了条件

本プロジェクトでは原則として、

```text
Implementation Complete
        ≠
Automated Test Passed
        ≠
Real-device Verified
```

として扱う。

ハードウェア依存機能については、
実機確認を Acceptance Criteria に含める。

---

## 6. 実装中に問題が見つかった場合

問題を Bug と Design Issue に分ける。

```text
Problem Found
      ↓
既存仕様から修正方法が明確か？
      │
      ├─ Yes
      │    ↓
      │  Bug Fix
      │    ↓
      │  Test
      │
      └─ No
           ↓
       Design Issue
           ↓
       ChatGPT Project
           ↓
       Technical Decision
           ↓
       ADR / Spec / AC Update
           ↓
       Coding Agent
```

Coding Agent が設計判断を暗黙に行い、
そのまま実装を進めることを避ける。

---

## 7. 実機確認から新しい事実が見つかった場合

実機確認は単なる最終テストではなく、
新しい技術的事実を発見する工程でもある。

例えば、

- 公式仕様と実機挙動が異なる
- Hardware / Driver 固有の制約がある
- Timing による問題が発生する
- Sensor Data にノイズがある
- 推論結果が一時的に欠落する

といった事象が確認された場合、
推測で吸収せず事実として記録する。

その結果として設計変更が必要なら、
ADR / Specification / Acceptance Criteria を更新してから実装へ戻る。

---

## 8. Phase 完了時の整理

Phase の節目では最低限、以下を整理する。

- 現在の Hardware / Software 構成
- 実装した機能
- 成功した手順
- Automated Test 結果
- Real-device Test 結果
- 重要な Technical Decisions / ADR
- 既知の制限
- 未確認項目
- Technical Debt
- 次 Phase への課題

これらを `docs/progress/` に反映する。

---

## 9. 基本原則

本プロジェクトでは以下を優先する。

```text
実機確認 > 推測

現在の環境 > 一般論

公式仕様 > 非公式情報

確認済み構成の維持 > 不要な作り直し

明示された設計判断 > Agentによる暗黙の判断

Acceptance Criteriaによる確認 > 「たぶん動く」

段階的な拡張 > 将来を見越した過剰実装
```

Physical AI Robot は長期開発プロジェクトである。

各 Phase で小さく動作するシステムを完成させ、
実機から得られた事実を次の設計へ反映しながら、

```text
Observe → Reason → Action → Log
```

を段階的に拡張していく。
