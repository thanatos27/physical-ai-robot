# Phase 0.8 Implementation Plan

## 1. 目的

この文書は、`docs/specs/phase-0.8-stationary-ai-robot.md` で確定した設計を、Claude Code が段階的に実装するための作業計画へ落とし込む。

Phase 0.8 では、Phase 0.5 で実機確認済みの同期 Robot Runtime を壊さずに、Whisplay HAT と AI Job を追加する。

最優先事項:

```text
Preserve Phase 0.5
    ↓
Add Event / State extension
    ↓
Add Hardware abstraction
    ↓
Add AI Job isolation
    ↓
Real-device integration
    ↓
NPU coexistence verification
```

将来拡張のためだけに先行実装しない。

---

## 2. 実装ルール

実装前に以下を確認する。

- `AGENTS.md`
- `docs/development/workflow.md`
- `docs/specs/phase-0.8-stationary-ai-robot.md`
- `docs/progress/phase-0.5-progress.md`
- 関連 ADR
- 現行 `runtime/` と `tests/runtime/`

実装中に、既存仕様だけでは決められない問題が出た場合:

```text
Problem
  ↓
Existing spec だけで修正可能?
  ├─ Yes → Bug Fix / Test
  └─ No  → GitHub Design Issue
              ↓
           再設計
              ↓
           Design PR
              ↓
           Review / Merge
              ↓
           Implementation 再開
```

Coding Agent が設計判断を独自に確定しない。

---

## 3. Branch / PR

実装 branch:

```text
implementation/phase-0.8
```

実装完了後、この branch から `main` へ Implementation PR を作成する。

Implementation PR の実装レビュー担当は Codex。

PR には Acceptance Criteria の確認状況を記載する。

---

## 4. Milestone 0 — Baseline Regression

### Goal

Phase 0.8 の変更前に Phase 0.5 の既存挙動を基準として固定する。

### Tasks

- 現行 Runtime / Test を読む
- 既存自動テストを実行する
- 既存 CLI 互換性を確認する
- Phase 0.5 の stdin JSONL path を変更しない
- 既存 `RobotLoopRecord` schema を変更する場合は後方互換性を明示する

### Verification

PC / Raspberry Pi で可能な範囲:

```bash
python -m unittest discover -s tests -t .
```

既存 test failure がある場合、Phase 0.8 実装開始前に原因を切り分ける。

### Related AC

- AC-01
- AC-02
- AC-03
- AC-05
- AC-06
- AC-07
- AC-31
- AC-32

---

## 5. Milestone 1 — Event / State Foundation

### Goal

Phase 0.5 の同期 Core を維持しながら、Vision 以外の Event Source を扱える最小基盤を追加する。

### Important Constraint

Runtime Core 自体を asyncio へ全面移行しない。

Phase 0.5 の stdin / SIGINT / Shutdown の実機確認済み挙動を不用意に壊さない。

### Tasks

- State 型と Event 型を区別できる最小 data model を追加
- Runtime State を必要最小限で追加
- Vision State は latest-only で扱える構造にする
- Button / AI Result 等の Event は FIFO として扱える構造にする
- 複数 Input Source を同期 Runtime へ渡す最小 Multiplexing 方法を実装する
- 既存 Detection JSONL の parser / adapter 境界を維持する
- 既存 `Reasoner → ActionPlanner → Executor → Logger` の責務を維持する

### Implementation Note

Input Multiplexing の実装方式は、既存 SIGINT / Shutdown を壊さないことを優先する。

候補例:

- producer thread + synchronized queue
- OS primitive を使った multiplexing
- その他の最小方式

実装調査の結果、Architecture 変更が必要な場合は Design Issue を起票する。

### Tests

- Vision State を連続投入しても backlog が無制限に増えない
- Event FIFO ordering
- Phase 0.5 Detection fixture が従来通り処理される
- EOF / stop / SIGINT の既存 unit test を維持
- Runtime State update

### Related AC

- AC-04
- AC-08
- AC-09
- AC-21
- AC-30

---

## 6. Milestone 2 — Hardware Abstraction + Fake Adapter

### Goal

Whisplay 実機到着前でも Runtime の Action / Event 経路を実装・テストできるようにする。

### Tasks

- Whisplay 固有 API を隠す Adapter interface を追加
- Fake / Mock Adapter を追加
- Generic Action を必要最小限追加
  - Display message
  - LED status
  - Play audio
- Button Event の Fake source を追加
- Device availability / failure を表現する最小状態を追加
- 非必須 I/O failure で Runtime 全体を停止しない
- Hardware failure を Application Log / Robot Event Log へ残す

### Constraint

Reasoner と Runtime Core から GPIO / PiSugar / Whisplay driver を直接参照しない。

### Tests

Fake Adapter で以下を確認する。

```text
Fake Button
  ↓
Event
  ↓
Rule Reason
  ↓
Display / LED / Speaker Action
  ↓
Fake Adapter
  ↓
Log
```

