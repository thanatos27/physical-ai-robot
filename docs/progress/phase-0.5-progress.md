# Physical AI Robot Project --- Phase 0.5 開発進捗

更新日: 2026-09-21

## 1. プロジェクトの目的

最終目標は、実世界で動作する自律ロボットとネットワーク上の AI Agent
を組み合わせ、ロボットが収集した観測・行動ログを学習へ還流できる
Physical AI システムを構築すること。

基本ループ:

``` text
Observe → Reason → Action → Log
   ↑                         ↓
   └──── Learning / Update ──┘
```

将来的には、ロボットのカメラ・センサー・行動ログから環境モデル / Digital
Twin を構築し、Behavior Cloning、RL、Sim2Real、Domain Randomization
等へ発展させる。

## 2. ロードマップ

### Phase 0.5 --- Edge AI 基礎（現在）

Raspberry Pi 5 + AI HAT+ 2 + Camera Module 3 Wide を使い、カメラ観測を
Hailo-10H で推論し、認識結果を Robot Runtime
から利用できるデータへ変換する。

### Phase 0.8 --- Stationary AI Robot

Whisplay HAT
等を追加し、ディスプレイ・マイク・スピーカー・ボタン・LEDを備えた据え置き型AIロボットへ拡張する。

### Phase 1 --- Mobile Robot

モーター、エンコーダー、モータードライバ、ToF、IMU、バッテリー、非常停止等を追加し、自走・障害物回避・行動ログ収集を行う。

### Phase 2 --- LiDAR / SLAM

LiDARを追加し、自己位置推定と2Dマッピングを実装する。

### Phase 3 --- Digital Twin

収集データから3D環境モデルやDigital Twinを構築する。

### Phase 4 --- Learning / Sim2Real

Behavior Cloning、RL、Domain
Randomization、Sim2Real、継続学習へ発展させる。

## 3. Phase 0.5 ハードウェア

-   Raspberry Pi 5 8GB
-   Raspberry Pi AI HAT+ 2
    -   Hailo-10H
    -   40 TOPS INT4
    -   専用 8GB RAM
-   Raspberry Pi Camera Module 3 Wide
    -   IMX708 Wide
-   Raspberry Pi 5 Active Cooler
-   Raspberry Pi 27W USB-C Power Supply
-   KIOXIA EXCERIA G3 microSDXC 128GB

## 4. OS / 基本環境

確認済み環境:

``` text
OS: Debian GNU/Linux 13 (trixie)
Architecture: aarch64
Kernel: 6.18.50+rpt-rpi-2712
```

初期確認時:

``` text
Temperature: 42.8'C
get_throttled: 0x0
```

SSH 接続:

``` bash
ssh kei@pi5.local
```

OS更新:

``` bash
sudo apt update
sudo apt full-upgrade -y
```

## 5. Camera Module 3 Wide

カメラ認識:

``` bash
rpicam-hello --list-cameras
```

確認結果:

``` text
0 : imx708_wide [4608x2592 10-bit RGGB]
```

主なモード:

``` text
1536x864   120.13 fps
2304x1296   56.03 fps
4608x2592   14.35 fps
```

静止画取得にも成功:

``` bash
rpicam-still -o test.jpg
```

## 6. AI HAT+ 2 / Hailo-10H

インストール:

``` bash
sudo apt install dkms
sudo apt install hailo-h10-all
```

主な導入コンポーネント:

``` text
h10-hailort              5.1.1
h10-hailort-pcie-driver  5.1.1
hailo-models             1.0.0-2
hailo-tappas-core        5.1.0
python3-h10-hailort      5.1.1-1
rpicam-apps-hailo-postprocess 1.13.0-1
```

デバイス確認:

``` bash
hailortcli fw-control identify
```

確認結果:

``` text
Executing on device: 0001:01:00.0
Firmware Version: 5.1.1
Device Architecture: HAILO10H
```

これにより PCIe、driver、firmware、Hailo-10H の動作を確認済み。

## 7. YOLOv8 推論

