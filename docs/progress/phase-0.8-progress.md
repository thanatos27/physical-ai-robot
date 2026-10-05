# Physical AI Robot Project --- Phase 0.8 開発進捗

更新日: 2026-10-02

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
* 表示の切り替わりは 53 回。描画中に届いた Vision は State Coalescing で最新値に
  まとめられるため backlog は溜まらない
* **訂正 (Milestone 11):** 当初、8 MHz の1画面描画を約0.13秒 (SPI 転送時間のみの
  理論値) とし、「53 回 × 約0.13秒 ≒ 約207フレーム分で処理件数の減少をほぼ説明
  できる」と記録した。Milestone 11 で実測した描画時間は約0.18秒 (10.1) で、これで
  計算すると 53 回 × 0.18秒 ≒ 9.5秒 ≒ 約286フレーム分となり、実際の減少 (約213件)
  とは合わない。処理件数の減少と描画時間の関係は説明しきれていない
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

Milestone 9 (NPU Arbiter) の方式は Design Issue #9 で判断を仰いだ (8章)。

## 8. Milestone 9 --- NPU Arbiter Minimal Implementation

### 8.1 決定 (Design Issue #9)

Option D (Vision 動作中は AI Job を実行しない排他ポリシー) を採用した。ただし NPU の
状態を Vision の受信間隔から推定する方式は採らず、起動時に明示したモードで管理する。
`NpuArbiter` は OS / HailoRT レベルのロックではなく、Runtime 管理下の NPU Job に対する
admission control / resource visibility とする。

Vision process の lifecycle 管理 (停止 / 再開 / health check)、Vision と AI の自動
モード切替、HailoRT service による共有、rpicam-apps の Hailo stage の置き換え、
priority scheduling / preemption は Phase 0.8 では実装しない。自動切替には Vision の
推論状態を判定できる信号が前提になるため、別の Design Issue / ADR で扱う。

### 8.2 実装 (`7a6041c`)

* `--npu-mode {vision,ai}` (既定 `vision`)
* `NpuArbiter`: `vision` では状態を `VISION` に固定し AI Job を拒否する。`ai` では
  `FREE -> EXCLUSIVE_AI -> FREE` を管理し、worker の回収後に `FREE` に戻す。遷移は
  Application Log に記録する
* 拒否した Job は worker を起動せず、理由付きの AI Result (`REJECTED`) を返す。
  要求 cycle と同じ `job_id` で Robot Event Log から追跡できる
* `EXCLUSIVE_AI` の間は Job Type が異なる Job も拒否する (AC-NPU-01)。Milestone 4 では
  異なる type を同時に実行していたため、該当する自動テストを新しい仕様に合わせて更新した
* VLM を使う場合は `--ai vlm --npu-mode ai` と指定する

自動テストは開発 PC で 131 件パスした (Pillow 未導入のため1件 skip)。

### 8.3 実機確認 (2026-10-02)

```bash
# vision モード (Vision 実行中に Button)
rpicam-hello -t 30000 \
  --post-process-file edge/detection_logger/hailo_yolov8_logger.json \
  --nopreview | python3 -m runtime.robot_runtime --ai vlm --log-path /tmp/m9_vision.jsonl

# ai モード (Vision なし)
python3 -m runtime.robot_runtime --ai vlm --npu-mode ai --log-path /tmp/m9_ai.jsonl
```

* **vision モード:** 起動時に `NPU mode: vision (state=VISION)`。Button 押下の直後に
  `AI Job rejected: ... (NPU is reserved for VISION (--npu-mode vision))` が出力され、
  worker は起動しなかった。要求 cycle (53) と同じ `job_id` の AI Result (`REJECTED`、
  理由付き) が cycle 55 に記録された。Vision は止まらず、30秒後に正常終了した
* **ai モード:** 起動時に `NPU mode: ai (state=FREE)`。Button 押下で
  `NPU FREE -> EXCLUSIVE_AI`、Job 完了・worker 回収後に `NPU EXCLUSIVE_AI -> FREE`
  (約18.9秒後)。同じ `job_id` の AI Result (`COMPLETED`) が記録された

### 8.4 制限 / 未確認

