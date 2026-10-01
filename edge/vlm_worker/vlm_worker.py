"""Hailo-10H VLM worker (Milestone 7, per-job subprocess)。

Robot Runtime の `SubprocessAIBackend` から Job ごとに起動され、
カメラで1枚撮影 → Qwen2-VL で説明文を生成 → stdout の最後の行に JSON を
1つ出力して終了する。NPU / カメラは終了時に解放される。

hailo-apps 用 venv の Python で実行する (Runtime 本体は標準ライブラリのみ)。
API の使い方は Hailo 公式 hailo-apps 26.03.1 の simple_vlm_chat に合わせ、
Milestone 7 の疎通確認で実機動作を確認した呼び出しと同じにしている
(docs/progress/phase-0.8-progress.md #6.3)。

単体実行:
    ~/venvs/hailo-apps/bin/python edge/vlm_worker/vlm_worker.py \
        --hef /usr/local/hailo/resources/models/hailo10h/Qwen2-VL-2B-Instruct.hef
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time

import cv2
import numpy as np
from hailo_apps.python.core.common.defines import SHARED_VDEVICE_GROUP_ID
from hailo_platform import VDevice
from hailo_platform.genai import VLM

DEFAULT_PROMPT = "Describe the image in one short sentence."
SYSTEM_PROMPT = "You are a helpful assistant that analyzes images and answers questions about them."
VLM_INPUT_SIZE = (336, 336)


def capture(path: str) -> None:
    subprocess.run(
        ["rpicam-still", "-n", "-t", "1000", "--width", "1280", "--height", "960", "-o", path],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )


def load_frame(path: str) -> np.ndarray:
    image = cv2.imread(path)
    if image is None:
        raise RuntimeError(f"could not read captured image: {path}")
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    return cv2.resize(image, VLM_INPUT_SIZE, interpolation=cv2.INTER_LINEAR).astype(np.uint8)


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture one camera image and describe it with a Hailo VLM.")
    parser.add_argument("--hef", required=True, help="Qwen2-VL HEF path")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--max-tokens", type=int, default=100)
    args = parser.parse_args()

    # SIGTERM にはハンドラを登録しない (既定動作で即時終了)。Python のハンドラを
    # 登録すると native の待機 (HailoRT の poll) が EINTR で中断され、実機で
    # HailoRT が abort した。プロセス終了時にデバイスは解放され、直後の再実行で
    # NPU を利用できることを実機で確認している (phase-0.8-progress #6)。
    vdevice = None
    vlm = None
    try:
        with tempfile.TemporaryDirectory(prefix="vlm-worker-") as tmp:
            image_path = os.path.join(tmp, "frame.jpg")
            t0 = time.monotonic()
            try:
                capture(image_path)
            except subprocess.CalledProcessError as exc:
                raise RuntimeError(f"rpicam-still failed: {exc.stderr.strip()[-300:]}") from exc
            frame = load_frame(image_path)
            t1 = time.monotonic()

            params = VDevice.create_params()
            params.group_id = SHARED_VDEVICE_GROUP_ID
            vdevice = VDevice(params)
            vlm = VLM(vdevice, args.hef)
            t2 = time.monotonic()

            prompt = [
                {"role": "system", "content": [{"type": "text", "text": SYSTEM_PROMPT}]},
                {"role": "user", "content": [{"type": "image"}, {"type": "text", "text": args.prompt}]},
            ]
            response = vlm.generate_all(
                prompt=prompt,
                frames=[frame],
                temperature=0.1,
                seed=42,
                max_generated_tokens=args.max_tokens,
            )
            t3 = time.monotonic()

        # 公式サンプルと同じ後処理 (生成テキスト末尾の制御トークン等を除く)。
        description = response.split(". [{'type'")[0].split("<|im_end|>")[0].strip()
        print(
            json.dumps(
                {
                    "description": description,
                    "capture_s": round(t1 - t0, 2),
                    "load_s": round(t2 - t1, 2),
                    "generate_s": round(t3 - t2, 2),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return 0
    except Exception as exc:  # noqa: BLE001 - 失敗理由を Runtime 側の detail に渡す
        print(f"vlm_worker failed: {exc}", file=sys.stderr, flush=True)
        return 1
    finally:
        if vlm is not None:
            try:
                vlm.clear_context()
                vlm.release()
            except Exception as exc:  # noqa: BLE001
                print(f"VLM release failed: {exc}", file=sys.stderr)
        if vdevice is not None:
            try:
                vdevice.release()
            except Exception as exc:  # noqa: BLE001
                print(f"VDevice release failed: {exc}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
