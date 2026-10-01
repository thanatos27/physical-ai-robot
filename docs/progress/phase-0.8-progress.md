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

### 6.5 Runtime 統合 (AC-EXT-04) の実装

実行方式・カメラの所有権・起動トリガー・表示方法は仕様だけでは決められない
ため Design Issue #6 で判断を仰ぎ、PR #7 で暫定方針が確定した
(spec #15.3 / #16.4、implementation plan #11.4)。

```text
Whisplay Button → VLM_REQUESTED → REQUEST_VLM (受付表示 "Button pressed")
  → AIJobManager → SubprocessAIBackend (per-job subprocess)
  → edge/vlm_worker (hailo-apps venv: rpicam-still 1枚 → Qwen2-VL → JSON)
  → AI_RESULT Event → Robot Event Log (event.payload)
```

* `edge/vlm_worker/vlm_worker.py`: hailo-apps venv の Python で動く worker。
  Runtime 本体は標準ライブラリのみを維持する
* `SubprocessAIBackend`: Job ごとに worker を起動し、timeout / shutdown 時は
  terminate / kill して reap してから戻る
* `AIJobManager`: timeout の Event は即時に出すが、次の pending Job は worker が
  終了するまで開始しない
* `AIRequestExecutor`: Job を投入し、投入した `job_id` を `ActionResult.detail`
  に残す。要求した cycle と AI Result の cycle を Log 上で対応付けられる
* `--ai {none,vlm}` (既定 `none`)。Vision 実行中のカメラ共有は未検証のため
  明示指定時のみ有効。前提 (venv の Python / worker / HEF) が無ければ AI なしで
  継続する。VLM 出力文の LCD 表示は Milestone 7 では行わない

### 6.6 実機確認 (Raspberry Pi 5 + AI HAT+ 2 + Whisplay、2026-10-01〜02)

実行 (リポジトリルートで、連続 Vision は止めた状態):

```bash
python3 -m runtime.robot_runtime --ai vlm --log-path /tmp/m7_vlm3.jsonl
```

* **AC-EXT-04:** Button 押下で `VLM_REQUESTED` の cycle が記録され、十数秒後に
  `AI_RESULT` (`COMPLETED`) の cycle が記録された。両者の `job_id` が一致し、
  `event.payload.output` に説明文と所要時間が記録された
* **受付表示:** LCD が `Button pressed` → `AI result received` と切り替わった
* **Backpressure:** 2秒以内に3回押すと、実行中1件 + pending 1件となり、
  2件目は3件目に置き換えられ実行されなかった (AI Result は2件)
* **失敗時:** カメラ未接続時は worker が `rpicam-still failed: ... no cameras
  available` で失敗し、理由が AI Result の `detail` に記録された。Runtime は
  停止しなかった
* **Job 実行中の Ctrl+C:** `Stopping AI worker (pid=...)` の後、worker は
  SIGTERM で約0.05秒で終了し (`-15`)、Runtime は正常終了した。worker は残らず、
  直後の worker 単体実行も成功し NPU が解放されていることを確認した
* **所要時間:** 起動直後の最初の Job だけロードが約31秒、以降は約9.9秒
  (撮影 約1.3秒、推論 約3〜9秒)。最初の1回は HEF がページキャッシュに無いため
  と考えられる。Runtime 側の timeout (60秒) には最初の1回でも約20秒の余裕がある

### 6.7 実機確認で見つかり修正した問題

* **停止待ちの無表示:** worker はモデルロード中に SIGTERM へすぐ応答できず、
  shutdown の待機が無表示で止まって見えた。そこで2回目の Ctrl+C を押すと
  traceback で異常終了した → 待機をログに出し、待機中の Ctrl+C は即時 kill と
  して扱うよう修正 (`b4e6d2a`)
* **HailoRT の abort:** Job 実行中の Ctrl+C で、端末の SIGINT が worker にも
  届き、HailoRT の `poll` が EINTR で中断されて abort した (`buffer overflow
  detected`、SIGABRT)。NPU はプロセス終了後に再利用できた → worker を別セッション
  で起動し端末の SIGINT を届けないようにし、Python の SIGTERM ハンドラ (native
  の待機を EINTR で中断させる) を削除した (`f3619a8`)

### 6.8 Whisplay 積層時の LCD 不安定 (Design Issue #8)

Milestone 7 の作業中の再起動後、公式 `test.py` を含め LCD に描画されなくなった
(バックライトのみ点灯)。切り分けの結果:

* 起動設定 (`config.txt` は 19:27 から未変更)、電源 (`throttled=0x0`)、ピン設定
  (`pinctrl`)、Runtime のコードは原因ではない
* AI HAT+ 2 を外して Whisplay を Pi に直接載せると安定した
* AI HAT+ 2 を戻して丁寧に積層し直すと概ね動作したが、SPI 100 / 32 MHz で
  ときどき下部に太い線のノイズが出た。8 MHz ではノイズを観測していない
  (PiSugar の既定は 100 MHz)

積層の嵌合状態で LCD がほぼ使えなくなり、正しく嵌合していても高速 SPI の余裕が
小さいと考えられる (原因を SPI clock のみとは断定しない)。

**決定 (Design Issue #8):** Phase 0.8 では LCD の SPI clock を暫定 8 MHz とし、
表示の安定性を優先する。組み立て時は GPIO stacking header の嵌合状態を確認する。
最終値は Milestone 11 で 8 / 16 / 32 MHz を比較して決める。8 MHz でも再発する
場合はハードウェア側の対策を検討する。

**実装 (`8b6dc1a`):** `RealWhisplayAdapter` が SPI clock を設定し (既定 8 MHz、
`WHISPLAY_SPI_HZ` で上書き可)、その速度で LCD を初期化し直す。PiSugar の
`WhisplayBoard` は生成時に 100 MHz で LCD を初期化するため、初期化し直しには
PiSugar の非公開メソッド (`_reset_lcd` / `_init_display`) を使う。

**実機確認 (2026-10-02、8 MHz):**

* 起動時に `Whisplay LCD SPI speed: 8000000 Hz` が出力された
* Button E2E、Vision E2E とも LCD にノイズ・欠けは無かった
* Vision E2E (30秒) の処理件数は 674 件 (約22.5件/秒、PERSON_DETECTED 288、
  NO_PERSON 386)。Milestone 6 (100 MHz) の 887 件より約213件少ない
* 表示の切り替わりは 53 回。8 MHz での1画面 (240x280、RGB565) の描画は約0.13秒で、
  53 回 × 約0.13秒 ≒ 約6.9秒 ≒ 30fps で約207フレーム分となり、処理件数の減少を
  ほぼ説明できる。描画中に届いた Vision は State Coalescing で最新値にまとめられる
  ため backlog は溜まらず、Core の停止は1回あたり約0.13秒 (AC-27 の数秒単位の
  遅延には当たらない)
* Milestone 6 のログは残っておらず、100 MHz 時の切り替わり回数との厳密な比較は
  できていない

AI HAT+ 2 の付け外しの際にカメラの FFC ケーブルが外れ、再接続後の再起動で
認識が戻った (CSI カメラは起動時にのみ検出される)。AI HAT+ 2 は再装着後も
HAILO10H (FW 5.1.1) として認識されている。

### 6.9 未確認

* VLM と Vision (YOLO) の NPU / カメラ共存、Vision 実行中に Button を押した
  場合の影響 (Milestone 8)
* 種類の異なる AI Job (STT / LLM / VLM) を同時に実 NPU で実行した場合
  (Milestone 7 で統合したのは VLM のみ。Milestone 8 / 9)
* STT 精度の改善、日本語での認識 (6.4)
* LCD の SPI clock の最終値 (8 / 16 / 32 MHz の比較、Milestone 11)。長時間運転で
  8 MHz でも表示異常が再発しないか

## 7. Milestone 8 --- Hailo YOLO / VLM Coexistence Spike

### 7.1 方法

Phase 0.5 の Vision pipeline (rpicam-apps + `hailo_yolov8_logger.json`、未変更) と、
Milestone 7 の Qwen2-VL-2B-Instruct で、NPU とカメラの共存を実機で確認した
(2026-10-02)。NPU とカメラを切り分けるため、VLM には事前に撮影した静止画を渡した。
実験用スクリプトは `/tmp` に置き、リポジトリのコードは変更していない。

### 7.2 結果

| 実験 | 結果 |
|---|---|
| YOLO 実行中に VLM をロード | VLM の `VDevice` 作成が `HAILO_OUT_OF_PHYSICAL_DEVICES (74)` で失敗。YOLO は全区間約 30 fps で影響なし |
| VLM がロード済みの状態で YOLO を起動 | rpicam-hello は stderr に `HailoRT not ready!` を出しつつ `exit=0` で動き続け、593 フレームすべて `"detections":[]` |
| 上記の状態で VLM が NPU を解放 | 解放後 25 秒以上経っても検出は0件のまま (自然復帰しない)。`HailoRT not ready!` 1343 回 |
| VLM の解放後に YOLO が Hailo を初期化 | 最初のフレームは解放の 0.739 秒後、正常に検出 |
| YOLO 実行中に `rpicam-still` | `Pipeline handler in use by another process` で失敗 (exit 255)。YOLO は約 30 fps で影響なし |

所要時間 (warm): VLM ロード約 10 秒 (起動直後の初回は約 31 秒)、推論約 4 秒、
解放 (`release()`) 約 2.75 秒。rpicam-hello の起動から最初のフレームまで約 5 秒。
温度 47〜50 ℃、throttling なし。

### 7.3 原因 (ソース確認)

* rpicam-apps の Hailo stage は `VDevice::create()` を既定パラメータで呼ぶ。HailoRT の
  既定 group_id は `"UNIQUE"` で NPU を専有する
* プロセス間共有には `multi_process_service` (HailoRT service) が必要だが、この環境には
  HailoRT service が無い
* rpicam-apps の vdevice はプロセス内シングルトンで、起動時の確保に失敗すると再試行しない
* コミュニティ記事にあった環境変数 `HAILO_VDEVICE_GROUP_ID` は、公開されている HailoRT の
  ソースには見当たらなかった

### 7.4 わかったこと

* 現行の rpicam-apps のままでは、YOLO と VLM は NPU を同時に使えない。カメラも同時に
  使えないが、撮影の失敗は動作中の Vision に影響しない (Milestone 7 のレビューで残した
  「Vision 実行中の Button 押下」は Vision に影響しない)
* 常駐 worker / model resident は、待機中も NPU を専有するため連続 YOLO と両立しない
* AI が NPU を保持している間に Vision が起動すると、Vision は検出0件を出し続け、
  再起動するまで復帰しない。ADR 0008 で「正常な検出0件と推論失敗を区別できない」とした
  制限が、実際の故障モードとして現れた
* 現在の Runtime は Vision process を所有していない (シェルの pipe で stdin から受け取る)
  ため、Runtime から Vision を停止・再開できない

Milestone 9 (NPU Arbiter) の方式は Design Issue #9 で判断を仰いでいる。

## 8. 次の課題

* Design Issue #9 の判断後、Milestone 9 (NPU Arbiter Minimal Implementation)
* Milestone 11: LCD の SPI clock (8 / 16 / 32 MHz) の比較 (Design Issue #8)
* 5.3 の Button 表示が Vision に上書きされる挙動は、Button に対する UX を
  決める際に設計側で扱う
