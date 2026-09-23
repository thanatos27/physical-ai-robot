# Physical AI Robot — Phase 0.8 Stationary AI Robot 設計仕様

## 1. 目的

Phase 0.8 の目的は、Phase 0.5 で実機確認済みの Robot Runtime を据え置き型 AI Robot へ拡張し、

```text
Observe → Reason → Action → Log
```

を Camera だけでなく、Display / Button / Microphone / Speaker / RGB LED を含む Human Interaction へ拡張することである。

Phase 0.8 では Whisplay HAT を追加し、Robot Runtime から物理 I/O を扱えるようにする。

同時に、今後の VLM / LLM / STT 等の AI Workload 増加を見据え、

- AI 処理で Runtime Core を停止させない
- Hailo-10H の利用競合を無制御にしない
- AI Job の優先順位や Backpressure を将来追加できる

ための責務境界を設計する。

ただし Phase 0.8 では高度な Scheduler や汎用 AI Orchestrator を作り込まない。

---

## 2. 既存システム

Phase 0.5 では以下が実装・実機確認済みである。

```text
Camera Module 3 Wide
        ↓
rpicam-apps
        ↓
Hailo-10H
        ↓
YOLOv8
        ↓
detection_logger
        ↓
Detection JSONL
        ↓
Robot Runtime
        ↓
Observation
        ↓
Rule Reason
        ↓
Console Action
        ↓
RobotLoopRecord
        ↓
JSONL
```

既存 Runtime は `runtime/` にあり、同期・逐次処理で構成されている。

主な責務境界:

```text
InputSource
    ↓
DetectionEvent
    ↓
ObservationAdapter
    ↓
Observation
    ↓
Reasoner
    ↓
Decision
    ↓
ActionPlanner
    ↓
Action
    ↓
Executor
    ↓
ActionResult
    ↓
RobotLoopRecord
    ↓
RobotDataLogger
```

Phase 0.8 ではこの責務境界を尊重し、全面的な作り直しを前提としない。

特に以下は原則として変更しない。

- Camera / Hailo / YOLO / rpicam-apps の動作確認済み構成
- `detection_logger` の Detection JSONL 境界
- Observation / Reason / Action / Log の分離
- Hardware 固有処理を Reasoner へ入れない原則
- Robot Data Log と Application Log の分離

必要な変更がある場合は、理由、影響範囲、移行方法を明示する。

---

## 3. Phase 0.8 Hardware

既存:

- Raspberry Pi 5 8GB
- Raspberry Pi AI HAT+ 2
  - Hailo-10H
  - 純正ヒートシンク装着済み
  - GPIO stacking header 装着済み
- Raspberry Pi Camera Module 3 Wide
- Raspberry Pi 5 Active Cooler
- Raspberry Pi 27W USB-C Power Supply
- microSDXC 128GB

Phase 0.8 追加:

- Whisplay HAT
  - LCD
  - Microphone
  - Speaker
  - Button
  - RGB LED

Whisplay は Raspberry Pi 5 + AI HAT+ 2 上へ積層する構成を基本とする。

物理クリアランス、FFC ケーブル取り回し、長時間運転時の熱状態は実機到着後に確認する。

---

## 4. Scope

### 4.1 Core

Phase 0.8 Core では以下を実現する。

- Phase 0.5 Detection JSONL の継続利用
- Vision Observation の取得
- Whisplay Button 入力
- Whisplay Microphone 入力
- Whisplay Display 出力
- Whisplay RGB LED 出力
- Whisplay Speaker 出力
- Rule-based Reason
- Observe → Reason → Action → Log の継続
- Hardware Adapter 境界
- AI Job 管理境界
- NPU 利用管理境界
- 構造化 Robot Event Log
- Hardware なしでの自動テスト

### 4.2 Extension

Phase 0.8 では以下を疎通レベルで実施してよい。