使用モデル:

``` text
/usr/share/hailo-models/yolov8m_h10.hef
```

rpicam-apps 設定:

``` text
/usr/share/rpi-camera-assets/hailo_yolov8_inference.json
```

推論テスト:

``` bash
rpicam-hello -t 10000 \
  --post-process-file /usr/share/rpi-camera-assets/hailo_yolov8_inference.json \
  --nopreview
```

Hailo-10H が推論デバイスとして利用されることを確認。

## 8. Hailo 推論映像のリアルタイム配信

Pi 側:

``` bash
rpicam-vid -t 0 \
  --width 1280 \
  --height 720 \
  --post-process-file /usr/share/rpi-camera-assets/hailo_yolov8_inference.json \
  --nopreview \
  --inline \
  -o tcp://192.168.1.6:8888
```

Windows 側:

``` powershell
ffplay -fflags nobuffer -flags low_delay -framedrop -f h264 "tcp://0.0.0.0:8888?listen=1"
```

Camera → Hailo-10H → YOLOv8 → Bounding Box描画 → H.264 → Ethernet →
Windows ffplay のリアルタイム動作を確認。

腕時計を `clock` として検出することも確認した。

## 9. Detection Metadata の取得

映像上のBounding Boxだけでは Robot Runtime
から判断材料として利用しづらいため、YOLOの検出結果を構造化データとして取得することを目標とした。

調査により rpicam-apps の `Detection` 型を確認:

``` cpp
struct Detection
{
    int category;
    std::string name;
    float confidence;
    libcamera::Rectangle box;
};
```

Hailo post-process binary の調査から metadata tag を特定:

``` text
object_detect.results
```

また、保存される型が以下であることを確認:

``` cpp
std::vector<Detection>
```

したがって内部フローは次のようになる。

``` text
Hailo YOLO inference
        ↓
object_detect.results
        ↓
std::vector<Detection>
```

## 10. 技術判断: GStreamer から rpicam-apps Plugin へ

当初は Python + GStreamer Pad Probe を利用する案を調査した。

Hailo Python APIでは以下を確認:

``` text
HailoROI
HailoDetection
get_roi_from_buffer
get_hailo_detections
```

しかし Raspberry Pi 環境には:

``` bash
gst-inspect-1.0 libcamerasrc
```

に対して:

``` text
No such element or plugin 'libcamerasrc'
```

となり、既存の正常動作している rpicam-apps
カメラパイプラインを作り直すメリットが小さいと判断。

そこで、

``` text
Camera
 ↓
rpicam-apps
 ↓
Hailo
 ↓
自作 Post Processing Stage
```

という方式へ変更した。

## 11. 自作 detection_logger

開発用パッケージ:

``` bash
sudo apt install librpicam-app-dev
sudo apt install libcamera-dev
sudo apt install libboost-dev
```

作業ディレクトリ:

``` text
~/detection-logger/
```

Plugin:

``` text
detection-logger-postproc.so
```

配置先:

``` text
/usr/lib/aarch64-linux-gnu/rpicam-apps-postproc/
```

### detection_logger.cpp

> 注: 現在のソースとビルド手順は `edge/detection_logger/` にある(第15章、`edge/detection_logger/README.md`)。
> 以下は ADR 0008 対応前の版で、`object_detect.results` を取得できないフレームでは何も出力しない。

JSON Lines版(ADR 0008 対応前):

