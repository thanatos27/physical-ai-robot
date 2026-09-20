# Physical AI Robot — Phase 0.5 Robot Runtime 実装仕様

## 1. 目的

Phase 0.5 Robot Runtime の目的は、既に実機動作確認済みの Camera / Hailo-10H / YOLOv8 パイプラインから得られる Detection Event を入力として、

```text
Observe → Reason → Action → Log
```

の Robot Runtime 基本ループを成立させることである。

Phase 0.5 では Reasoning 性能や物理的なロボット制御は目的としない。

今後の Phase で、

- Motor / Encoder / ToF / IMU
- VLM / LLM / AI Agent
- SLAM
- Digital Twin
- Behavior Cloning / RL
- Sim2Real

へ発展させられる責務境界を作ることを重視する。

---

## 2. 既存システム

以下は実機動作確認済みであり、原則として変更しない。

```text
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
detection_logger
        ↓
JSON Lines
```

`detection_logger` は rpicam-apps の自作 Post Processing Stage として実装済み。

出力例:

```json
{"timestamp":1789762879207,"detections":[{"class":"person","category":1,"confidence":0.901203,"bbox":{"x":3,"y":2,"width":1242,"height":1044}},{"class":"clock","category":75,"confidence":0.435167,"bbox":{"x":940,"y":502,"width":235,"height":373}}]}
```

Robot Runtime は、この JSON Lines を外部インターフェースとして利用する。

Hailo API や `object_detect.results` へ Robot Runtime から直接アクセスしない。

---

## 3. Phase 0.5 全体構成

```text
Camera
  ↓
Hailo-10H / YOLOv8
  ↓
detection_logger
  ↓
Detection JSONL
  │
  │ stdin/stdout pipe
  ▼
┌──────────────────────────────┐
│ Robot Runtime                │
│                              │
│ InputSource                  │
│      ↓                       │
│ DetectionEvent               │
│      ↓                       │
│ ObservationAdapter           │
│      ↓                       │
│ Observation                  │
│      ↓                       │
│ Reasoner                     │
│      ↓                       │
│ Decision                     │
│      ↓                       │
│ ActionPlanner                │
│      ↓                       │
│ Action                       │
│      ↓                       │
│ Executor                     │
│      ↓                       │
│ ActionResult                 │
│      ↓                       │
│ RobotLoopRecord              │
│      ↓                       │
│ RobotDataLogger              │
└──────────────────────────────┘
```

---

## 4. 設計原則

### 4.1 Runtime と Edge AI を疎結合にする

Robot Runtime は以下へ直接依存しない。

```text
Hailo-10H
YOLOv8
rpicam-apps 内部 API
object_detect.results
```

Runtime から見える境界は Detection Event のみとする。

### 4.2 外部入力と内部 Observation を分離する

```text
DetectionEvent
      ↓
ObservationAdapter
      ↓
Observation
```

DetectionEvent は外部インターフェース、Observation は Robot Runtime 内部の世界表現とする。

将来的には、

```text
Observation
├─ objects
├─ distances
├─ orientation
├─ odometry
└─ robot_state
```

などへ拡張可能とする。

### 4.3 Reason と Action を分離する

Reasoner は、

```text
Observation → Decision
```

のみを担当する。

Reasoner は Motor Driver 等のハードウェア事情を認識しない。

### 4.4 Decision と Action を分離する

```text
Decision
   ↓
ActionPlanner
   ↓
Action
```

Decision は「何をしたいか」、Action は「ロボットに何をさせるか」を表す。

### 4.5 Action と実行処理を分離する

```text
Action
   ↓
Executor
   ↓
ActionResult
```

Phase 0.5 では ConsoleExecutor のみを実装する。

将来は Motor、Display、Speaker 等の Executor へ拡張可能とする。

### 4.6 Phase 0.5 では同期・逐次処理とする

```text
Event N
 ↓
Observe
 ↓
Reason
 ↓
Action
 ↓
Log
 ↓
Event N+1
```

Phase 0.5 では async、multiprocessing、Event Bus、ROS 2 は導入しない。

---

## 5. プロセス構成

Camera / Hailo 処理と Robot Runtime は別プロセスとする。

```text
rpicam-apps process
       │
       │ JSONL
       ▼
Robot Runtime process
```

Phase 0.5 では stdin/stdout pipe で接続する。

```text
rpicam-apps | robot-runtime
```

Robot Runtime 自身は rpicam-apps を subprocess として起動しない。

プロセス接続は Shell 側の責務とする。

