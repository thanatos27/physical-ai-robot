# Physical AI Robot Project --- Phase 0.5 開発進捗

更新日: 2026-09-19

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

現在のJSON Lines版:

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

## 14. Phase 0.5 現在地

``` text
Observe
 ├─ Camera capture          ✓
 ├─ Hailo-10H inference     ✓
 ├─ YOLOv8 detection        ✓
 ├─ Bounding Box            ✓
 ├─ Detection metadata      ✓
 └─ JSON event              ✓

Reason                       ← NEXT
Action
Log
```

「AIが認識した映像を見る」段階から、「AIの認識結果をプログラムの入力として利用する」段階まで到達した。

## 15. 次のステップ

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

## 16. 将来的な全体像

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

------------------------------------------------------------------------

## 現在の到達点

**Phase 0.5 の Observe パイプラインは実機で動作確認済み。**

特に重要な成果は、Hailo-10HのYOLOv8推論結果を `object_detect.results`
から取得し、自作 rpicam-apps post-processing plugin によって **1フレーム
= 1 JSON event** として外部プログラムへ渡せる状態にしたこと。

次の開発対象は **Robot Runtime / Reason 層**。