- STT
- LLM
- VLM
- AI Result の Runtime への返却

本格的な AI Agent / Tool Use / Long-term Memory / RAG は対象外。

### 4.3 Out of Scope

以下は Phase 0.8 では実装しない。

- Motor
- Encoder
- ToF
- IMU
- Battery operation
- Emergency Stop
- LiDAR
- SLAM
- Autonomous Navigation
- Behavior Cloning
- RL
- Digital Twin
- Sim2Real
- ROS 2
- 汎用 Message Broker
- 高度な AI Job Scheduler
- Preemption
- Fair Scheduling
- Distributed Worker

---

## 5. Functional Requirements

### FR-01 Vision Observation

Phase 0.5 の Detection JSONL を Runtime が継続利用できること。

### FR-02 Observation Normalization

外部 I/O を Runtime 内部の Observation / Event へ変換できること。

### FR-03 Button Input

Whisplay Button 入力を Runtime へ通知できること。

### FR-04 Microphone Input

Whisplay Microphone から音声データを取得できること。

### FR-05 Runtime Loop

Observe → Reason → Action → Log を継続実行できること。

### FR-06 Rule-based Reason

AI Backend なしでも決定論的な Rule-based Reason が成立すること。

### FR-07 Hardware Abstraction

Reasoner / Runtime Core から Whisplay 固有 API を直接呼ばないこと。

### FR-08 Display Action

Runtime から Display へ任意の状態・メッセージを表示できること。

### FR-09 LED Action

Runtime から RGB LED の状態を変更できること。

### FR-10 Speaker Action

Runtime から Speaker へ音声を再生できること。

### FR-11 Robot Event Log

Observation / Reason / Action / Result を構造化ログとして保存できること。

### FR-12 Device Status

主要デバイスの利用可否を Runtime が把握できること。

### FR-13 Graceful Degradation

非必須 I/O の一部が利用不能でも可能な範囲で Runtime を継続できること。

---

## 6. Non-Functional Requirements

### NFR-01 Compatibility

Phase 0.5 の実機確認済み構成を原則変更しない。

### NFR-02 Modularity

Observe / Reason / Action / Log の責務を維持する。

### NFR-03 Hardware Isolation

Whisplay 固有処理を Hardware Adapter 層へ閉じ込める。

### NFR-04 Failure Isolation

Display / Speaker 等の一部障害を Runtime 全体の即時停止へ直結させない。

### NFR-05 AI Fallback

LLM / VLM / STT が利用不能でも Rule-based Core は動作可能とする。

### NFR-06 Core Responsiveness

Rule-based Core は AI Job 待ちで停止しない。

### NFR-07 AI Asynchrony

長時間 AI 処理を Runtime Core の Control Flow から分離する。

### NFR-08 NPU Arbitration

Hailo を利用する複数処理を無制御に同時実行しない。

### NFR-09 Traceability

Observation → Reason → Action → Result を同一処理単位として追跡可能にする。

### NFR-10 Testability

Core Logic は実機なしで自動テスト可能とする。

### NFR-11 Extensibility

Phase 1 の Sensor / Motor 追加時に Runtime 全体を全面リライトしない。

### NFR-12 Offline Core

Core は Internet 接続なしで動作可能とする。

### NFR-13 Thermal Stability

通常運転で継続的な thermal throttling が発生しないことを実機確認する。

### NFR-14 Secret Management

API Key 等を Git 管理対象へ保存しない。

---

## 7. Architecture Principles

Phase 0.8 では以下を設計原則とする。

```text
1. Hardware と Runtime Core を分離する
2. Rule-based Core を基準系として残す
3. AI 推論を Job として扱う
4. Runtime Core は AI Job 完了を同期的に待たない
5. NPU 利用管理の責務を一箇所へ集約する
6. State 型入力と Event 型入力を区別する
7. 将来拡張のための境界は作るが、機能を先行実装しない
```

---

