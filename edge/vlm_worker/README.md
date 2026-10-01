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

```bash
python3 -m runtime.robot_runtime --ai vlm
```

venv の Python と HEF の場所は環境変数で変更できる。

| 環境変数 | 既定値 |
|---|---|
| `HAILO_GENAI_PYTHON` | `~/venvs/hailo-apps/bin/python` |
| `VLM_HEF_PATH` | `/usr/local/hailo/resources/models/hailo10h/Qwen2-VL-2B-Instruct.hef` |
