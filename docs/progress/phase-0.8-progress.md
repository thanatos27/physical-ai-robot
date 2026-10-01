# Physical AI Robot Project --- Phase 0.8 開発進捗

更新日: 2026-10-01

## 1. 目的

Phase 0.5 で実機確認済みの Robot Runtime を据え置き型 AI Robot へ拡張する。
設計は `docs/specs/phase-0.8-stationary-ai-robot.md`、実装計画は
`docs/specs/phase-0.8-implementation-plan.md` を参照。

実装は `implementation/phase-0.8` ブランチで進めている。

## 2. 設計レビュー / Design Issue

設計は ChatGPT、設計レビューは Claude Code という分担で進めた
(`docs/specs/phase-0.8-stationary-ai-robot.md` #24)。

* PR #1: 初期設計のレビュー(AI実行モデル、NPU ownership、Backpressure 等)
* Issue #2 / PR #3: State / Event の merge 順序ポリシー (FIFO Dispatch +
  State Coalescing) を確定
* Issue #4 / PR #5: State Coalescing と Milestone 1 regression 要件の
  矛盾を解消 (Legacy direct-input path と Dispatch path の分離)

いずれも仕様だけでは決められない設計判断は独自に確定せず、GitHub Issue /
PR で判断を仰いでから実装を再開した。

## 3. Milestone 0〜4 (コードレベル、自動テストのみ)

| Milestone | 内容 | 状態 |
|---|---|---|
| 0 | Baseline Regression | 完了 |
| 1 | Event / State Foundation (Dispatch Queue, State Coalescing) | 完了 |
| 2 | Hardware Abstraction + Fake Adapter | 完了 |
| 3 | Structured Event Log / Traceability (schema v0.2) | 完了 |
| 4 | AI Job Foundation with Fake Backend | 完了 |

自動テストは開発 PC (Windows, Python 3.13) で
`python -m unittest discover -s tests -t .` を実行し、77件がパスした。
Raspberry Pi 上での自動テスト実行は Milestone 10 で行う。

主な追加モジュール:

```text
runtime/
├── event.py        Event型入力 (RuntimeEvent, EventQueue)
├── state.py         State型入力 (LatestValueBox, RuntimeWorldState)
├── dispatch.py       Dispatch Queue (FIFO Dispatch + State Coalescing)
├── ai.py             AI Job (AIJobManager, FakeAIBackend)
└── adapters/
    ├── __init__.py   HardwareAdapter Protocol
    └── mock.py        FakeHardwareAdapter, FakeButtonSource
```

Reasoner は Observation (Vision State) に加え RuntimeEvent (Button, AI
Result) も入力として受け取れるよう拡張した。Runtime Core (同期ループ,
SIGINT/Shutdown 処理) 自体は Phase 0.5 から変更していない。

## 4. Milestone 5 --- Whisplay Real-device Bring-up

### 4.1 実機環境

```text
Raspberry Pi 5 Model B Rev 1.1
Linux pi5 6.18.50+rpt-rpi-2712 aarch64 (Debian 13 trixie)
```

Phase 0.5 から環境変更なし。

### 4.2 ドライバインストール

公式リポジトリ (推測で driver API を決めず、公式ドキュメント・公式
サンプルを確認してから実施):

* ドライバ: https://github.com/PiSugar/Whisplay
* ドキュメント: https://docs.pisugar.com/docs/product-wiki/whisplay/overview

```bash
git clone https://github.com/PiSugar/Whisplay.git --depth 1
cd Whisplay
sudo bash install_driver.sh
sudo reboot
```

インストール時に `no PiSugar Whisplay HAT EEPROM detected` という警告が
出たが、ドライバ自体は正常にビルド・インストールされ、再起動後の動作にも
影響しなかった (このボードは HAT EEPROM を持たない、または検出未対応の
個体と見られる)。

### 4.3 オーディオコーデックの実機確認

```bash
dmesg | grep -i -E "whisplay|st7789|es8389|wm8960"
```

```text
whisplay 1-0010: Whisplay probing ES8389 at 0x10
whisplay-soundcard sound: Detected WM8960 at 0x1a on Synopsys DesignWare I2C adapter
whisplay-soundcard sound: Whisplay 'whisplaysound' registered (chip=WM8960)
```