## 8. Logical Architecture

```text
                    Physical World
                          │
          ┌───────────────┼───────────────┐
          │               │               │
        Camera          Button           Mic
          │               │               │
          ▼               ▼               ▼
   Vision Adapter    Button Adapter   Audio Adapter
          │               │               │
          └───────────────┼───────────────┘
                          ▼
                 Observation / Event
                          │
                          ▼
                  ┌──────────────┐
                  │ Runtime Core │
                  └──────┬───────┘
                         │
              ┌──────────┴──────────┐
              │                     │
              ▼                     ▼
        Rule Reasoner          AI Job Manager
              │                     │
              │                AI Backend
              │                     │
              └──────────┬──────────┘
                         ▼
                   Action Layer
                         │
             ┌───────────┼───────────┐
             ▼           ▼           ▼
          Display       LED        Speaker
                         │
                         ▼
                     Event Log
```

Runtime Core は Hailo / Whisplay 固有 API を直接所有しない。

---

## 9. Existing Runtime Evolution

Phase 0.5 の `runtime/` は既に実装・実機確認済みであるため、Phase 0.8 では新 Package への全面置換を行わない。

既存:

```text
runtime/
├── models.py
├── input.py
├── observation.py
├── reasoner.py
├── action.py
├── robot_logger.py
└── robot_runtime.py
```

Phase 0.8 では必要に応じて段階的に以下を追加する。

```text
runtime/
├── ...
├── event.py              # 必要になった場合
├── state.py              # Runtime State
├── ai.py                 # AI Job / Job Manager / NPU resource boundary の初期配置候補
└── adapters/
    ├── whisplay.py       # 初期は1ファイルでもよい
    └── mock.py
```

AI 側も Whisplay Adapter と同様に、初期は1ファイルまたは最小限の構成から開始する。

`AIJob` / `AIJobManager` / `NpuArbiter` は Architecture 上の責務として分離するが、Python ファイルまで先行分割しない。責務や実装量が増えた時点で `ai_job.py` / `ai_manager.py` / `npu_arbiter.py` 等へ分割する。

将来の可能性だけを理由に細かいディレクトリ階層を先行導入しない。

---

## 10. Observation Model

Phase 0.5 の `Observation` は Vision の世界表現として既に利用されている。

Phase 0.8 では、既存モデルを不用意に巨大な Union 型へ変更せず、入力特性を以下の2種類へ分けて扱う。

### 10.1 State 型

最新値が重要な入力。

例:

- Vision Detection
- 将来の IMU
- 将来の ToF

Policy:

```text
Latest wins
```

古い State を無制限に Queue へ蓄積しない。

### 10.2 Event 型

発生事実を保持する入力。

例:

- Button pressed
- AI Job completed
- Error

Policy:

```text
FIFO
```

Phase 0.8 では高度な Event Bus を導入しない。

---

## 11. Runtime State

必要になった状態だけを Runtime State として保持する。

例:

```text
RuntimeState
├─ latest_vision
├─ devices
│   ├─ camera
│   ├─ hailo
│   └─ whisplay
└─ ai
    ├─ current_job
    └─ resource_state
```

Runtime State は Hardware API の Object Handle 集合にはしない。

Reasoner から見えるのは意味的な状態のみとする。

---

## 12. Reason Architecture

Phase 0.8 Core の基準系は Rule-based Reasoner とする。

```text
Observation / Event
       ↓
Rule Reasoner
       ↓
Decision
       ↓
Action
```

AI Reasoning を利用する場合も Reasoner から Hailo を直接呼ばない。

```text
AI Reason request
      ↓
AI Job
      ↓
AI Job Manager
```

AI Job の結果は後続 Event として Runtime へ戻す。

---

## 13. Action Architecture

既存 Phase 0.5 の

```text
Decision
   ↓
ActionPlanner
   ↓
Action
   ↓
Executor
```

を維持する。