### Related AC

- AC-10
- AC-11
- AC-19
- AC-20
- AC-23
- AC-24
- AC-25
- AC-30

---

## 7. Milestone 3 — Structured Event Log / Traceability

### Goal

Vision / Button / AI Result を一つの処理単位として追跡可能にする。

### Tasks

- Phase 0.5 `RobotLoopRecord` を壊さず schema evolution を設計・実装
- `cycle_id` または同等の correlation identifier を導入
- AI Job 用に必要なら `job_id` を関連付ける
- Application Log と Robot Event Log の分離を維持
- schema version を更新する場合は migration / compatibility を明記

### Constraint

既存 Phase 0.5 log reader が存在しないことを推測しない。

既存 schema を変更する場合は、影響範囲をコード・テストから確認する。

### Tests

- 1 cycle を Observation / Event → Reason → Action → Result まで追跡できる
- JSONL として parse 可能
- log write failure の既存 failure policy を維持

### Related AC

- AC-21
- AC-22
- AC-23

---

## 8. Milestone 4 — AI Job Foundation with Fake Backend

### Goal

実 NPU を使わずに、AI Job の非同期性、timeout、failure、backpressure を検証する。

### Tasks

最初は `runtime/ai.py` 等の最小構成で開始する。

最低限:

```text
AIJob
AIJobStatus
AIResult
AIBackend Protocol
FakeAIBackend
AIJobManager
NPU resource state boundary
```

AI Job の status:

```text
QUEUED
RUNNING
COMPLETED
FAILED
TIMEOUT
```

`CANCELLED` は必要になった場合のみ実装する。

### Execution Model

- Runtime Core は同期のまま
- AI Job Manager / Worker を Core から隔離
- thread / subprocess は実装時に最小で安全な方式を選ぶ
- AI Result は Event として Runtime へ返す
- AI Job 実行中も Core Event を処理可能にする

### Backpressure

Phase 0.8 default:

```text
same Job Type:
  running = max 1
  pending = latest 1

new request while pending:
  replace pending
```

Priority は data model 上の metadata として保持可能にする。

以下は実装しない。

- Priority Queue
- Preemption
- Starvation control
- Generic scheduler

### Fake Backend Tests

Fake backend で以下を再現する。

- immediate success
- delayed success
- failure
- timeout

必須確認:

```text
AI Job running
    +
Button / Core Event
    → still processed
```

### Related AC

- AC-AI-01
- AC-AI-02
- AC-AI-03
- AC-AI-04
- AC-JOB-01
- AC-33

---

## 9. Milestone 5 — Whisplay Real-device Bring-up

### Entry Condition

Whisplay HAT が実機で利用可能になっていること。

### Goal

Runtime 統合前に各 I/O を単体確認する。

### Procedure

実機上で、現在の Whisplay hardware revision / codec / driver / official sample を確認する。

推測で driver API を決めない。

確認順序は固定しないが、最低限:

- Display
- RGB LED
- Button
- Speaker
- Microphone

を個別確認する。

### Documentation

成功した install / setup / run command を `docs/progress/` へ記録するのは、実機確認後とする。

### Related AC

- AC-12
- AC-13
- AC-14
- AC-15
- AC-16

---

## 10. Milestone 6 — Whisplay Runtime Integration

### Goal

Real Whisplay Adapter を Runtime へ接続する。

### Tasks

- Fake Adapter と同じ上位 interface で Real Adapter を実装
- Button Event を Runtime へ投入
- Display / LED / Speaker Action を実機へ出力
- I/O unavailable 時の graceful degradation
- startup / shutdown / resource cleanup

### E2E

#### Button E2E

```text
Button
 ↓
Event
 ↓
Rule Reason
 ↓
Display / LED / Speaker
 ↓
Robot Event Log
```

#### Vision E2E

```text
Camera
 ↓
Hailo YOLO
 ↓
Detection JSONL
 ↓
Observation
 ↓
Rule Reason
 ↓
Display / LED
 ↓
Robot Event Log
```

### Related AC

- AC-17
- AC-18
- AC-24
- AC-25
- AC-26
- AC-29

---

## 11. Milestone 7 — AI Connectivity Proof

### Goal

STT / LLM / VLM を Phase 0.8 の疎通レベルで確認する。

### 11.1 STT

```text
Microphone
 ↓
short audio
 ↓
STT
 ↓
text
 ↓
Runtime Event / Log
```

本格会話 Agent は作らない。

### 11.2 LLM

```text
simple prompt
 ↓
LLM
 ↓
short response
 ↓
Runtime Event / Log
```

Remote API を使う場合、Core offline operation と secret management を壊さない。

### 11.3 VLM

Phase 0.8 VLM:

```text
on-demand request
 ↓
single Camera Image
 ↓
Local VLM
 ↓
short description
 ↓
AI Result Event
```

Hailo-10H を第一候補 Backend とする。

Streaming VLM は実装しない。

### Related AC

