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

## 5. 次の課題

* Milestone 6: Whisplay Runtime Integration (`runtime/adapters/whisplay.py`
  の実装、Button Event / Display / LED / Speaker Action の実配線)
* Milestone 7 以降: AI Connectivity Proof、NPU 実機検証