Phase 0.8 では Executor 側を Hardware Adapter へ拡張する。

概念例:

```text
Action
 ├─ DISPLAY_MESSAGE
 ├─ SET_STATUS_LED
 └─ PLAY_AUDIO
        ↓
Executor / Adapter
        ↓
Whisplay
```

Reasoner は Whisplay の GPIO / daemon / driver 詳細を知らない。

---

## 14. AI Job Model

AI Workload は Job として表現する。

Phase 0.8 の最小モデル:

```text
AIJob
├─ job_id
├─ type
│   ├─ STT
│   ├─ VLM
│   └─ LLM
├─ backend
├─ input
├─ timeout
├─ status
└─ priority
```

状態例:

```text
QUEUED
RUNNING
COMPLETED
FAILED
TIMEOUT
CANCELLED
```

Phase 0.8 で全状態遷移を高度に実装する必要はない。

`priority` は将来利用できる Data Model として用意してよいが、Priority Queue / Preemption / Starvation Control は Phase 0.8 の必須実装としない。

---

## 15. AI Asynchrony

### 15.1 Goal

AI Job 実行中でも Runtime Core の基本 I/O を停止させない。

例:

```text
VLM running
    │
    ├─ Button input      → 処理可能
    ├─ Runtime logging   → 継続
    └─ Device status     → 更新可能
```

### 15.2 Execution Model

Phase 0.8 では、Phase 0.5 で実機確認済みの同期 Runtime Core と SIGINT / Shutdown 処理を維持する。

```text
Existing synchronous Runtime Core
        ↑
        │ Event / Result
        │
AI Job Manager
        ↓
Worker thread / process
        ↓
Blocking / Native AI
```

Runtime Core 自体を asyncio へ全面移行しない。

AI Job Manager は Runtime Core から分離して動作させる。実装方式は thread または subprocess を候補とし、必要であれば AI Job Manager 内部で asyncio を利用してよい。

AI Job 完了時は `AI Job completed` 相当の Event を Runtime 入力側へ返し、既存 Core は通常 Event として処理する。

Phase 0.8 の変更点は「Core を非同期化すること」ではなく、「Vision 以外の Event Source と AI Result Source を同期 Core へ多重化できるようにすること」とする。

実装時には以下を確認する。

- 現行 `stdin_input_source` と複数 Event Source の統合方法
- SIGINT / Shutdown の既存挙動を壊さないこと
- Worker の停止・timeout・exception propagation
- thread と subprocess のどちらが Phase 0.8 に適切か
- Phase 1 以降で Worker 実装を交換できる境界になっているか

---

## 16. NPU Resource Management

### 16.1 Problem

現在の Vision Pipeline は Runtime 外の `rpicam-apps` process で Hailo-10H を利用している。

したがって Python Runtime 内だけで Lock を取得しても、

```text
Runtime Lock = FREE
```

であることと、

```text
Hailo device = FREE
```

であることは一致しない。

Phase 0.8 の NPU 管理はこの事実を無視しない。

### 16.2 NPU Arbiter Boundary

NPU 利用管理責務を `NpuArbiter` 相当の境界へ集約する。

概念状態:

```text
FREE
VISION
EXCLUSIVE_AI
```

ただし実装方式は設計レビュー後に決定する。

候補:

- Runtime 内 Lock
- Process lifecycle coordination
- Worker ownership
- Hailo Runtime の共存機能

### 16.3 Conservative Policy

実機で共存が確認できるまでは、NPU は競合し得る Exclusive Resource として扱う。

Phase 0.8 の VLM Proof は、連続 Streaming ではなく on-demand の単一画像推論とする。

```text
User / Runtime request
        ↓
single camera image
        ↓
VLM Job
        ↓
short description
        ↓
AI Result Event
```

VLM Backend は Hailo-10H 上の Local VLM を第一候補とする。これにより、既存の連続 YOLO と on-demand VLM の共存可否を Phase 0.8 で小さく実機検証する。