* Runtime の外で手動起動された `rpicam-hello` 等による NPU の利用は防げない。AI の
  実行中に Vision を起動すると、7.4 の「検出0件を出し続ける」故障が起こり得る
* AI Result は内容に関係なく LCD に `AI result received` と表示するため、`REJECTED`
  も LCD 上では区別できない (ログでは区別できる)
* vision モードの確認時、Vision の処理件数は約30秒で 480 件 (約16件/秒) で、Issue #8 の
  確認時 (674 件) より少なかった。人の検出の切り替わりが多く、8 MHz での LCD 描画が
  増えたためと考えられるが、切り替わり回数は計測していない

## 9. Milestone 10 --- Regression / Automated Verification

### 9.1 結果 (2026-10-02)

```bash
python3 -m unittest discover -s tests -t .
```

| 環境 | 結果 |
|---|---|
| 開発 PC (Windows, Python 3.13) | 131 件パス (Pillow 未導入のため LCD 描画テスト1件 skip) |
| Raspberry Pi 5 (Debian 13, システムの python3) | **131 件パス、skip なし**。実機の Whisplay を一度も初期化していない (`Detected hardware` の出力 0 回) |

Phase 0.5 から未確認だった「Raspberry Pi 上での自動テスト実行」も確認できた。

### 9.2 既存テストの扱い

Milestone 0 時点 (`8bd7d60`) の 25 件のテストは、削除・改名されたものは無い。内容を
更新したテストは、いずれも仕様変更に伴うもので、理由をコミットに記録している。