``` cpp
#include <iostream>
#include <vector>
#include <chrono>
#include <iomanip>

#include <rpicam-apps/post_processing_stages/object_detect.hpp>
#include <rpicam-apps/post_processing_stages/post_processing_stage.hpp>

class DetectionLogger : public PostProcessingStage
{
public:
    DetectionLogger(RPiCamApp *app)
        : PostProcessingStage(app)
    {
    }

    char const *Name() const override
    {
        return "detection_logger";
    }

    bool Process(CompletedRequestPtr &request) override
    {
        std::vector<Detection> detections;

        if (request->post_process_metadata.Get(
                "object_detect.results", detections) != 0)
        {
            return false;
        }

        auto now = std::chrono::system_clock::now();
        auto timestamp =
            std::chrono::duration_cast<std::chrono::milliseconds>(
                now.time_since_epoch()).count();

        std::cout
            << "{\"timestamp\":" << timestamp
            << ",\"detections\":[";

        for (std::size_t i = 0; i < detections.size(); ++i)
        {
            const auto &d = detections[i];

            if (i > 0)
                std::cout << ",";

            std::cout
                << "{"
                << "\"class\":\"" << d.name << "\","
                << "\"category\":" << d.category << ","
                << "\"confidence\":"
                << std::fixed << std::setprecision(6)
                << d.confidence << ","
                << "\"bbox\":{"
                << "\"x\":" << d.box.x << ","
                << "\"y\":" << d.box.y << ","
                << "\"width\":" << d.box.width << ","
                << "\"height\":" << d.box.height
                << "}"
                << "}";
        }

        std::cout << "]}" << std::endl;

        return false;
    }
};

static PostProcessingStage *CreateDetectionLogger(RPiCamApp *app)
{
    return new DetectionLogger(app);
}

static RegisterStage register_stage(
    "detection_logger",
    &CreateDetectionLogger
);
```

### Build

``` bash
g++ -std=c++17 -fPIC -shared \
  detection_logger.cpp \
  -o detection-logger-postproc.so \
  -I/usr/include/rpicam-apps \
  $(pkg-config --cflags --libs libcamera) \
  -lrpicam_app
```

Plugin 配置:

``` bash
sudo cp detection-logger-postproc.so \
  /usr/lib/aarch64-linux-gnu/rpicam-apps-postproc/
```

## 12. Post Processing 設定

標準設定をコピー:

``` bash
cp /usr/share/rpi-camera-assets/hailo_yolov8_inference.json \
   ~/detection-logger/hailo_yolov8_logger.json
```

処理順:

``` text
hailo_yolo_inference
        ↓
detection_logger
        ↓
object_detect_draw_cv
```

設定に以下を追加:

``` json
"detection_logger":
{
},

"object_detect_draw_cv":
{
    "line_thickness": 2
}
```

## 13. JSON Lines 出力 --- 動作確認済み

実行:

``` bash
rpicam-hello -t 10000 \
  --post-process-file ~/detection-logger/hailo_yolov8_logger.json \
  --nopreview
```

実際の出力例:

``` json
{"timestamp":1789762879207,"detections":[{"class":"person","category":1,"confidence":0.901203,"bbox":{"x":3,"y":2,"width":1242,"height":1044}},{"class":"clock","category":75,"confidence":0.435167,"bbox":{"x":940,"y":502,"width":235,"height":373}}]}
```

これにより以下が成立した。

``` text
Camera Module 3 Wide
        ↓
rpicam-apps
        ↓
Hailo-10H
        ↓
YOLOv8
        ↓
object_detect.results
        ↓
std::vector<Detection>
        ↓
自作 detection_logger
        ↓
JSON Lines
```

## 14. Robot Runtime の実装と実機確認

仕様は `docs/specs/phase-0.5-robot-runtime.md`。実装は `runtime/`、テストは `tests/runtime/`。Python 標準ライブラリのみで実装している。

### 14.1 実装

``` text
runtime/
├── models.py          データモデル
├── input.py           JSONL の読み込み (InputSource)
├── observation.py     DetectionEvent → Observation
├── reasoner.py        Observation → Decision (person の有無)
├── action.py          ActionPlanner / ConsoleExecutor
├── robot_logger.py    Robot Data Log (JSONL)
└── robot_runtime.py   Runtime 本体 / CLI
```

実行 (リポジトリルートで):

``` bash
rpicam-hello -t 10000 \
  --post-process-file edge/detection_logger/hailo_yolov8_logger.json \
  --nopreview | python3 -m runtime.robot_runtime
```