ただし設計段階で必ず、

```text
YOLO stop
→ VLM
→ YOLO restart
```

を実装するとは決めない。

まず Hailo / VDevice / model の実機挙動を確認し、

- 共存可能なら軽量な Resource 管理
- 共存不可なら Vision Process Lifecycle と協調した排他

のどちらが必要かを決定する。

この実機検証結果によって NPU Arbiter の具体実装を確定する。

---

## 17. Backpressure

高速な Vision Event を全件 AI Job 化しない。

State 型:

```text
latest wins
```

User interaction 等の Event 型:

```text
FIFO
```

AI Job については Job Type ごとに将来、

- latest wins
- FIFO
- drop if busy
- replace pending

等を選択可能な責務境界を残す。

Phase 0.8 の default policy は以下とする。

```text
State input
  → latest wins

Button / Device Event
  → FIFO

AI Result Event
  → FIFO

AI Job Request
  → 同一 Job Type につき running 1件 + pending 最新1件
  → pending 中に新しい同種 request が来た場合は pending を置換
```

この AI Job Request policy は Phase 0.8 の簡易方針であり、ユーザー操作を常に捨ててよいという恒久ルールではない。

Phase 0.8 では汎用 Policy Engine、Priority Queue、Preemption、Starvation Control は実装しない。

---

## 18. Logging

### 18.1 Application Log

人間向けの運用・デバッグログ。

### 18.2 Robot Event Log

機械処理可能な構造化ログ。

最低限:

```text
schema_version
cycle_id
timestamp
observation / event
reason
action
result
```

AI Job を含む場合は必要に応じて `job_id` を関連付ける。

Phase 0.5 の `RobotLoopRecord` を直ちに破棄せず、schema evolution として扱う。

データ形式変更時は schema version を更新する。

---

## 19. Failure Policy

### 19.1 Non-critical I/O

例:

- Speaker unavailable
- Display write failed

可能な範囲で Runtime を継続し、Application Log / Robot Event Log へ記録する。

### 19.2 AI Failure

以下で Runtime Core を停止しない。

- AI Job timeout
- AI Job failed
- Remote API unavailable

Rule-based fallback を維持する。

### 19.3 Critical Runtime Failure

Runtime の整合性を維持できない障害は異常終了してよい。

例:

- Robot Data Log を保存できない
- Runtime internal invariant violation

Shutdown 時は子 process / worker / logger の後始末を試みる。

---

## 20. Whisplay Integration Strategy

Whisplay 到着後は Runtime へ統合する前に単体確認を行う。

```text
Display
Button
RGB LED
Speaker
Microphone
```

の順序は固定しないが、各 I/O を個別に確認してから Runtime Adapter へ接続する。

Whisplay 固有依存は Adapter 層へ閉じ込める。

Real Adapter と Fake / Mock Adapter を切り替えられる構造を目標とする。

---

## 21. AI Extension Scope

### STT

```text
Mic
 ↓
short audio
 ↓
STT
 ↓
text
```

が成立すればよい。

### VLM

Phase 0.8 では on-demand の単一画像推論とする。

```text
Request
 ↓
single Camera Image
 ↓
Local VLM (Hailo-10H 第一候補)
 ↓
short description
```

が成立すればよい。

連続 Streaming VLM は Phase 0.8 の対象外とする。

### LLM

```text
simple prompt
 ↓
LLM
 ↓
short response
```

が成立すればよい。

Phase 0.8 では少なくとも1種類の AI Result を Runtime へ戻し、Display または Log で利用できれば Integration Proof とする。

---

## 22. Acceptance Criteria

### AC-01 Runtime Lifecycle

Robot Runtime を起動・正常終了できる。

### AC-02 Existing Vision Input

Phase 0.5 Detection JSONL を継続的に受信できる。

### AC-03 Observation