これにより保存済み JSONL から、

```text
JSONL fixture
      ↓
Robot Runtime
```

という Runtime 単体実行も可能とする。

stdin/stdout pipe は Phase 0.5 の接続方式であり、Runtime の恒久的な通信方式とはしない。

---

## 6. InputSource

外部入力は InputSource 境界を通す。

```text
External Input
      ↓
InputSource
      ↓
DetectionEvent
```

Phase 0.5:

```text
stdin / JSONL
      ↓
InputSource
```

将来的には必要に応じて Unix Socket、IPC、MQTT、Event Bus、ROS 2 Topic 等への交換余地を残す。

Phase 0.5 ではこれらを実装しない。

---

## 7. データモデル

### DetectionEvent

`detection_logger` から受信する外部モデル。

```text
DetectionEvent
├─ timestamp
└─ detections[]
    ├─ class
    ├─ category
    ├─ confidence
    └─ bbox
        ├─ x
        ├─ y
        ├─ width
        └─ height
```

既存の Detection JSON 仕様を変更しない。

### Observation

Robot Runtime 内部モデル。

```text
Observation
├─ timestamp
└─ objects[]
    ├─ type
    ├─ confidence
    └─ bounding_box
```

DetectionEvent と Observation を同一モデルにしない。

### Decision

Phase 0.5 では最低限、

```text
PERSON_DETECTED
NO_PERSON
```

を扱う。

### Action

ActionPlanner の出力。

Phase 0.5 では ConsoleExecutor で扱える論理 Action のみとする。

具体的な Action 名称は実装時に簡潔なものを定義してよい。

物理ハードウェアへの依存は持たせない。

### ActionResult

最低限、

```text
SUCCESS
FAILED
```

を表現可能とする。

Executor が正常に `FAILED` を返すケースと、Executor 内部で予期しない例外が発生するケースを区別する。

---

## 8. Reason 仕様

Phase 0.5 では単純な Rule-based Reasoner とする。

```text
Observation
      ↓
person が存在するか
      │
      ├─ YES → PERSON_DETECTED
      └─ NO  → NO_PERSON
```

Reasoning 性能の評価は Phase 0.5 の目的ではない。

---

## 9. Action 仕様

```text
Decision
   ↓
ActionPlanner
   ↓
Action
   ↓
ConsoleExecutor
```

ConsoleExecutor は短い人間可読テキストをコンソールへ出力する。

例:

```text
Person detected
```

```text
No person detected
```

Phase 0.5 の目的は Action 経路を実際に成立させることであり、Action 自体の高度化は行わない。

---

## 10. Logging

ログは2種類に分離する。

```text
Logging
├─ Application Log
└─ Robot Data Log
```

### Application Log

Runtime の運用・デバッグ用。

```text
INFO  Robot Runtime started
WARN  Invalid input skipped
ERROR Reasoner failed
INFO  Robot Runtime stopped
```

Python 標準 logging を利用してよい。

Robot Data とは分離する。

### Robot Data Log

1回の Runtime Loop を `RobotLoopRecord` として保存する。

```text
RobotLoopRecord
├─ schema_version
├─ loop_id
├─ timestamp
├─ observation
├─ decision
├─ action
└─ result
```

`loop_id` は Phase 0.5 では単調増加整数とする。

`timestamp` は Observation / DetectionEvent 由来の観測時刻を使用する。

`schema_version` を必ず持たせる。

初期バージョンは `0.1` とする。

---

## 11. Robot Data 保存方式

Phase 0.5 では JSON Lines を使用する。

```text
{RobotLoopRecord #1}
{RobotLoopRecord #2}
{RobotLoopRecord #3}
...
```

ただし Runtime 本体を JSONL ファイル保存へ直接依存させない。

```text
RobotRuntime
      ↓
RobotDataLogger
      ↓
JSONL writer
```

将来的には、

```text
RobotDataLogger
├─ JSONL
├─ SQLite
├─ PostgreSQL
├─ Time-series DB
└─ Cloud / Data Lake
```

等へ変更できる余地を残す。

Phase 0.5 では DB を実装しない。

---

## 12. Raw Data

Phase 0.5 では生の DetectionEvent を RobotLoopRecord へ重複保存しない。

```text
DetectionEvent
      ↓
Observation
      ↓
RobotLoopRecord
```

Camera 画像・動画・Raw Sensor Data の保存は、将来の Data Recorder / Dataset Recorder の責務として扱う。

---

## 13. モジュール構成