* Robot Data Log は既定で `logs/robot-data-<UTC日時>.jsonl` に保存する(`--log-path` で変更可、`logs/` は Git 管理外)
* Application Log は stderr、Action のコンソール出力は stdout

### 14.2 自動テスト

開発PC(Windows、Python 3.13)で `python -m unittest discover -s tests -t .` を実行し、25件がパスした。Raspberry Pi 上でのテスト実行は未確認。

### 14.3 実機確認 (Raspberry Pi 5、2026-09-21)

* **Observe → Reason → Action → Log:** 人をカメラに映し、`Person detected` のコンソール出力と RobotLoopRecord の保存を確認した。保存されたログ3ファイル(100 / 68 / 63行)は、最終行の `loop_id` が行数と一致し、`schema_version`、`loop_id`、`timestamp`、`observation`、`decision`、`action`、`result` の7キーを持つ
* **rpicam-apps の診断出力:** libcamera の INFO / WARN 等は stderr に出力され、パイプへ混入しない。Runtime の不正入力 WARN は大量発生しなかった
* **EOF での終了:** `rpicam-hello -t 10000` の終了後、`Robot Runtime stopped` が出力され正常終了した
* **Ctrl+C での終了:** `-t 0` で実行中に Ctrl+C を押すと、traceback なしで `Interrupted; stopping` → `Robot Runtime stopped` となった。`PIPESTATUS` は `130 0`(`rpicam-hello` が 130、Runtime が 0)。ログは38行で、最終行の `loop_id` も38

これにより、仕様書の AC-08(人を映して `PERSON_DETECTED` → Console Action → RobotLoopRecord)を満たした。

未確認:

* 処理中(入力待ち以外)に SIGINT が来た場合の実機での挙動(単体テストのみ)
* Robot Data 保存失敗(disk full 等)の実機での挙動

## 15. 検出0件の正規化 (ADR 0008)

### 15.1 問題

カメラを覆って検出0件の状態で 10 秒実行したところ、`detection_logger` から JSONL が1行も出力されなかった。Robot Data Log は 0 行、`NO_PERSON` は 0 件だった。既存の3つのログにも `NO_PERSON` は無かった。

`detection_logger` は `object_detect.results` を取得できないフレームでは何も出力せずに戻る。ADR 0008 のとおり、`hailo_yolo_inference` は Detection 0件のフレームで `object_detect.results` を設定しない場合がある。

### 15.2 対応

* ADR: `docs/decisions/0008-normalize-missing-detection-metadata-as-zero-detections.md`
* 仕様書: 「object_detect.results が存在しないフレーム」を追記
* `edge/detection_logger/detection_logger.cpp`: `object_detect.results` を取得できないとき、`detections` を空にして出力する
* `edge/detection_logger/build.sh` と `README.md`: Raspberry Pi 5 上での再ビルド・配置手順(`bash build.sh install`。既存の `.so` は `build/backup/` へ退避する)

Camera / Hailo / rpicam-apps の構成と `hailo_yolov8_logger.json` は変更していない。

### 15.3 実機確認 (Raspberry Pi 5、2026-09-21)

* `bash build.sh install` でビルドと配置に成功した
* カメラを覆った状態で、`{"timestamp":...,"detections":[]}` が約33ms間隔(約30fps)で出力された
* 人・椅子が映るフレームは、`class` / `category` / `confidence` / `bbox` の形式が従来のまま出力された
* Runtime に接続して `-t 10000` で実行し、`No person detected` の出力と、`NO_PERSON` 271件の記録を確認した
* 人の出入りに応じて、`Person detected` と `No person detected` が切り替わった

### 15.4 観測した挙動と制限

* 人が映り続けている間にも、1〜2フレームだけ `detections: []` になることがある。フレーム単位で判定する Reasoner は、その都度 `NO_PERSON` に切り替わる
* ADR 0008 のとおり、正常な Detection 0件と、推論失敗・結果取得失敗は区別できない。上の挙動は、その区別が実際に問題になり得ることを示している
* 連続するフレームで、confidence と bbox が完全に同一の検出結果が出力されることがある(原因は未確認)