Detection JSONL を内部 Observation へ変換できる。

### AC-04 State Update

Observation / Event によって Runtime State を更新できる。

### AC-05 Rule Reason

AI 無効状態で Rule-based Reason が成立する。

### AC-06 Core Loop

Observation → Reason → Action → Log の1 cycle が成立する。

### AC-07 Shutdown

停止時に Logger と Runtime 管理下の Worker / Process を適切に終了できる。

### AC-08 State Backpressure

Vision 等の State 型入力を無制限に Queue へ蓄積しない。

### AC-09 Event Ordering

Button 等の Event 型入力を通常利用範囲で発生順に処理できる。

### AC-10 Deterministic Rule

同じ入力条件に対して Rule-based Reason が決定論的な結果を返す。

### AC-11 AI-independent Core

LLM / VLM / STT 無効状態でも Core が成立する。

### AC-12 Whisplay Display

LCD へ任意テキストを表示できる。

### AC-13 Whisplay LED

RGB LED を Runtime から制御できる。

### AC-14 Whisplay Button

Button 入力を Runtime Event として取得できる。

### AC-15 Whisplay Speaker

Speaker からテスト音声を再生できる。

### AC-16 Whisplay Microphone

Microphone から音声を取得できる。

### AC-17 Button E2E

```text
Button
 ↓
Event
 ↓
Rule Reason
 ↓
Display / LED / Speaker
 ↓
Log
```

が成立する。

### AC-18 Vision E2E

```text
Camera
 ↓
Person Detection
 ↓
Observation
 ↓
Rule Reason
 ↓
Display / LED
 ↓
Log
```

が成立する。

### AC-19 Hardware Abstraction

RuleReasoner / Runtime Core から Whisplay 固有 API を直接呼ばない。

### AC-20 Fake Hardware

Whisplay 実機を Fake / Mock Adapter へ置き換えて Runtime の主要処理を実行できる。

### AC-21 Traceability

1つの処理単位から Observation / Reason / Action / Result を追跡できる。

### AC-22 Structured Log

Robot Event Log が JSONL 等の機械処理可能な形式で保存される。

### AC-23 Application Log

Runtime 内部エラーを Application Log から調査できる。

### AC-24 Non-critical Failure

非必須 I/O の1つが失敗しても Runtime 全体を即時異常終了させない。

### AC-25 Device Failure Visibility

障害デバイスと原因を Log から識別できる。

### AC-26 Fatal Shutdown

継続不能時に可能な範囲で正常な Shutdown 処理を行う。

### AC-AI-01 Non-blocking AI

AI Job 実行中でも Runtime Core の基本 Event 処理を継続できる。

### AC-AI-02 AI Job State

少なくとも QUEUED / RUNNING / COMPLETED / FAILED / TIMEOUT 相当の状態を表現できる。

### AC-AI-03 AI Timeout

AI Job timeout が Runtime Core の停止を引き起こさない。

### AC-AI-04 AI Result Event

AI 結果を Runtime へ Event として返却できる。

### AC-NPU-01 Controlled Execution

Runtime 管理下の NPU Job を無制御に同時実行しない。

### AC-NPU-02 Resource Visibility

NPU 利用状態を Runtime から確認可能にする。

### AC-NPU-03 NPU Logging

NPU Job の開始 / 終了 / 失敗を追跡可能にする。

### AC-NPU-04 External Ownership Awareness

Runtime 外の rpicam-apps / YOLO による Hailo 利用を無視した見かけだけの Lock にしない。

### AC-JOB-01 Priority Extensibility

AI Job に Priority 概念を追加可能な Data Model とする。

Priority Queue / Preemption / Starvation Control は Phase 0.8 の必須条件としない。

### AC-EXT-01 STT Proof

Mic → STT → text が一度以上成功する。

### AC-EXT-02 VLM Proof

on-demand の single Camera Image → Local VLM → short description が一度以上成功する。