本機は **WM8960 コーデック版** の Whisplay HAT であることを実機で確認した
(ES8389 ではない。両コーデックは Whisplay driver v3.0.0 以降で両対応)。

ALSA デバイス:

```bash
aplay -l | grep -i whisplay
```

```text
card 2: whisplaysound [Whisplay Sound], device 0: Whisplay HiFi wm8960-hifi-0 [Whisplay HiFi wm8960-hifi-0]
```

### 4.4 スピーカー単体確認 (ドライバレベル)

```bash
sox -n -r 48000 -c 2 -b 16 /tmp/t.wav synth 2 sine 440
amixer -c whisplaysound cset name='speaker' 80
aplay -D whisplaysound /tmp/t.wav
```

440Hz のビープ音を確認した。

### 4.5 公式 Run Test (Display / LED / Speaker / Button / Microphone)

公式サンプル (`example/test.py`、`example/run_test.sh`) を推測で改変せず
そのまま実行した。

```bash
sudo apt install -y python3-pil python3-numpy python3-pygame
cd ~/Whisplay/example
python3 test.py
```

```text
Detected hardware: Raspberry Pi 5 Model B Rev 1.1, Backlight mode: PWM
Whisplay sound card detected.
Using Whisplay audio card: whisplaysound (index 2)
Flow: display -> LED -> speaker -> button -> mic
```

確認結果 (すべて実機で目視・聴取により確認、2026-10-01):

* **Display**: 赤/緑/青の単色塗りつぶし、および参照画像の表示を確認 (AC-12)
* **LED**: 赤/緑/青/白の RGB LED 発光を確認 (AC-13)
* **Speaker**: 確認音の再生を確認 (AC-15)
* **Button**: 押下・離上の両方を検出 (AC-14)
* **Microphone**: ボタン長押しで録音、離すと録音内容を再生し、マイク →
  スピーカーのループバックを確認 (AC-16)

### 4.6 実機 API の確認 (Milestone 6 向けメモ)

`example/test.py` から、`runtime/whisplay_client.py` の
`create_whisplay_hardware()` が返す board オブジェクトの実際の公開 API を
確認した。

```text
board.set_backlight(level)
board.fill_screen(color565)
board.draw_image(x, y, width, height, rgb565_bytes)
board.set_rgb(r, g, b)
board.on_button_press(callback)
board.on_button_release(callback)
board.on_exit_request(callback)   # 存在する場合のみ
board.on_focus_revoked(callback)  # 存在する場合のみ
board.cleanup()
board.LCD_WIDTH / board.LCD_HEIGHT
```

Milestone 6 (Whisplay Runtime Integration) で `runtime/adapters/whisplay.py`
(Real Adapter) を実装する際は、この実際の API を基準にする
(推測で API を決めない)。

### 4.7 未確認

* 長時間運転時の熱状態 (Milestone 11 Real-device Acceptance で確認)
* Raspberry Pi 5 + AI HAT+ 2 + Whisplay の物理クリアランス・FFC
  ケーブル取り回し (積層後の外観確認は未実施)

## 5. Milestone 6 --- Whisplay Runtime Integration

### 5.1 実装

* `runtime/adapters/whisplay.py`: `RealWhisplayAdapter`。4.6 の board API に
  合わせて実装した。PiSugar の driver コードはこのリポジトリへ vendor せず、
  外部依存として扱う (`WHISPLAY_DRIVER_DIR`、既定 `~/Whisplay/runtime`)
* Button press は Vision と同じ Dispatch Queue へ `BUTTON_PRESSED` として投入する
  (release は Event を出さない)
* `play_audio` は board に API が無いため `aplay -D whisplaysound` で再生する
* Vision の console report (Phase 0.5 で実機確認済み) は維持し、Display / LED
  へは best-effort でミラーする (`PERSON_DETECTED` → LED 緑、`NO_PERSON` →
  LED 消灯)。ミラー失敗は report の結果に影響させない
* LCD 描画コストが大きいため、display / set_led は直前と同じ内容なら再出力しない
* Whisplay を取得できない場合は Phase 0.5 と同じ console 出力のみで継続する
* `--hardware {auto,none}` を追加した (既定 `auto`。自動テストは `none` で実機に
  触れない)
* Runtime 停止時 (正常 / 異常とも) に cleanup で LED 消灯・board 解放を行う