* Dispatch path では raw 入力件数と RobotLoopRecord 件数の一致を求めない (PR #5)
* schema v0.2 (`cycle_id`、`event`) (Milestone 3)
* `main()` を経由するテストに `--hardware none` を追加 (Milestone 6)

Phase 0.8 で追加したテストのうち、Milestone 4 の「異なる Job Type は同時に実行する」
テストは、Milestone 9 (`EXCLUSIVE_AI` の間は異なる type も拒否) に合わせて更新した。

### 9.3 確認対象とテストの対応

| 確認対象 (implementation plan #14) | 主なテスト |
|---|---|
| Phase 0.5 parser | `test_input` |
| Observation conversion | `test_observation` |
| RuleReasoner | `test_reasoner` |
| Phase 0.5 legacy direct-input E2E (1件 = 1 cycle) | `test_runtime.RobotRuntimeTest` |
| Phase 0.8 Dispatch path | `test_dispatch`、`test_runtime.MainTest` / `CliEndToEndTest` |
| State latest-only | `test_state`、`test_dispatch.StateChannelCoalescingTest` |
| Event FIFO | `test_event`、`test_dispatch.DispatchQueueEventOrderingTest` |
| Fake Hardware | `test_adapters`、`test_hardware_executor`、`test_whisplay_adapter` |
| Fake AI success / failure / timeout | `test_ai.AIJobManagerLifecycleTest`、`FakeAIBackendTest` |
| AI Job non-blocking | `test_ai_runtime_integration` |
| Backpressure | `test_ai.AIJobManagerBackpressureTest` |
| shutdown / cleanup | `test_ai.AIJobManagerShutdownTest`、`test_subprocess_backend`、`test_runtime.MainWhisplayTest`、`test_vlm_integration.MainVlmTest` |
| structured logging | `test_runtime.ButtonEndToEndTest`、`test_vlm_integration` |

### 9.4 Raspberry Pi 上の実行で見つかり修正した問題

最初の実行で、`test_missing_driver_is_device_unavailable` が**実機の Whisplay を
初期化して**失敗した。`RealWhisplayAdapter` が `~/Whisplay/runtime` を `sys.path` に
追加したまま戻さないため、`WHISPLAY_DRIVER_DIR` を空にしても本物の `whisplay_client`
が import されていた。`MainWhisplayTest` の同種のテストも、実行順しだいで同じ状態に
なり得た (開発 PC で、偽の「本物のドライバ」を `PYTHONPATH` に置いて再現)。

テストの間だけ `whisplay_client.py` を含むディレクトリを `sys.path` から除き、読み込み
済みのモジュールも外す `isolated_driver_import` を追加して修正した (`01a108e`)。

### 9.5 Implementation Review (PR #10、Codex) で見つかり修正した問題

* **[P1] worker の起動と shutdown の競合:** `Popen()` が lock の外で実行されていたため、
  生成から登録までの間に shutdown が走ると worker を見落とし、shutdown 後の起動も拒否
  できなかった。`AIJobManager` の `submit()` / `_on_job_finished()` から `_start()` までの
  間に shutdown が来た場合も同様。Runtime の終了後も worker が残り、NPU を保持し続ける
  可能性があった → backend に closed 状態を持たせ、「closed の確認 → 起動 → 登録」を
  1つの lock の中で行うよう修正した
* **[P2] 撮影用の子プロセスの残存:** terminate / kill の対象が worker 本体だけで、撮影用の
  `rpicam-still` 等が残り、カメラを保持し続ける可能性があった → POSIX では worker の
  プロセスグループ全体を停止し、最後にグループ全体を強制終了するよう修正した。開発 PC
  (Windows) では worker 本体だけを停止する

修正は `b8b6ad0`。待ち合わせを制御した回帰テストを5件追加した。P1 の3件は修正前の
コードで失敗することを開発 PC で確認した。P2 の2件 (POSIX のみ) は Raspberry Pi で
パスしたが、修正前のコードで失敗することは確認していない。

修正後の自動テスト: 開発 PC 136 件パス (Pillow 未導入の1件と POSIX 専用の2件を skip)、
Raspberry Pi 136 件パス (skip なし、実機の Whisplay の初期化 0 回)。

## 10. Milestone 11 --- Real-device Acceptance

実機確認日: 2026-10-02 (Raspberry Pi 5 + AI HAT+ 2 + Whisplay HAT、積層構成)

### 10.1 LCD の SPI clock 比較 (Design Issue #8)

`RealWhisplayAdapter.display()` を `Person detected` / `No person detected` で交互に
40 回 (0.5 秒間隔) 描画し、速度ごとに描画時間を測った。同じ手順を 3 回行った。

| SPI | 中央値 | 最大 | SPI 転送の理論値 | 差 (転送以外) |
|---|---|---|---|---|
| 8 MHz | 180 ms | 194 ms | 134 ms | 約 46 ms |
| 16 MHz | 116 ms | 129〜155 ms | 67 ms | 約 49 ms |
| 32 MHz | 83 ms | 96 ms | 34 ms | 約 49 ms |

描画時間は「転送以外の約 48 ms (Python での文字描画と RGB565 変換) + SPI 転送時間」
でよく説明できる。

LCD のノイズ (目視) は、1 回目は 16 / 32 MHz、2 回目はなし、3 回目は 8 / 16 MHz で
出た。**8 MHz でも再発し、速度を下げても無くならない。** Design Issue #8 の
「8 MHz でも表示異常が再発する場合はハードウェア側の対策を検討する」に該当した。

**Design Issue #8 の再 Open と追加判断:**

* 8 MHz は最終解決策とみなさず、SPI clock は未確定に戻す (コードの既定値 8 MHz は
  ハードウェア改善後の再評価まで変更しない)
* ハードウェア側の積層 / 固定の改善 (stacking header、spacer 等) を主対策とし、改善後に
  8 / 16 / 32 MHz を再評価する。安定性が同程度なら描画時間の短い 32 MHz を第一候補とする
* ソフトウェア側では LCD の高頻度更新を抑制する方向を検討する
* 周期的な LCD 再初期化は根本対策ではなく Recovery 策として扱う
* Issue #8 はハードウェア改善後の再評価まで継続する

### 10.2 30 分連続稼働 (AC-02 / AC-28)

```bash
rpicam-hello -t 1800000 --post-process-file edge/detection_logger/hailo_yolov8_logger.json \
  --nopreview | python3 -m runtime.robot_runtime --log-path /tmp/m11_long.jsonl
```

(SSH 切断に備えて `nohup` で実行。温度は 30 秒ごとに `vcgencmd` で記録)

* 30 分で 42,578 件 (約 23.7 件/秒)、表示の切り替わり 2,802 回。Runtime / rpicam-hello
  ともエラー 0 件で、EOF で正常終了した
* **温度 47.7〜54.3 ℃、62 回の記録すべてで `throttled=0x0`** (AC-28)
* **約 15 分後から LCD に文字が表示されなくなった** (バックライトは点灯し、点滅する
  ような状態)。描画失敗のログは無い。その後 LCD を初期化し直すと表示が戻った。
  LCD コントローラが途中でおかしな状態になり、初期化するまで戻らないと考えられる
  (推測)。Issue #8 に記録した
* 切り替わりのたびに描画しており、8 MHz では 30 分のうち約 500 秒 (約 28%) が LCD
  描画に使われている計算になる。Phase 0.5 の判定のちらつき (15.4) が描画量を増やしている

### 10.3 AI Job 実行中の Core 応答性 (AC-27 / AC-AI-01)

`--ai vlm --npu-mode ai` で Button を押して VLM を起動し、実行中にさらに2回押した。

* VLM の実行中 (07:49:47〜07:50:08) に押した2回の Button が、その間に cycle として
  処理された。2件目は3件目に置き換えられ実行されなかった (Backpressure)
* 1件目の worker 回収後に NPU が解放され、同じミリ秒で次の Job が NPU を獲得した
* Button を押した瞬間の時刻は記録していないため、押してから処理されるまでの遅れ
  自体は測っていない

### 10.4 縮退運転と継続不能時の終了 (AC-24 / AC-25 / AC-26)

* `WHISPLAY_DRIVER_DIR=/nonexistent` で Vision を 10 秒動かした。原因つきで
  `Whisplay unavailable; continuing with console output only` を記録し、console 出力
  のみで処理を続け `exit=0`
* `--log-path /proc/m11/robot.jsonl` (Robot Data Log を保存できない) で起動した。
  Whisplay の初期化後に `Robot Runtime failed` と traceback を記録して `exit=1` で終了し、
  プロセスは残らなかった。LED は元から消えていたため、cleanup で消灯したことは
  目視では確認できていない (cleanup の実行は自動テストで確認済み)

### 10.5 インターネット接続なしでの動作 (AC-29)

LAN は接続したまま、デフォルトルート (eth0 / wlan0 の2本) を一時的に削除して
インターネットに出られない状態 (`ping: connect: Network is unreachable`) を作り、
90 秒後に自動で戻した。

```bash
sudo -v   # 先に前面で認証しておく (バックグラウンドの sudo はパスワードを入力できない)
ip route show default > /tmp/m11_default_routes.txt
sudo bash -c 'while read -r r; do ip route del $r; done < /tmp/m11_default_routes.txt; sleep 90; while read -r r; do ip route add $r; done < /tmp/m11_default_routes.txt' &
```

その状態で Vision E2E を 20 秒動かし、Button も押した。Camera / YOLO / Runtime /
Rule Reason / Whisplay (Button、LCD) / Log が動作し、`exit=0` で終了した。

### 10.6 Acceptance Criteria の状況

| AC | 状況 | 根拠 |
|---|---|---|
| AC-01 Runtime Lifecycle | 実機 OK | 各 Milestone |
| AC-02 Existing Vision Input | 実機 OK | 10.2 (30 分) |
| AC-03 Observation | 実機 OK | 5.2 |
| AC-04 State Update | 自動テスト | 9.3 |
| AC-05 Rule Reason (AI 無効) | 実機 OK | 5.2 |
| AC-06 Core Loop | 実機 OK | 5.2 |
| AC-07 Shutdown | 実機 OK | 5.2、6.6 (Ctrl+C / EOF / worker) |
| AC-08 State Backpressure | 実機 OK | 6.6、10.2 |
| AC-09 Event Ordering | 自動テスト + 実機 | 9.3、5.2 |
| AC-10 Deterministic Rule | 自動テスト | 9.3 |
| AC-11 AI-independent Core | 実機 OK | `--ai none` の各確認 |
| AC-12 Whisplay Display | **条件付き (Known Limitation)** | 表示はできるが、積層構成でノイズや長時間稼働時の表示停止がある (10.1 / 10.2 / 10.7、Issue #8)。LCD は補助的な HMI とし、Phase 0.8 の完了をブロックしない |
| AC-13 Whisplay LED | 実機 OK | 4.5、5.2 |
| AC-14 Whisplay Button | 実機 OK | 4.5、5.2 |
| AC-15 Whisplay Speaker | 実機 OK | 4.4 / 4.5 (Runtime の `PLAY_AUDIO` 経路は未使用) |
| AC-16 Whisplay Microphone | 実機 OK | 4.5、6.3 |
| AC-17 Button E2E | 実機 OK | 5.2、10.5 |
| AC-18 Vision E2E | 実機 OK | 5.2 (LCD 表示は AC-12 と同じ条件付き) |
| AC-19 Hardware Abstraction | 構造 + 自動テスト | 3、9.3 |
| AC-20 Fake Hardware | 自動テスト | 9.3 |
| AC-21 Traceability | 実機 OK | 6.6 (`job_id` で要求と結果を対応付け) |
| AC-22 Structured Log | 実機 OK | schema v0.2 |
| AC-23 Application Log | 実機 OK | 各 Milestone |
| AC-24 Non-critical Failure | 実機 OK | 10.4、6.6 (カメラ未接続) |
| AC-25 Device Failure Visibility | 実機 OK | 10.4、6.6 |
| AC-26 Fatal Shutdown | 実機 OK | 10.4 (LED 消灯は目視未確認) |
| AC-27 Core Responsiveness | 実機 OK | 10.3。LCD 描画1回あたり約 0.18 秒 (8 MHz) Core が止まる |
| AC-28 Thermal | 実機 OK | 10.2 |
| AC-29 Offline Core | 実機 OK | 10.5 |
| AC-30〜33 | 自動テスト (Pi 含む) | 9.1 |
| AC-AI-01〜04 | 実機 OK | 6.6、10.3 |
| AC-NPU-01〜04 | 実機 OK | 8.3 (Runtime 外の rpicam-hello は防げない制限あり) |
| AC-JOB-01 | 自動テスト | 9.3 |
| AC-EXT-01〜04 | 実機 OK | 6.3、6.6 (STT の精度に課題) |

### 10.7 Issue #8 の再評価と Known Limitation への変更 (2026-10-05)

Issue #8 の追加判断 (ハードウェア側の改善後に SPI clock を再評価する) に沿って再評価した。

**GPIO stacking header の差し替え後 (積層あり):**

* 10.1 と同じベンチを6回実施。1回目は 8 / 16 / 32 MHz とも表示されず (バックライトのみ)、
  速度ごとに LCD を初期化し直しても戻らなかった。2〜6回目のノイズ発生は 8 MHz 1/5、
  16 MHz 2/5、32 MHz 1/5 で、差し替え前 (10.1) とはっきりした違いは無く、速度による差も
  見られなかった
* 32 MHz で 30 分連続稼働し、約 7 分後に表示が止まった (バックライトの点滅のみ)。
  Runtime / rpicam-hello のエラーは 0 件。終了後に LCD を初期化し直すと復帰した

**積層なし (AI HAT+ 2 を外し、Whisplay を Pi 5 に直挿し):**

* Runtime (32 MHz) では、起動直後から表示が 180° 反転した。AI HAT+ 2 が無いため判断は
  30 分間 `NO_PERSON` のままで描画は起動時の1回だけだったので、反転は初期化か最初の
  描画の時点で起きた
* 同じ直挿し構成で、PiSugar 公式 `example/test.py` は安定して動作し、表示の向きも正常だった

**解釈:** 単一の原因には断定できない。AI HAT+ 2 を挟んだ積層経路は LCD 不安定化の大きな
要因である可能性が高い。一方、直挿しでの反転は公式サンプルでは起きず Runtime だけで
起きたため、Runtime 固有の処理 (`_configure_spi()` による SPI clock の変更と、PiSugar の
非公開 API での LCD 再初期化) が関与している可能性がある。

なお、Claude Code は当初、直挿しでの反転を根拠に「積層だけが原因ではない可能性が高い」と
Issue #8 に記録したが、公式サンプルを同じ構成で試していない段階の判断で、踏み込みすぎ
だった。

**決定 (Issue #8):**

* Phase 0.8 では LCD の原因究明を打ち切り、LCD の不安定さを Known Limitation とする
* Whisplay LCD は補助的な HMI として扱い、Runtime / Vision / NPU / AI Job 等の本体機能と
  切り分ける。Phase 0.8 の完了をこの問題だけでブロックしない
* 将来、筐体 / HMI / Hardware 構成を本格化する段階で、別 Display や接続方式も含めて
  再検討する
* Issue #8 の対策として追加した「暫定 8 MHz + 非公開 API による LCD 再初期化」は、問題を
  解消できず、直挿し時の反転に関与している可能性もある。撤去して PiSugar 公式 driver の
  標準動作へ戻すかは別途判断する (それまでコードは変更しない)
* Issue #8 は Close せず、Phase 0.8 でどこまで受け入れ、どの状態で終えるかを整理する

**付記 (LCD とは別の問題):** AI HAT+ 2 が無い状態でも、rpicam-hello は stderr に
`HailoRT not ready` 等を出しながら (54,015 行) `detections: []` を出し続け、Runtime は
30 分間 `NO_PERSON` として処理した。ADR 0008 / 0011 の制限 (正常な検出0件と推論失敗を
区別できない) が実際に現れた事実で、Vision の推論状態の問題として、Phase 1 以降の課題
(11.7) として扱う。

## 11. Phase 0.8 の整理 (Milestone 12)

Phase の完了判断は設計側で行う (`docs/development/workflow.md`)。ここでは判断材料を整理する。

### 11.1 現在の構成

Hardware:

* Raspberry Pi 5 8GB、Active Cooler、27W USB-C Power Supply、microSDXC 128GB
* Raspberry Pi AI HAT+ 2 (Hailo-10H)
* Raspberry Pi Camera Module 3 Wide
* PiSugar Whisplay HAT (WM8960 コーデック版)。AI HAT+ 2 の GPIO stacking header 上に積層

Software:

* Robot Runtime (`runtime/`、Python 標準ライブラリのみ)
* `detection_logger` (`edge/detection_logger/`、Phase 0.5 から変更なし)
* VLM worker (`edge/vlm_worker/`、hailo-apps venv で実行)
* 外部依存 (リポジトリには含めない): PiSugar Whisplay driver (`~/Whisplay`)、hailo-apps
  26.03.1 (`~/venvs/hailo-apps`)、Hailo GenAI Model Zoo v5.1.1 の HEF
  (`/usr/local/hailo/resources/models/hailo10h/`)
* HailoRT 5.1.1 / TAPPAS 5.1.0 はシステムパッケージのまま (Phase 0.5 から変更なし)

実行方法は `README.md`、導入手順は本書 4.2 (Whisplay) と 6.2 (hailo-apps / モデル) を参照。

### 11.2 技術判断

* ADR 0009: FIFO Dispatch + State Coalescing、回帰の境界 (legacy path / Dispatch path)
* ADR 0010: AI Job を per-job subprocess で実行 (Phase 0.8 の暫定方式)
* ADR 0011: NPU を明示的なモードで管理 (`--npu-mode`)
* Design Issue #8 (Whisplay LCD の表示): Phase 0.8 では Known Limitation とし、原因究明を
  打ち切る (10.7)。Issue は Close せず、回避策の撤去は別途判断

### 11.3 結果のまとめ

* Automated Test: 開発 PC / Raspberry Pi とも 136 件パス (Implementation Review の指摘
  対応後、9.5)
* Real-device Test: Acceptance Criteria の状況は 10.6。AC-12 (LCD) のみ条件付き

### 11.4 既知の制限

* Whisplay LCD の表示が不安定 (Issue #8、10.1 / 10.2 / 10.7)。積層構成ではノイズや長時間
  稼働での表示停止があり、GPIO stacking header の差し替えでも、SPI clock (8 / 16 / 32 MHz)
  を変えても解消しなかった。初期化し直すと復帰することが多いが、必ずではない。直挿し構成
  では Runtime でのみ表示が 180° 反転した。LCD は補助的な HMI として扱い、本体機能
  (Runtime / Vision / NPU / AI Job) とは切り分ける
* YOLO (rpicam-apps) と VLM は NPU を同時に使えない。`--npu-mode` で明示的に切り替える。
  Runtime の外で起動された `rpicam-hello` は防げず、AI の実行中に Vision を起動すると
  検出0件を出し続ける (7.4、ADR 0011)
* Dispatch path では Vision の中間フレームの処理を保証しない (ADR 0009)
* Vision 実行中は、Button の表示がすぐ Vision の表示で上書きされる (5.3)
* AI Result は内容に関係なく LCD に `AI result received` と表示し、`REJECTED` も区別
  できない (8.4)
* VLM は Job ごとにモデルをロードするため、1 Job に十数秒かかる (起動直後の初回は
  約 31 秒のロード) (6.6)
* LCD 描画1回あたり Core が約 0.18 秒 (8 MHz) 止まる (10.1)
* STT の精度が低い。英語でのみ確認した (6.4)
* Event 型 cycle の `timestamp` は Runtime の処理時刻で、Vision の検出時刻とは意味が異なる

### 11.5 未確認

* Runtime の `PLAY_AUDIO` Action を実機で再生すること (Speaker 自体は 4.4 / 4.5 で確認)
* STT / LLM の Runtime への組み込み (Milestone 7 で組み込んだのは VLM のみ)
* 継続不能時の終了で、cleanup により LED が消灯すること (10.4。自動テストでは確認済み)
* Button を押してから処理されるまでの遅れそのもの (10.3)
* vision モードの確認時に Vision の処理件数が少なかった理由 (8.4)
* 処理件数の減少と LCD 描画時間の関係 (6.8 の訂正)
* LCD 不安定の原因 (積層経路、Runtime 固有の SPI clock 変更と再初期化の関与。Issue #8 で
  究明を打ち切った)
* 積層構成での PiSugar 公式 `test.py` の長時間稼働 (Runtime の処理と切り分ける比較)
* 30 分を超える連続稼働

### 11.6 Technical Debt

* `RealWhisplayAdapter` は PiSugar の非公開メソッド (`_reset_lcd` / `_init_display`) に
  依存し、ドライバの場所を `sys.path` に追加したまま戻さない。この再初期化 (暫定 8 MHz) は
  Issue #8 を解消できず、直挿し時の反転に関与している可能性もあるため、撤去して PiSugar
  公式 driver の標準動作へ戻すかを別途判断する (10.7)
* PiSugar Whisplay driver の clone は特定の commit を記録していない (2026-10-01 時点の
  `--depth 1`)。hailo-apps は tag 26.03.1 を使用
* `hailo-download-resources` は Model Zoo のバージョンを v5.1.0 と解決するため、v5.1.1 の
  HEF を公式 URL から手動で取得している (6.2)
* LCD の文字描画と RGB565 変換を Python で行っており、1回約 48 ms かかる (10.1)
* `Decision` が内容を持たないため、AI の出力文を表示する Action を作れない
* Vision の推論状態 (正常な検出0件と推論失敗の区別) を示す信号が無い (ADR 0008 / 0011)
* `runtime/ai.py` は1ファイル構成 (責務が増えた時点で分割する方針)
* 自動テストの一部は `time.sleep` による待ち合わせに依存している

### 11.7 Phase 1 への課題

* NPU mode management: Vision の停止・再開と AI の自動切替。前提として Vision の推論
  状態を判定できる信号が要る (ADR 0011)
* 判定の安定化: 1〜2 フレームの検出0件による判定のちらつき (Phase 0.5 15.4)。LCD の
  描画量 (10.2) にも影響している
* Vision の推論失敗の検出: AI HAT+ 2 が無くても Runtime は 30 分間 `NO_PERSON` として
  処理した (10.7 付記)。上の NPU mode management の前提 (推論状態の信号) と同じ課題
* 筐体 / HMI / Hardware 構成: 別 Display や接続方式を含めた LCD の再検討 (Issue #8)。
  Motor 等を追加する前に物理構成を安定させる
* Motor 等の物理 Actuator を扱う際の安全要件 (Emergency Stop、Watchdog 等)
* AI Result の内容を Reason で使うこと、STT の組み込み、日本語での認識

## 12. 次の課題

* Design Issue #8: Phase 0.8 でどこまで受け入れ、どの状態で終えるかの整理。
  `RealWhisplayAdapter` の回避策 (暫定 8 MHz + 再初期化) を撤去するかの判断
* Phase 0.8 の完了判断 (設計側)
* Vision の推論状態を判定する信号 (ADR 0008 の将来課題) と NPU mode management の
  自動切替 (Design Issue #9 で将来課題とした)
* 5.3 の Button 表示が Vision に上書きされる挙動は、Button に対する UX を
  決める際に設計側で扱う