```text
runtime/
├── robot_runtime.py
├── models.py
├── input.py
├── observation.py
├── reasoner.py
├── action.py
└── robot_logger.py
```

### robot_runtime.py

Runtime 全体の Orchestrator。

```text
Input
 ↓
Observation
 ↓
Reason
 ↓
Action
 ↓
Execute
 ↓
Log
```

を順番に呼び出す。

個別の判断・変換ロジックは持たせない。

### models.py

主に以下の Runtime データモデルを定義する。

```text
DetectionEvent
Observation
Decision
Action
ActionResult
RobotLoopRecord
```

Phase 0.5 では Python 標準 `dataclass` 等で十分とする。

不要な外部依存を増やさない。

### input.py

InputSource および Detection JSONL の読み込みを担当する。

### observation.py

```text
DetectionEvent → Observation
```

の変換を担当する。

### reasoner.py

```text
Observation → Decision
```

を担当する。

### action.py

Phase 0.5 では、

```text
ActionPlanner
ConsoleExecutor
```

を配置する。

必要になった時点で planner / executor を分割する。

### robot_logger.py

Robot Data Log を担当する。

Python 標準 `logging` との名称衝突を避けるため `logging.py` とはしない。

---

## 14. テスト構成

```text
tests/
└── runtime/
    ├── test_input.py
    ├── test_observation.py
    ├── test_reasoner.py
    └── test_runtime.py
```

最低限以下を自動テストする。

```text
JSON → DetectionEvent

DetectionEvent → Observation

personあり → PERSON_DETECTED

personなし → NO_PERSON

fixture JSONL
      ↓
Runtime全体
```

Camera / Hailo なしでも Runtime の主要部分を検証可能とする。

---

## 15. Runtime Lifecycle

基本状態:

```text
STARTING
   ↓
RUNNING
   ↓
STOPPING
   ↓
STOPPED
```

状態管理機構を過剰に実装する必要はない。

Phase 0.5 では `PAUSED` や `RECOVERING` は不要。

---

## 16. 正常終了

stdin EOF:

```text
EOF
 ↓
Runtime Loop終了
 ↓
Logger flush / close
 ↓
正常終了
```

Ctrl+C / SIGINT:

```text
SIGINT
 ↓
安全にLoop終了
 ↓
Logger flush / close
 ↓
正常終了
```

---

## 17. エラー処理

### 不正入力

以下は Runtime 全体を停止させない。

- 空行
- JSONではない行
- 不正JSON
- 想定外Detection JSON

基本動作:

```text
Application Log: WARN
        ↓
入力eventをskip
        ↓
次eventを処理
```

Observation まで成立していないため RobotLoopRecord は作成しない。

実機確認時に rpicam-apps の通常診断出力によって WARN が大量発生する場合は、ログレベル等を再検討する。

### Detection 0件

エラーではない。

```text
Observation
  objects = []

Reason
  NO_PERSON

Action
  corresponding action

ActionResult
  SUCCESS

RobotLoopRecord
  保存
```

「何も検出されなかった」という Observation も Robot Data として扱う。

### Action失敗

Executor が期待される失敗として、

```text
ActionResult = FAILED
```

を返した場合は Runtime Loop 自体は成立したものとする。

FAILED を含む RobotLoopRecord を保存する。

### Runtime内部例外

ObservationAdapter、Reasoner、ActionPlanner、Executor、RobotDataLogger 等で発生した予期しない例外は隠蔽しない。

```text
Application Log
  ERROR + traceback
        ↓
Runtime停止
        ↓
non-zero exit
```

Phase 0.5 では自動リトライ・自己復旧は実装しない。

### Robot Data保存失敗

RobotDataLogger の保存失敗は Runtime 障害として扱う。

例:

- disk full
- permission error
- I/O error

Robot Data が保存されないまま正常動作を継続しない。

---

## 18. データフローとコード依存関係

### 18.1 データフロー

```text
InputSource
    ↓
DetectionEvent
    ↓
ObservationAdapter
    ↓
Observation
    ↓
Reasoner
    ↓
Decision
    ↓
ActionPlanner
    ↓
Action
    ↓
Executor
    ↓
ActionResult
    ↓
RobotLoopRecord
    ↓
RobotDataLogger
```

### 18.2 コード依存関係

```text
input              → models
observation        → models
reasoner           → models
action             → models
robot_logger       → models

robot_runtime      → input
robot_runtime      → observation
robot_runtime      → reasoner
robot_runtime      → action
robot_runtime      → robot_logger
robot_runtime      → models
```