Phase 0.5 では対応しない。判定の安定化(複数フレームでの判定)や推論状態の導入は、必要になった時点で別途検討する。

## 16. Phase 0.5 現在地

``` text
Observe
 ├─ Camera capture          ✓
 ├─ Hailo-10H inference     ✓
 ├─ YOLOv8 detection        ✓
 ├─ Bounding Box            ✓
 ├─ Detection metadata      ✓
 └─ JSON event              ✓

Reason
 └─ person の有無の判定     ✓  (PERSON_DETECTED / NO_PERSON)

Action
 └─ ConsoleExecutor         ✓

Log
 └─ RobotLoopRecord (JSONL) ✓
```

「AIが認識した映像を見る」段階から、「AIの認識結果をプログラムの入力として利用する」段階を経て、Observe → Reason → Action → Log の基本ループを実機で成立させる段階まで到達した。

## 17. Robot Runtime 着手時の構想 (第14章で実施済み)

> 注: 以下は Robot Runtime に着手する時点での構想の記録。実装と実機確認は第14章、検出0件の扱いは第15章に記録した。次の課題は第19章を参照。

次は Python の `robot_runtime.py` を作成する。

想定構成:

``` text
rpicam-apps / Hailo
       ↓
JSON Lines
       ↓
Robot Runtime
       ↓
Observation
       ↓
Reason
       ↓
Action
       ↓
Log
```

初期 Robot Runtime では、rpicam-apps
の出力からJSONとしてparse可能な行のみを `json.loads()`
で読み込み、最新のObservationとして保持する。

その後、例えば:

``` text
person detected
       ↓
位置・confidenceを評価
       ↓
Reason
       ↓
Action decision
       ↓
timestamp付きで記録
```

へ拡張する。

Phase 1でモーターやセンサーが追加された時も、Observation / Reason /
Action / Log の境界を維持する。

## 18. 将来的な全体像

``` text
Physical Robot
 ├─ Camera
 ├─ ToF
 ├─ IMU
 ├─ Encoder
 └─ Motors
       │
       ▼
Robot Runtime
 ├─ Observe
 ├─ Reason
 ├─ Action
 └─ Log
       │
       ▼
AI Agent / PC
 ├─ Log analysis
 ├─ RAG
 ├─ VLM / LLM
 ├─ Digital Twin
 └─ Policy generation
       │
       ▼
Learning Pipeline
 ├─ Behavior Cloning
 ├─ RL
 ├─ Domain Randomization
 └─ Sim2Real
       │
       └────────────→ Robot policy update
```

## 19. 次の課題

Phase 0.5 の基本ループは成立した。次に取り組む候補は以下(いずれも未着手)。

* Phase 0.8 (Stationary AI Robot) への拡張(第2章のロードマップ)
* 判定の安定化: 人が映っている間に単発で `NO_PERSON` へ切り替わる挙動への対応(複数フレームでの判定など)
* 正常な Detection 0件と、推論失敗・結果取得失敗の区別(推論状態を表すメタデータや `inference_status` の導入。ADR 0008 の将来課題)
* 第14章の「未確認」項目の実機確認

------------------------------------------------------------------------

## 現在の到達点

**Phase 0.5 の Observe → Reason → Action → Log の基本ループは、実機で動作確認済み。**

* Hailo-10H の YOLOv8 推論結果を、自作 rpicam-apps post-processing plugin (`detection_logger`) によって **1フレーム = 1 JSON event** として外部プログラムへ渡せる
* `detection_logger` は、検出結果メタデータが無いフレームも `detections: []` へ正規化する(ADR 0008)
* Python の Robot Runtime が JSONL を受け取り、`PERSON_DETECTED` / `NO_PERSON` を判定し、コンソールへ出力し、1 Loop = 1 RobotLoopRecord として保存する
* EOF と Ctrl+C のどちらでも、Robot Data Log を壊さず正常終了する

次の課題は第19章を参照。
