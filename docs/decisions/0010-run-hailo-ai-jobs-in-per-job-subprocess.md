# ADR 0010: Run Hailo AI Jobs in a Per-job Subprocess (Provisional) in Phase 0.8

* Status: Accepted (provisional for Phase 0.8)
* Date: 2026-10-01
* Phase: 0.8
* Decision record: Issue #6 / PR #7

## Context

Phase 0.8 では VLM / LLM / STT を Hailo-10H 上で動かす。API は HailoRT に含まれる `hailo_platform.genai` (`VLM` / `LLM` / `Speech2Text`) で、Runtime と同じプロセス内で動く native API である。

Milestone 4 の `AIJobManager` は Job を thread で実行していた。実 Hailo Backend を thread で実行すると、次の問題がある。

- timeout しても実行中の native 呼び出しを止められない。`AIJobManager` が TIMEOUT を報告して次の pending Job を開始すると、前の推論が NPU を掴んだまま次の推論が始まる
- native 側の crash が Runtime プロセスごと落とす

また、Robot Runtime は Python 標準ライブラリのみで実装している。AI 処理を Runtime プロセス内で行うと、OpenCV や hailo-apps の venv への依存が Runtime に入る。

## Decision

Milestone 7 の実 Hailo Backend は、Job ごとに worker を subprocess として起動する。

```text
Runtime Core
    ↓
AI Job Manager
    ↓
per-job subprocess (hailo-apps venv の Python)
    ↓
hailo_platform.genai
```

- worker はモデルをロードして1回推論し、結果を stdout の最後の行に JSON で出力して終了する
- worker は hailo-apps 用 venv の Python で起動し、Runtime 本体には OpenCV / hailo-apps 等の依存を持ち込まない
- timeout / failure / shutdown 時は worker を terminate / kill し、wait (reap) まで完了させる。**前 Job の worker が終了したことを確認するまで、同じ NPU を使う次の Job を開始しない**
- 起動トリガーは Button press、AI Result は Event として Robot Event Log に記録する (AC-EXT-04)。VLM の出力文の LCD 表示は行わない

この方式は Milestone 7 の Connectivity Proof を安全に成立させるための暫定方式であり、Phase 0.8 の恒久的な AI worker architecture としては確定しない。常駐 worker、model resident、YOLO との共存は Milestone 8 の実機結果をもとに判断する (ADR 0011)。

## Rationale

- timeout / shutdown 時に worker を kill でき、NPU を確実に解放できる
- native 側の crash が Runtime に波及しない
- Runtime 本体を標準ライブラリのみに保てる

## Consequences

- Job ごとにモデルのロードが入る。実測で Qwen2-VL-2B-Instruct のロードは約 10 秒 (起動直後の初回は HEF がページキャッシュに無いため約 31 秒)。Runtime 側の timeout は 60 秒とした
- 実機で、端末の Ctrl+C (SIGINT) が worker にも届くと、HailoRT の `poll` が EINTR で中断されて abort した (`buffer overflow detected`、SIGABRT)。このため worker は別セッション (`start_new_session=True`) で起動し、Python の SIGTERM ハンドラも登録しない (ハンドラ登録は native の待機を EINTR で中断させる)。プロセス終了後に NPU が再利用できることは実機で確認した
- Milestone 8 で、待機中もモデルを保持する常駐方式は連続 YOLO と両立しないことがわかった (ADR 0011)
- 実装: `runtime/ai.py` (`SubprocessAIBackend`、`AIJobManager`)、`edge/vlm_worker/vlm_worker.py`