Hailo-10H を第一候補 Backend とし、既存 YOLO との共存可否を実機で確認する。

### AC-EXT-03 LLM Proof

simple prompt → LLM → short response が一度以上成功する。

### AC-EXT-04 AI Runtime Integration

AI Result の少なくとも1種類を Runtime へ戻し、Display または Log で利用できる。

### AC-27 Core Responsiveness

Rule-based Interaction に明らかな数秒単位の不要な遅延がない。

### AC-28 Thermal

一定時間の連続稼働で継続的 thermal throttling が発生しない。

### AC-29 Offline Core

Internet 接続なしで Camera / YOLO / Runtime / Rule Reason / Whisplay / Log の Core が動作する。

### AC-30 Hardware-free Test

Fake Observation → Rule Reason → Fake Action を Hardware なしで自動テストできる。

### AC-31 Reasoner Unit Test

RuleReasoner を単体テストできる。

### AC-32 Vision Fixture Test

実 Camera なしで Detection JSON fixture から Vision 入力をテストできる。

### AC-33 Fake AI Backend

実 NPU なしで Success / Failure / Timeout を再現できる Fake AI Backend を利用して AI Job 管理をテストできる。

---

## 23. Design Review Focus

Phase 0.8 Design Review では Hardware / Runtime 境界よりも、以下を重点的に議論する。

### Review-01 AI Execution Model

レビュー結果として Runtime Core の同期構造を維持する。

AI Job Manager / Worker の隔離方式について、thread / subprocess / 必要に応じた内部 asyncio の責務分割を実装時に検証する。

- 既存 stdin / SIGINT / Shutdown の維持
- Worker shutdown race
- exception propagation
- timeout / cancellation
- testability
- Phase 1 以降の拡張性

### Review-02 NPU Ownership

既存 rpicam-apps YOLO を含め、Hailo-10H の ownership をどこで管理するべきか。

### Review-03 NPU Arbiter Scope

Phase 0.8 で NPU Arbiter をどこまで実装するべきか。

境界だけ作り、実際の scheduling を最小限に留める判断が妥当か確認する。

### Review-04 Job Priority

Phase 0.8 では priority metadata のみ持たせ、Priority Queue / Preemption を延期する方針が妥当か。

### Review-05 Backpressure

State = latest wins、Event = FIFO という分離が適切か。

AI Job の latest / FIFO / drop policy をどの層の責務にするべきか。

### Review-06 Over-engineering

将来拡張を意識するあまり Phase 0.8 で不要な abstraction / scheduler / process 管理を導入していないか。

### Review-07 Migration Safety

実機確認済み Phase 0.5 Runtime を壊さず、段階的に Phase 0.8 へ移行できるか。

---

## 24. Review / Implementation Workflow

Phase 0.8 では以下の分担を試行する。

```text
設計
  ChatGPT
    ↓
Design PR
    ↓
設計レビュー
  Claude Code
    ↓
Design Fix / Discussion
    ↓
Merge
    ↓
実装
  Claude Code
    ↓
Implementation PR
    ↓
実装レビュー
  Codex
    ↓
Fix / Merge
```

レビューは GitHub Pull Request 上で行い、議論・判断の履歴を残す。

本運用は Phase 0.8 で試行し、プロジェクト標準 Workflow へ恒久反映するかは結果を見て判断する。

---

## 25. Implementation Policy

Phase 0.8 では以下を優先する。

```text
実機確認 > 推測

既存の Phase 0.5 Runtime を尊重

Runtime / Hardware 境界を維持

Rule-based Core を壊さない

AI 非同期性の境界は作る

NPU 管理の責務は明確化する

Scheduler は必要になるまで作り込まない

将来拡張のための Interface
    >
将来使うかもしれない機能の先行実装
```

Design Review で Architecture / Acceptance Criteria を確定した後に Implementation Plan を作成する。
