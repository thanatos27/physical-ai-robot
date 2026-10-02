# vlm_worker

Robot Runtime の `--ai vlm` で使う、Hailo-10H 上の VLM worker。
Runtime の `SubprocessAIBackend` が AI Job ごとに起動し、終了まで待つ
(per-job subprocess、`docs/specs/phase-0.8-stationary-ai-robot.md` #15.3)。

処理:

```text
rpicam-still で1枚撮影 → Qwen2-VL-2B-Instruct (Hailo-10H) → 説明文
→ stdout の最後の行に JSON を出力して終了
```

出力例:

```json
{"description": "A computer mouse and a smartphone are placed on a table.", "capture_s": 1.4, "load_s": 9.9, "generate_s": 3.0}
```

失敗時は stderr に理由を出力し、終了コード 1 で終了する。

## 前提

`docs/progress/phase-0.8-progress.md` #6.2 の手順で以下を用意する。

* hailo-apps 26.03.1 を入れた venv: `~/venvs/hailo-apps`
* HEF: `/usr/local/hailo/resources/models/hailo10h/Qwen2-VL-2B-Instruct.hef`
  (Hailo GenAI Model Zoo v5.1.1)

カメラを使うため、連続 Vision (`rpicam-hello`) 実行中は撮影に失敗する。
Vision との共存は Milestone 8 で検証する (#16.4)。

## 単体実行

```bash
~/venvs/hailo-apps/bin/python edge/vlm_worker/vlm_worker.py \
  --hef /usr/local/hailo/resources/models/hailo10h/Qwen2-VL-2B-Instruct.hef
```

## Runtime から使う

連続 Vision を止めた状態で、NPU を AI に割り当てて起動する。

```bash
python3 -m runtime.robot_runtime --ai vlm --npu-mode ai
```

`--npu-mode` の既定は `vision` で、NPU を Vision (rpicam-apps の YOLO) に予約する。
その場合 Button で要求した VLM Job は worker を起動せずに拒否され、理由付きの
AI Result (`REJECTED`) として Robot Event Log に記録される (Design Issue #9)。
rpicam-apps と VLM は NPU を同時に使えないため (Milestone 8)。

`NpuArbiter` は Runtime 管理下の Job に対する受け入れ制御であり、Runtime の外で
起動された `rpicam-hello` 等による NPU の利用は防げない。VLM の実行中に
`rpicam-hello` を起動すると、Vision は検出0件を出し続け再起動まで復帰しない
(`docs/progress/phase-0.8-progress.md` #7)。

venv の Python と HEF の場所は環境変数で変更できる。

| 環境変数 | 既定値 |
|---|---|
| `HAILO_GENAI_PYTHON` | `~/venvs/hailo-apps/bin/python` |
| `VLM_HEF_PATH` | `/usr/local/hailo/resources/models/hailo10h/Qwen2-VL-2B-Instruct.hef` |
