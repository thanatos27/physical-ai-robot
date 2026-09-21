# detection_logger

rpicam-apps の自作 Post Processing Stage。Hailo YOLOv8 の検出結果を、1フレーム = 1 JSON の JSON Lines として標準出力へ出力し、Robot Runtime への入力にする。

```text
hailo_yolo_inference → detection_logger → object_detect_draw_cv
                            ↓
                      JSONL (stdout)
```

設計判断は以下を参照。

* `docs/decisions/0001-use-rpicam-postprocessing-plugin.md`
* `docs/decisions/0008-normalize-missing-detection-metadata-as-zero-detections.md`

## 出力仕様

```json
{"timestamp":1789762879207,"detections":[{"class":"person","category":1,"confidence":0.901203,"bbox":{"x":3,"y":2,"width":1242,"height":1044}}]}
```

`object_detect.results` を取得できないフレーム(Detection 0件のフレームを含む)も、空の Detection Event として出力する(ADR 0008)。

```json
{"timestamp":1789762879240,"detections":[]}
```

`detections: []` は、正常な推論結果が0件であることを保証しない。推論失敗や結果取得失敗も、Phase 0.5 では同じ出力に正規化される。

## ファイル

| ファイル | 内容 |
| --- | --- |
| `detection_logger.cpp` | Post Processing Stage のソース |
| `hailo_yolov8_logger.json` | rpicam-apps 用の post-process 設定(`hailo_yolo_inference` → `detection_logger` → `object_detect_draw_cv`) |
| `build.sh` | Raspberry Pi 5 上でのビルド・インストールスクリプト |

`build/`、`*.so`、`*.log` は Git 管理外。

## ビルド (Raspberry Pi 5)

### 前提

Raspberry Pi 5(Debian 13 / aarch64)に、以下の開発パッケージが必要。

```bash
sudo apt install librpicam-app-dev libcamera-dev libboost-dev
```

Camera / Hailo / rpicam-apps の既存環境は変更しない。

### ビルドのみ(システムは変更しない)

```bash
cd edge/detection_logger
bash build.sh
```

`build/detection-logger-postproc.so` が生成される。

`build.sh` は、`docs/progress/phase-0.5-progress.md` に記録されている実機確認済みのコマンドと同じ内容を実行する。

```bash
g++ -std=c++17 -fPIC -shared \
  detection_logger.cpp \
  -o build/detection-logger-postproc.so \
  -I/usr/include/rpicam-apps \
  $(pkg-config --cflags --libs libcamera) \
  -lrpicam_app
```

### ビルドして配置する

```bash
cd edge/detection_logger
bash build.sh install
```

配置先は `/usr/lib/aarch64-linux-gnu/rpicam-apps-postproc/` で、`sudo` を使う。配置前に、既存の `.so` を `build/backup/detection-logger-postproc.so.<日時>` へ退避する。

### ロールバック

```bash
sudo cp edge/detection_logger/build/backup/detection-logger-postproc.so.<日時> \
  /usr/lib/aarch64-linux-gnu/rpicam-apps-postproc/detection-logger-postproc.so
```

## 動作確認 (Raspberry Pi 5)

リポジトリルートで実行する。

### 1. Detection 0件でも JSONL が出力されること

カメラを覆うか、人をフレームから外した状態で実行する。

```bash
rpicam-hello -t 5000 \
  --post-process-file edge/detection_logger/hailo_yolov8_logger.json \
  --nopreview
```

`{"timestamp":...,"detections":[]}` の行が、フレームごとに出力されること。

### 2. 人が映っているときの出力が変わらないこと

人をカメラに映して同じコマンドを実行し、従来どおり `class` / `category` / `confidence` / `bbox` を持つ行が出力されること。

### 3. Robot Runtime で NO_PERSON になること

```bash
rpicam-hello -t 10000 \
  --post-process-file edge/detection_logger/hailo_yolov8_logger.json \
  --nopreview | python3 -m runtime.robot_runtime --log-path logs/check-no-person.jsonl

grep -c NO_PERSON logs/check-no-person.jsonl
```

カメラを覆った状態で `No person detected` が出力され、`grep` が1以上を返すこと。

## 確認状況

ADR 0008 に対応した `detection_logger` は、Raspberry Pi 5 上で再ビルド(`bash build.sh install`)し、2026-09-21 に以下を実機で確認した。

* Detection 0件のフレームで、`{"timestamp":...,"detections":[]}` が出力される
* 人・椅子が映るフレームの出力形式は、従来から変わらない
* Robot Runtime に接続すると、`No person detected` が出力され、`NO_PERSON` が記録される

詳細は `docs/progress/phase-0.5-progress.md` の第15章を参照。