自動テストは開発 PC で97件パスした (Pillow 未導入のため Display 描画テスト
1件は skip)。

### 5.2 実機確認 (Raspberry Pi 5 + Whisplay HAT、2026-10-01)

実行 (リポジトリルートで):

```bash
# Button E2E (カメラなし)
python3 -m runtime.robot_runtime --log-path /tmp/m6_button.jsonl

# Vision E2E
rpicam-hello -t 30000 \
  --post-process-file edge/detection_logger/hailo_yolov8_logger.json \
  --nopreview | python3 -m runtime.robot_runtime --log-path /tmp/m6_vision.jsonl
```

* **起動:** `Whisplay hardware adapter active` が出力された
* **Button E2E (AC-17):** ボタン押下で LCD に `Button pressed` が表示された。
  5回押して5レコード、`cycle_id` 1〜5、`event` が `BUTTON_PRESSED`、
  `observation` が `null`、`result` はすべて `SUCCESS`
* **Ctrl+C での終了:** traceback なしで `Interrupted; stopping` →
  `Robot Runtime stopped` となった。Vision 読み取りを producer thread へ移した
  後も、実機で SIGINT の挙動が保たれていることを確認した
* **Vision E2E (AC-18):** 人が映ると LCD に `Person detected` が表示され LED が
  緑に点灯、外れると `No person detected` が表示され LED が消灯した
* **Vision 実行中の Button:** 30秒で887レコード (PERSON_DETECTED 176、NO_PERSON
  710、BUTTON_PRESSED 1)。Vision 実行中に押した Button も `cycle_id` 495 として
  処理・記録され、Vision と Button が同じ Dispatch Queue で multiplex された
* **処理レート:** 30秒で887レコード (約29.6件/秒) で、約30fps の入力に対して
  State Coalescing による間引きはほぼ発生しなかった。LCD ミラーを入れても Core
  はフレームレートに追従している
* **EOF での終了:** `rpicam-hello -t 30000` の終了後、`Robot Runtime stopped`
  となり、cleanup により LED が消灯した

### 5.3 観測した挙動と制限

* Vision 実行中は、Button の `Button pressed` 表示が次の Vision フレームの表示で
  すぐに上書きされ、LCD 上ではほぼ見えない (ログには記録される)。1 Decision →
  1 Action の現在の構造による
* カメラの角度によって LCD / LED がちらつくことがある。Phase 0.5 第15.4章の、
  人が映っている間に1〜2フレームだけ検出0件になる挙動による
* LCD の文字は Pillow の既定フォントで描画しており、小さい

### 5.4 未確認

* `PLAY_AUDIO` Action を `RealWhisplayAdapter` 経由で実機再生すること
  (現在の Decision に Speaker を使うものが無い。Speaker 自体は 4.5 で確認済み)
* Whisplay が利用できない状態での縮退運転 (AC-24 / AC-25) の実機での挙動
  (自動テストのみ)
* 異常終了時の cleanup の実機での挙動 (自動テストのみ)
* Internet 接続なしでの Core 動作 (AC-29)
* Raspberry Pi 上での自動テスト実行 (Milestone 10)

## 6. Milestone 7 --- AI Connectivity Proof (疎通確認)

### 6.1 使用したもの

公式の情報・サンプルを確認してから実施した (推測で API / モデルを決めない)。

* API: `hailo_platform.genai` (`VLM` / `LLM` / `Speech2Text`)。システムの
  `python3-h10-hailort 5.1.1` に含まれており、追加インストールは不要だった
