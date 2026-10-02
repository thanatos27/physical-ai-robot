# ADR 0009: Merge Runtime Inputs with FIFO Dispatch and State Coalescing in Phase 0.8

* Status: Accepted
* Date: 2026-09-23
* Phase: 0.8
* Decision record: Issue #2 / PR #3, Issue #4 / PR #5

## Context

Phase 0.5 の Robot Runtime は、stdin の Detection JSONL を1行ずつ読み、1件ごとに Observe → Reason → Action → Log を行う同期ループである (ADR 0007)。SIGINT / Shutdown の挙動は実機で確認済みである。

Phase 0.8 では Vision に加えて Button や AI Result 等の入力が増える。設計仕様は入力を2種類に分ける (`docs/specs/phase-0.8-stationary-ai-robot.md` #10)。

- State 型 (Vision 等): 最新値が重要。古い値を無制限に Queue へ蓄積しない
- Event 型 (Button、AI Result 等): 発生事実。順序を保ち、通常の範囲では drop しない

同期ループが「次に処理する1件」をどう選ぶか (State と Event の merge 順序) は、仕様だけでは決まっていなかった。

また実装中に、Vision を State Coalescing で扱うと、producer が consumer より速い場合に中間の DetectionEvent が配送されず、Phase 0.5 の「valid DetectionEvent 1件 = 1 cycle」という回帰要件と両立しないことがわかった。

## Decision

Runtime Core は同期構造のまま維持し、Core の手前に Dispatch Queue を置いて入力を merge する。

```text
Vision Producer
    ├─ latest_vision を更新
    └─ VISION_STATE_UPDATED を必要時のみ enqueue
                                  │
Button Producer ──────────────────┼→ Dispatch Queue (FIFO)
                                  │
AI Result Producer ───────────────┘
                                  ↓
                         synchronous Runtime Core
```

- Event 型は 1 Event = 1 Queue item とし、FIFO で処理する
- State 型は実データ本体を Queue に積まず最新値として保持し、State 種別ごとに未処理通知を最大1件とする (State Coalescing)
- State 通知と Event の間に優先順位は設けず、Dispatch Queue への enqueue 順で処理する

回帰要件は2つの経路で分ける。

| 経路 | 構成 | 回帰要件 |
|---|---|---|
| Phase 0.5 legacy direct-input path | `JsonlInputSource` → `RobotRuntime` | valid DetectionEvent 1件 = 1 cycle を維持する |
| Phase 0.8 Dispatch path | Vision Producer → State Coalescing → Dispatch Queue → `RobotRuntime` | 中間の Vision State の coalescing を許容し、raw 入力件数と RobotLoopRecord 件数の一致は要求しない |

Phase 0.8 の production path (`main()`) は Dispatch path を使う。Robot Runtime は古い Vision State の全件逐次処理より、処理可能な時点で最新の Vision State へ追従することを優先する。

## Rationale

- Priority Scheduler を導入せずに、Event の取りこぼしと Vision の backlog の両方を避けられる
- Runtime Core の同期構造と、実機確認済みの SIGINT / Shutdown の考え方を維持できる (stdin の読み取りは producer thread へ移し、Core は Dispatch Queue の取り出しで待つ)
- Phase 0.5 の回帰テストを弱めずに残しつつ、Phase 0.8 の production path に適した基準を別に定義できる

## Consequences

- Dispatch path では、Vision の中間フレームの処理を保証しない。全フレームの履歴が必要な用途 (Behavior Cloning、Dataset Logging 等) は、Runtime の Dispatch Queue に全件保持させず、別の Logger 等へ責務を分ける
- State の pending 判定 (check-then-act) は、pending flag の設定とクリアを同じ lock で直列化して実装する
- 将来 IMU / ToF 等の State 型入力を追加する場合も、State 種別ごとに pending 通知最大1件へ拡張する
- 実装: `runtime/dispatch.py` (`DispatchQueue`、`StateChannel`、`DispatchingVisionSource`)