- AC-EXT-01
- AC-EXT-02
- AC-EXT-03
- AC-EXT-04

---

## 12. Milestone 8 — Hailo YOLO / VLM Coexistence Spike

### Goal

NPU Arbiter の具体実装を推測で決めず、実機事実から決める。

### Important

この Milestone は NPU scheduler 実装より先に行う。

### Verify

現在の Raspberry Pi 5 + AI HAT+ 2 で以下を確認する。

```text
continuous YOLO
        +
on-demand Local VLM
```

確認事項:

- 同時利用可能か
- VDevice / device ownership conflict が出るか
- YOLO pipeline に影響するか
- VLM 起動 / 終了後に YOLO が継続できるか
- latency / memory / temperature
- failure 時の復旧

### Decision

#### coexistence possible

最小限の NPU resource visibility / serialization で対応する。

#### coexistence not possible

```text
Vision lifecycle
   ↓
release / stop
   ↓
exclusive AI
   ↓
restart / health check
```

が必要か検討する。

この時点で既存設計だけでは判断できない場合、Design Issue を起票する。

### Related AC

- AC-NPU-01
- AC-NPU-02
- AC-NPU-03
- AC-NPU-04
- AC-EXT-02

---

## 13. Milestone 9 — NPU Arbiter Minimal Implementation

### Entry Condition

Milestone 8 の実機結果が得られていること。

### Goal

実機で必要と判明した最小限の NPU Arbitration のみ実装する。

### Do Not Implement Unless Required

- generic scheduler
- priority scheduling
- preemption
- multi-device scheduling
- distributed ownership

### Tests / Logs

- resource state visibility
- job start / end / failure logging
- uncontrolled concurrent NPU Job を防止
- external YOLO ownership を無視しない

### Related AC

- AC-NPU-01
- AC-NPU-02
- AC-NPU-03
- AC-NPU-04

---

## 14. Milestone 10 — Regression / Automated Verification

### Goal

Phase 0.5 と Phase 0.8 の自動テストを通す。

### Minimum

```bash
python -m unittest discover -s tests -t .
```

確認対象:

- existing Phase 0.5 parser
- Observation conversion
- RuleReasoner
- existing Runtime E2E fixture
- State latest-only
- Event FIFO
- Fake Hardware
- Fake AI success / failure / timeout
- AI Job non-blocking behavior
- Backpressure
- shutdown / cleanup
- structured logging

既存テストを削除して green にしない。

仕様変更により既存テスト更新が必要な場合は、変更理由を PR に明記する。

---

## 15. Milestone 11 — Real-device Acceptance

### Goal

Raspberry Pi 5 実機上で Acceptance Criteria を確認する。

最低限:

- existing Camera / YOLO regression
- Button E2E
- Vision E2E
- Display
- LED
- Speaker
- Microphone
- AI Job running 中の Core responsiveness
- STT / LLM / VLM proof
- NPU coexistence / arbitration
- offline Core
- graceful shutdown
- thermal

Thermal:

```bash
vcgencmd measure_temp
vcgencmd get_throttled
```

固定 threshold を推測で設定しない。

---

## 16. Milestone 12 — Documentation / Progress

実機確認後に以下を更新する。

- `docs/progress/phase-0.8-progress.md`
- 必要な ADR
- README / AGENTS の Current Phase
- 実行手順
- Automated Test 結果
- Real-device Test 結果
- 未確認事項
- Technical Debt
- Phase 1 への課題

未確認項目を Pass として記録しない。

---

## 17. Implementation PR Checklist

Implementation PR には最低限以下を含める。

```markdown
## Summary

## Design / Spec
- docs/specs/phase-0.8-stationary-ai-robot.md

## Automated Tests
- [ ] existing regression
- [ ] new runtime tests
- [ ] fake hardware tests
- [ ] fake AI tests

## Real-device Verification
- [ ] Camera / YOLO regression
- [ ] Whisplay
- [ ] AI connectivity
- [ ] NPU coexistence / arbitration
- [ ] thermal

## Acceptance Criteria
- [ ] AC-...
...

## Design Issues
- None / #issue

## Known Limitations
...
```

Implementation Review は Codex が担当する。

---

## 18. Recommended Implementation Order

Claude Code は以下の順で進める。

```text
0 Baseline Regression
        ↓
1 Event / State Foundation
        ↓
2 Hardware Abstraction + Fake
        ↓
3 Structured Logging
        ↓
4 AI Job + Fake Backend
        ↓
5 Whisplay Bring-up
        ↓
6 Whisplay Runtime Integration
        ↓
7 AI Connectivity Proof
        ↓
8 YOLO / VLM Coexistence Spike
        ↓
9 Minimal NPU Arbiter
        ↓
10 Automated Verification
        ↓
11 Real-device Acceptance
        ↓
12 Progress Update
```

Whisplay 未到着の場合は Milestone 4 まで先行してよい。

NPU Arbiter の具体実装は Milestone 8 の実機結果より前に作り込まない。