`models` は Runtime 内部の共通データモデルを提供し、Reasoner や InputSource などの具体的な処理モジュールには依存しない。

`robot_runtime` は各コンポーネントを組み合わせて Runtime Loop を成立させる Orchestrator とする。

以下のような依存は避ける。

```text
models       → reasoner
models       → action
reasoner     → input
reasoner     → rpicam-apps / Hailo
action       → observation
robot_logger → reasoner
```

特に Reasoner から Hailo、YOLOv8、rpicam-apps 等の Edge AI 実装へ直接依存しない。

---

## 19. Acceptance Criteria

### AC-01 Input

`detection_logger` の JSONL を stdin から受信できる。

保存済み fixture JSONL でも同じ Runtime を実行できる。

### AC-02 Observation

DetectionEvent を Observation へ変換できる。

Detection 0件も正常 Observation として処理できる。

### AC-03 Reason

person の有無を判定できる。

```text
personあり → PERSON_DETECTED
personなし → NO_PERSON
```

### AC-04 Action

Decision から Action を生成し、ConsoleExecutor によって短いテキストを出力できる。

### AC-05 Log

正常に成立した各 Runtime Loop について、

```text
schema_version
loop_id
timestamp
observation
decision
action
result
```

を含む RobotLoopRecord を JSONL へ保存できる。

### AC-06 Error Handling

不正な外部入力では Runtime 全体を停止しない。

Runtime 内部の予期しない例外は隠蔽しない。

Robot Data 保存失敗は異常終了とする。

EOF / Ctrl+C では正常終了し、Logger を flush / close する。

### AC-07 Automated Tests

最低限、

```text
JSON → DetectionEvent
DetectionEvent → Observation
personあり → PERSON_DETECTED
personなし → NO_PERSON
fixture JSONL → Runtime全体
```

を自動テストできる。

Camera / Hailo なしでも Runtime の主要部分を検証可能とする。

### AC-08 Raspberry Pi E2E

Raspberry Pi 5 上で、

```text
Camera
 ↓
Hailo-10H
 ↓
YOLOv8
 ↓
detection_logger
 ↓
JSONL pipe
 ↓
Robot Runtime
 ↓
Reason
 ↓
Console Action
 ↓
Robot Data Log
```

を実行する。

実際にカメラへ人を映し、

```text
person detection
      ↓
PERSON_DETECTED
      ↓
Console Action
      ↓
RobotLoopRecord
```

まで確認する。

この確認をもって、

```text
Observe → Reason → Action → Log
```

の Phase 0.5 基本ループ成立とする。

---

## 20. Phase 0.5 スコープ外

以下は Phase 0.5 Robot Runtime では実装しない。

- Motor制御
- Encoder
- ToF
- IMU
- LiDAR / SLAM
- VLM / LLM Reasoning
- AI Agent
- ROS 2
- MQTT / WebSocket / Event Bus
- async runtime / multiprocessing
- Database
- Runtime自動復旧
- Camera画像 / 動画 Dataset 保存
- Behavior Cloning / RL
- Digital Twin
- Sim2Real

ただし、

```text
InputSource
Observation
Reasoner
ActionPlanner
Executor
RobotDataLogger
```

の境界を維持し、将来これらを追加できる余地を残す。

---

## 21. 実装方針

将来交換する理由が明確な箇所には境界を置く。ただし、将来使う可能性だけを理由として機能を先行実装しない。

既存の実機動作確認済み Camera / Hailo / detection_logger 構成を尊重し、Robot Runtime 実装のためだけに変更しない。

新しい外部ライブラリやフレームワークを導入する場合は、その必要性を明確にする。

Phase 0.5 では可能な限り Python 標準機能を利用する。

---

## 22. Phase 0.5 完成時の状態

```text
Physical World
      ↓
Camera Module 3 Wide
      ↓
Hailo-10H / YOLOv8
      ↓
DetectionEvent
      ↓
Observation
      ↓
Reason
      ↓
Decision
      ↓
Action
      ↓
ConsoleExecutor
      ↓
ActionResult
      ↓
RobotLoopRecord
      ↓
JSONL
```

これにより Physical AI Robot プロジェクトとして、

```text
Observe
   ↓
Reason
   ↓
Action
   ↓
Log
```

の完全な Runtime Loop を Raspberry Pi 実機上で成立させる。

Phase 1 以降はこの Runtime Loop の責務境界を維持しながら、Observation Source と Executor を物理ロボット向けに拡張する。