* サンプル: Hailo 公式 hailo-apps 26.03.1 の `simple_vlm_chat` /
  `simple_llm_chat` / `simple_whisper_chat`
  (https://github.com/hailo-ai/hailo-apps)。26.03.1 は Hailo-10H の
  HailoRT 5.1.1 対応を明記している
* モデル: Hailo GenAI Model Zoo **v5.1.1** の HEF
  (https://github.com/hailo-ai/hailo_model_zoo_genai/blob/v5.1.1/docs/MODELS.rst)

### 6.2 導入手順

システムの HailoRT を上書きしないよう、hailo-apps は venv
(`--system-site-packages`) へ入れた。hailo-apps の pip 依存に `hailort` は
含まれず、導入後も `hailo_platform` はシステム側
(`/usr/lib/python3/dist-packages`) から読み込まれることを確認した。

```bash
sudo apt install -y portaudio19-dev python3-dev python3-gi
git clone --depth 1 --branch 26.03.1 https://github.com/hailo-ai/hailo-apps.git
python3 -m venv --system-site-packages ~/venvs/hailo-apps
source ~/venvs/hailo-apps/bin/activate
pip install --upgrade pip
cd ~/hailo-apps
pip install -e ".[gen-ai]"

sudo mkdir -p /usr/local/hailo/resources/packages
sudo chown -R $USER:$USER /usr/local/hailo
mkdir -p /usr/local/hailo/resources/models/hailo10h
cd /usr/local/hailo/resources/models/hailo10h
wget -c https://dev-public.hailo.ai/v5.1.1/blob/Whisper-Base.hef
wget -c https://dev-public.hailo.ai/v5.1.1/blob/Qwen2.5-1.5B-Instruct.hef
wget -c https://dev-public.hailo.ai/v5.1.1/blob/Qwen2-VL-2B-Instruct.hef
```

モデルを `hailo-download-resources` ではなく直接取得した理由:

* `hailo-download-resources` は Model Zoo のバージョンを **v5.1.0** と解決し、
  `Qwen2.5-1.5B-Instruct.hef` が 404 になった (v5.1.1 で追加されたモデル)
* `--dry-run` を付けても実際にダウンロードしており、中断すると
  `.<name>.hef.<random>.tmp` が残った (2.0 GB、手動で削除)

### 6.3 実機確認 (Raspberry Pi 5 + AI HAT+ 2 + Whisplay、2026-10-01)

カメラ / Runtime を止めた状態で実行した。

```bash
cd ~/hailo-apps
M=/usr/local/hailo/resources/models/hailo10h
python -m hailo_apps.python.gen_ai_apps.simple_whisper_chat.simple_whisper_chat --hef-path $M/Whisper-Base.hef
python -m hailo_apps.python.gen_ai_apps.simple_llm_chat.simple_llm_chat --hef-path $M/Qwen2.5-1.5B-Instruct.hef
python -m hailo_apps.python.gen_ai_apps.simple_vlm_chat.simple_vlm_chat --hef-path $M/Qwen2-VL-2B-Instruct.hef
```

* **同梱入力:** Whisper は `What is the temperature today?`、LLM は短い
  ジョーク、VLM は `There is one person in the image.` を返した
* **AC-EXT-01 (Mic → STT):** Whisplay マイクで5秒録音
  (`arecord -D whisplaysound -f S16_LE -r 48000 -c 2`、`sox` で 16 kHz /
  モノラルへ変換) し、Whisper-Base で文字起こしできた。ロード込みで約2.3秒
* **AC-EXT-02 (Camera Image → VLM):** `rpicam-still` で撮影した1枚を
  Qwen2-VL-2B-Instruct へ渡し、`A computer mouse and a smartphone are placed
  on a table with a patterned cloth.` を得た (iPhone を写しており内容は妥当)。
  ロード 9.9 秒、推論 3.0 秒。公式サンプルは画像パスが固定のため、同じ API
  呼び出しで画像パスだけ引数にした使い捨てスクリプトで実施した
* **AC-EXT-03 (prompt → LLM):** Qwen2.5-1.5B-Instruct が応答を返した

### 6.4 観測した挙動と制限

* STT の精度が低い。"Hello robot, what do you see?" と英語で話したところ
  `Caron robot, but they see.` となった。原因 (Whisper-Base のモデル規模、
  マイクとの距離・入力レベル、発音等) は未切り分け
* 公式サンプルの Whisper は `language="en"` 固定。日本語での確認は未実施

### 6.5 未確認 / 未着手

* AC-EXT-04 (AI Result を Runtime へ戻し Display または Log で利用):
  実行方式、カメラの所有権、起動トリガー、表示方法が仕様だけでは決められない
  ため、Design Issue #6 で判断を仰いでいる
* VLM と Vision (YOLO) の NPU / カメラ共存 (Milestone 8)

## 7. 次の課題

* Design Issue #6 の判断後、AC-EXT-04 (AI Result の Runtime 統合) を実装する
* Milestone 8: Hailo YOLO / VLM Coexistence Spike
* 5.3 の Button 表示が Vision に上書きされる挙動は、Button に対する UX を
  決める際に設計側で扱う
