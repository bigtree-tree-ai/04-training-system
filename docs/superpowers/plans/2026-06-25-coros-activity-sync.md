# COROS Activity 自动采集链路 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 自动从 COROS MCP 采集训练 session 全量明细（列表+详情+分段+FIT），入库 sessions/laps/track_points/gait，并全量回填历史。

**Architecture:** 新建 `ActivitySyncService` 4 步管线（querySportRecords → getActivityDetail → queryActivityLapData → downloadActivityFitFiles），复用现有 `parse_fit_file` / `upsert_track_points` / `upsert_gait` 与 `laps` 表，与 `sync.py`（汇总统计）分离。

**Tech Stack:** Python 3.14、COROS MCP（Streamable HTTP `https://mcpcn.coros.com/mcp`）、SQLite、pytest

## Global Constraints

- 联网脚本须 `SSL_CERT_FILE=/opt/homebrew/lib/python3.14/site-packages/certifi/cacert.pem`（会话环境被注入企业 CA，公网 TLS 验证会失败）。
- token 经 `training.coros.token_health.get_valid_token()` 获取；失效时优雅降级不崩。
- 复用 `CorosMcpClient`（不重写 HTTP 层）；`call_tool` 返回 `{"content":[{"type":"text","text":...}]}`，用 `extract_tool_text()` 取文本。
- 去重键：`sessions.filename = coros_<labelId>.fit`（UNIQUE 约束）。
- FIT 落盘 `config.COROS_FIT_DIR`（默认 `高驰的运动数据导出`），与 `reparse_fit_v2.find_fit` 对齐。
- 解析器遵循 `parsers.py` 现有模式：`parse_X(text) -> dict | list[dict]`。
- 提交规范：每个 task 末 `git commit`，message 带 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`。

## File Structure

- **Create** `training/coros/activity.py` — `ActivitySyncService`（4 步管线）
- **Create** `tests/test_coros_activity.py` — 全部测试
- **Modify** `training/coros/parsers.py` — 加 `parse_sport_records` / `parse_activity_detail` / `parse_activity_laps`
- **Modify** `training/coros/storage.py` — 加 `upsert_coros_sessions` / `upsert_laps` / `existing_coros_label_ids`
- **Modify** `training/cli.py` — 加 `activity-sync` 子命令
- **Reuse** `training/data_import/fit_parser.parse_fit_file`、`training/storage/writers.upsert_track_points/upsert_gait`

---

### Task 1: parse_sport_records 解析器

**Files:**
- Modify: `training/coros/parsers.py`（末尾追加）
- Test: `tests/test_coros_activity.py`（新建）

**Interfaces:**
- Produces: `parse_sport_records(text: str) -> list[dict]`，每条含 `label_id`(str)、`sport_type`(int)、`start_ts`(int)、`end_ts`(int)、`distance_km`(float)、`avg_pace_sec`(int)、`avg_hr`(int)、`duration_sec`(int)、`calories`(int)、`date`(str YYYY-MM-DD)、`sport`(str)、`location`(str)。

**真实样本（来自 2026-06-25 实测，作为测试固定数据）：**
```
Sport Records — 2026-06-18 to 2026-06-24 (4 records)

1. Indoor Run — 2026-06-24
   Location: (强度课)4Km有氧+2Km混氧+1.2*3组 间歇
   Time Window: startTimestamp=1782273830 | endTimestamp=1782277731
   Duration: 1:05:02 | Distance: 14.25 km
   Average Pace: 4:34 /km | Avg HR: 151 bpm | Calories: 584 kcal
   LabelId: 478426540852413118 | SportType: 101
```

- [ ] **Step 1: 写失败测试**

```python
# tests/test_coros_activity.py
from training.coros.parsers import parse_sport_records

SAMPLE = """Sport Records — 2026-06-18 to 2026-06-24 (4 records)

1. Indoor Run — 2026-06-24
   Location: (强度课)4Km有氧+2Km混氧+1.2*3组 间歇
   Time Window: startTimestamp=1782273830 | endTimestamp=1782277731
   Duration: 1:05:02 | Distance: 14.25 km
   Average Pace: 4:34 /km | Avg HR: 151 bpm | Calories: 584 kcal
   LabelId: 478426540852413118 | SportType: 101
"""

def test_parse_sport_records():
    rows = parse_sport_records(SAMPLE)
    assert len(rows) == 1
    r = rows[0]
    assert r["label_id"] == "478426540852413118"
    assert r["sport_type"] == 101
    assert r["sport"] == "Indoor Run"
    assert r["distance_km"] == 14.25
    assert r["avg_hr"] == 151
    assert r["calories"] == 584
    assert r["start_ts"] == 1782273830
    assert r["end_ts"] == 1782277731
    assert r["avg_pace_sec"] == 4 * 60 + 34  # 4:34 -> 274
    assert r["duration_sec"] == 1 * 3600 + 5 * 60 + 2  # 1:05:02 -> 3902
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd training-system && python3 -m pytest tests/test_coros_activity.py::test_parse_sport_records -v`
Expected: FAIL `ImportError: cannot import name 'parse_sport_records'`

- [ ] **Step 3: 实现**

```python
# training/coros/parsers.py 末尾追加
_SPORT_RECORD_RE = re.compile(
    r"\d+\.\s+(?P<sport>.+?)\s*—\s*(?P<date>\d{4}-\d{2}-\d{2})\s*\n"
    r"\s*Location:\s*(?P<location>.*?)\s*\n"
    r"\s*Time Window:\s*startTimestamp=(?P<start>\d+)\s*\|\s*endTimestamp=(?P<end>\d+)\s*\n"
    r"\s*Duration:\s*(?P<dur>[\d:]+)\s*\|\s*Distance:\s*(?P<dist>[\d.]+)\s*km\s*\n"
    r"\s*Average Pace:\s*(?P<pace>[\d:]+)\s*/km\s*\|\s*Avg HR:\s*(?P<hr>\d+)\s*bpm\s*\|\s*Calories:\s*(?P<cal>\d+)\s*kcal\s*\n"
    r"\s*LabelId:\s*(?P<label>\d+)\s*\|\s*SportType:\s*(?P<stype>\d+)",
    re.DOTALL,
)

def _hhmmss_to_sec(s: str) -> int:
    parts = [int(x) for x in s.split(":")]
    sec = 0
    for p in parts:
        sec = sec * 60 + p
    return sec

def parse_sport_records(text: str) -> list[dict]:
    rows = []
    for m in _SPORT_RECORD_RE.finditer(text):
        rows.append({
            "label_id": m.group("label"),
            "sport_type": int(m.group("stype")),
            "sport": m.group("sport").strip(),
            "date": m.group("date"),
            "location": m.group("location").strip(),
            "start_ts": int(m.group("start")),
            "end_ts": int(m.group("end")),
            "distance_km": float(m.group("dist")),
            "avg_pace_sec": _hhmmss_to_sec(m.group("pace")),
            "avg_hr": int(m.group("hr")),
            "calories": int(m.group("cal")),
            "duration_sec": _hhmmss_to_sec(m.group("dur")),
        })
    return rows
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/test_coros_activity.py::test_parse_sport_records -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add training/coros/parsers.py tests/test_coros_activity.py
git commit -m "feat(coros): parse_sport_records 解析训练记录列表" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: parse_activity_detail 解析器

**Files:** Modify `training/coros/parsers.py`；Test `tests/test_coros_activity.py`

**Interfaces:** Produces `parse_activity_detail(text: str) -> dict`，含 `distance_km`/`avg_hr`/`avg_pace_sec`/`avg_cadence`/`calories`/`training_load`/`aerobic_te`/`anaerobic_te`/`training_focus`/`perceived_effort`/`best_km_sec`。

**真实样本：**
```
🏃 Indoor Run Activity Details
========================================

Workout Time: 1:05:02
Distance: 14.25 km
Average Pace: 4:34 /km
Best Kilometer: 3:50 /km
Average Heart Rate: 151 bpm
Average Cadence: 193 spm
Average Stride Length: 1.14 m
Calories: 584 kcal
Training Load: 252
Aerobic TE: 3.4
Anaerobic TE: 4.2
Training Focus: Threshold
Perceived Effort: Somewhat Tired
```

- [ ] **Step 1: 写失败测试**

```python
# tests/test_coros_activity.py 追加
from training.coros.parsers import parse_activity_detail

DETAIL = """🏃 Indoor Run Activity Details
========================================

Workout Time: 1:05:02
Distance: 14.25 km
Average Pace: 4:34 /km
Best Kilometer: 3:50 /km
Average Heart Rate: 151 bpm
Average Cadence: 193 spm
Calories: 584 kcal
Training Load: 252
Aerobic TE: 3.4
Anaerobic TE: 4.2
Training Focus: Threshold
Perceived Effort: Somewhat Tired
"""

def test_parse_activity_detail():
    d = parse_activity_detail(DETAIL)
    assert d["distance_km"] == 14.25
    assert d["avg_hr"] == 151
    assert d["avg_cadence"] == 193
    assert d["calories"] == 584
    assert d["training_load"] == 252
    assert d["aerobic_te"] == 3.4
    assert d["anaerobic_te"] == 4.2
    assert d["training_focus"] == "Threshold"
    assert d["perceived_effort"] == "Somewhat Tired"
    assert d["best_km_sec"] == 3 * 60 + 50  # 3:50
    assert d["avg_pace_sec"] == 4 * 60 + 34
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_coros_activity.py::test_parse_activity_detail -v`
Expected: FAIL ImportError

- [ ] **Step 3: 实现**

```python
# training/coros/parsers.py 追加
def _field(text: str, label: str, pattern: str = r"([\d.]+)") -> str | None:
    m = re.search(rf"{re.escape(label)}:\s*{pattern}", text)
    return m.group(1) if m else None

def parse_activity_detail(text: str) -> dict:
    def pace(label):
        v = _field(text, label, r"(\d+:\d+(?::\d+)?)")
        return _hhmmss_to_sec(v) if v else None
    def num(label, cast=float):
        v = _field(text, label)
        return cast(v) if v else None
    return {
        "distance_km": num("Distance"),
        "avg_hr": num("Average Heart Rate", int),
        "avg_cadence": num("Average Cadence", int),
        "avg_stride_m": num("Average Stride Length"),
        "calories": num("Calories", int),
        "training_load": num("Training Load", int),
        "aerobic_te": num("Aerobic TE"),
        "anaerobic_te": num("Anaerobic TE"),
        "training_focus": _field(text, "Training Focus", r"(\D+?)\s*\n") or _field(text, "Training Focus", r"(\S+)"),
        "perceived_effort": _field(text, "Perceived Effort", r"(.+?)\s*\n"),
        "avg_pace_sec": pace("Average Pace"),
        "best_km_sec": pace("Best Kilometer"),
    }
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/test_coros_activity.py::test_parse_activity_detail -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add training/coros/parsers.py tests/test_coros_activity.py
git commit -m "feat(coros): parse_activity_detail 解析训练详情" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: parse_activity_laps 解析器（JSON）

**Files:** Modify `training/coros/parsers.py`；Test `tests/test_coros_activity.py`

**Interfaces:** Produces `parse_activity_laps(text: str) -> list[dict]`，每圈含 `lap_index`/`distance_km`/`avg_pace_sec`/`avg_hr`/`max_hr`/`avg_power`/`avg_cadence`/`ground_time`/`ground_balance`/`stride_height`。输入是 `queryActivityLapData` 的 content text（JSON 字符串）。

**注意：** 真实返回是 `{"columns":[{"name":...,"label":...}], "data":[[...]]}` 结构（columns 定义字段名，data 是行数组）。实现前若 data 行格式有疑，先实测确认；下列实现按「columns + data 行数组」处理。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_coros_activity.py 追加
import json
from training.coros.parsers import parse_activity_laps

LAPS_JSON = json.dumps({
    "source": "activityDetail",
    "labelId": "478426540852413118",
    "sportType": 101,
    "columns": [
        {"name": "lapIndex", "label": "圈数"},
        {"name": "distance", "label": "距离"},
        {"name": "avgPace", "label": "平均配速"},
        {"name": "avgHr", "label": "平均心率"},
        {"name": "maxHr", "label": "最大心率"},
        {"name": "avgPower", "label": "平均功率"},
        {"name": "avgCadence", "label": "平均步频"},
    ],
    "data": [
        [1, 1000, 240, 148, 162, 250, 190],
        [2, 1000, 235, 152, 164, 255, 192],
    ],
}, ensure_ascii=False)

def test_parse_activity_laps():
    laps = parse_activity_laps(LAPS_JSON)
    assert len(laps) == 2
    assert laps[0]["lap_index"] == 1
    assert laps[0]["distance_m"] == 1000
    assert laps[0]["avg_hr"] == 148
    assert laps[1]["avg_cadence"] == 192
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_coros_activity.py::test_parse_activity_laps -v`
Expected: FAIL ImportError

- [ ] **Step 3: 实现**

```python
# training/coros/parsers.py 追加
_LAP_KEY = {
    "lapIndex": "lap_index", "distance": "distance_m", "avgPace": "avg_pace_sec",
    "avgHr": "avg_hr", "maxHr": "max_hr", "avgPower": "avg_power",
    "avgCadence": "avg_cadence", "groundTime": "ground_time",
    "groundBalance": "ground_balance", "strideHeight": "stride_height",
    "avgStrideLength": "avg_stride_m",
}

def parse_activity_laps(text: str) -> list[dict]:
    obj = json.loads(extract_tool_text(text) if not text.strip().startswith("{") else text)
    cols = [c["name"] for c in obj.get("columns", [])]
    rows = []
    for raw in obj.get("data", []):
        rec = {}
        for name, val in zip(cols, raw):
            if name in _LAP_KEY:
                rec[_LAP_KEY[name]] = val
        rows.append(rec)
    return rows
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/test_coros_activity.py::test_parse_activity_laps -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add training/coros/parsers.py tests/test_coros_activity.py
git commit -m "feat(coros): parse_activity_laps 解析分段JSON" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: storage — upsert_coros_sessions / upsert_laps / 去重查询

**Files:** Modify `training/coros/storage.py`；Test `tests/test_coros_activity.py`

**Interfaces:**
- Produces:
  - `existing_coros_label_ids() -> set[str]`：查 `sessions.filename LIKE 'coros_%'` 提取已入库 labelId。
  - `upsert_coros_sessions(rows: list[dict]) -> int`：按 filename 唯一约束 upsert，返回写入数。
  - `upsert_laps(session_id: int, laps: list[dict]) -> int`：写入 laps（UNIQUE(session_id, lap_index)）。
- Consumes: `training/storage/db.get_conn`（参照 storage.py 现有 upsert_hrv 等的连接模式）。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_coros_activity.py 追加
import pathlib, tempfile
def _temp_db(monkeypatch, tmp_path):
    monkeypatch.setenv("TRAIN_DB_PATH", str(tmp_path / "t.db"))
    from training.storage.db import init_db
    init_db()

def test_upsert_coros_sessions_dedup(monkeypatch, tmp_path):
    _temp_db(monkeypatch, tmp_path)
    from training.coros.storage import upsert_coros_sessions, existing_coros_label_ids
    row = {"label_id": "111", "sport_type": 101, "sport": "Indoor Run",
           "start_time": "2026-06-24 13:00:00", "distance_km": 14.25,
           "avg_hr": 151, "avg_pace_sec": 274, "duration_sec": 3902,
           "calories": 584, "training_effect": 3.4, "anaerobic_te": 4.2}
    assert upsert_coros_sessions([row]) == 1
    assert "111" in existing_coros_label_ids()
    # 重复写不新增
    assert upsert_coros_sessions([row]) == 0
    assert len(existing_coros_label_ids()) == 1
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_coros_activity.py::test_upsert_coros_sessions_dedup -v`
Expected: FAIL ImportError

- [ ] **Step 3: 实现**（参照 `storage.py` 现有 `upsert_hrv` 的 get_conn/INSERT OR IGNORE 模式）

```python
# training/coros/storage.py 追加
from training.storage.db import get_conn

def existing_coros_label_ids() -> set[str]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT filename FROM sessions WHERE filename LIKE 'coros_%.fit'"
        ).fetchall()
    finally:
        conn.close()
    out = set()
    for r in rows:
        # coros_<labelId>.fit -> <labelId>
        out.add(r["filename"][len("coros_"):-len(".fit")])
    return out

def upsert_coros_sessions(rows: list[dict]) -> int:
    if not rows:
        return 0
    conn = get_conn()
    n = 0
    try:
        for r in rows:
            filename = f"coros_{r['label_id']}.fit"
            cur = conn.execute(
                """INSERT OR IGNORE INTO sessions
                   (filename, sport, start_time, duration_sec, distance_km,
                    total_calories, avg_hr, avg_pace_sec, training_effect, anaerobic_te)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (filename, r.get("sport"), r["start_time"], r.get("duration_sec"),
                 r.get("distance_km"), r.get("calories"), r.get("avg_hr"),
                 r.get("avg_pace_sec"), r.get("training_effect"), r.get("anaerobic_te")),
            )
            n += cur.rowcount
        conn.commit()
    finally:
        conn.close()
    return n

def upsert_laps(session_id: int, laps: list[dict]) -> int:
    if not laps:
        return 0
    conn = get_conn()
    n = 0
    try:
        for lap in laps:
            cur = conn.execute(
                """INSERT OR IGNORE INTO laps
                   (session_id, lap_index, distance_km, avg_hr, max_hr, avg_pace_sec, avg_cadence)
                   VALUES (?,?,?,?,?,?,?)""",
                (session_id, lap.get("lap_index"),
                 (lap.get("distance_m") or 0) / 1000.0, lap.get("avg_hr"),
                 lap.get("max_hr"), lap.get("avg_pace_sec"), lap.get("avg_cadence")),
            )
            n += cur.rowcount
        conn.commit()
    finally:
        conn.close()
    return n
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/test_coros_activity.py::test_upsert_coros_sessions_dedup -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add training/coros/storage.py tests/test_coros_activity.py
git commit -m "feat(coros): upsert_coros_sessions/laps + labelId 去重查询" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: ActivitySyncService — 4 步管线 + 去重 + 增量

**Files:** Create `training/coros/activity.py`；Test `tests/test_coros_activity.py`

**Interfaces:**
- Produces: `class ActivitySyncService(client=None, timezone="Asia/Shanghai")`；`sync(days=7, full=False) -> dict` 返回 `{"success": bool, "persisted": {"sessions": n, "laps": n}, "failed": [labelId...], "fetched": n}`。
- Consumes: `CorosMcpClient`、`get_valid_token`、`parse_sport_records/parse_activity_detail/parse_activity_laps`、`existing_coros_label_ids/upsert_coros_sessions/upsert_laps`、`extract_tool_text`。
- 测试用 FakeClient（参照 `test_coros_sync.py`）mock `call_tool`。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_coros_activity.py 追加
def test_activity_sync_persists(monkeypatch, tmp_path):
    _temp_db(monkeypatch, tmp_path)
    from training.coros.activity import ActivitySyncService
    from training.coros.storage import existing_coros_label_ids

    SAMPLE_RECORDS = """1. Indoor Run — 2026-06-24
   Location: x
   Time Window: startTimestamp=1782273830 | endTimestamp=1782277731
   Duration: 1:05:02 | Distance: 14.25 km
   Average Pace: 4:34 /km | Avg HR: 151 bpm | Calories: 584 kcal
   LabelId: 478426540852413118 | SportType: 101
"""
    DETAIL = ("Distance: 14.25 km\nAverage Heart Rate: 151 bpm\nAverage Cadence: 193 spm\n"
              "Calories: 584 kcal\nAerobic TE: 3.4\nAnaerobic TE: 4.2\nTraining Focus: Threshold\n")
    LAPS = '{"columns":[{"name":"lapIndex"},{"name":"distance"},{"name":"avgHr"}],"data":[[1,1000,150]]}'

    class FakeClient:
        def call_tool(self, name, arguments=None):
            return {"content": [{"type": "text", "text": {
                "querySportRecords": SAMPLE_RECORDS,
                "getActivityDetail": DETAIL,
                "queryActivityLapData": LAPS,
            }[name]}], "isError": False}

    res = ActivitySyncService(FakeClient()).sync(days=7)
    assert res["success"] is True
    assert res["persisted"]["sessions"] == 1
    assert "478426540852413118" in existing_coros_label_ids()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m pytest tests/test_coros_activity.py::test_activity_sync_persists -v`
Expected: FAIL `ModuleNotFoundError: training.coros.activity`

- [ ] **Step 3: 实现**

```python
# training/coros/activity.py
"""COROS Activity (session-level) sync: records + detail + laps + FIT."""
from __future__ import annotations

from datetime import date, timedelta, timezone

from training.coros.client import CorosMcpClient
from training.coros.parsers import (
    extract_tool_text, parse_sport_records, parse_activity_detail, parse_activity_laps,
)
from training.coros import storage


class ActivitySyncService:
    def __init__(self, client=None, timezone: str = "Asia/Shanghai"):
        self.client = client
        self.timezone = timezone

    def _ensure_client(self):
        if self.client is None:
            from training.coros.token_health import get_valid_token
            token, status = get_valid_token()
            if token is None:
                return None, status
            self.client = CorosMcpClient(access_token=token)
        return self.client, None

    def sync(self, days: int = 7, full: bool = False) -> dict:
        client, token_status = self._ensure_client()
        if client is None:
            return {"success": False, "token_status": token_status,
                    "persisted": {"sessions": 0, "laps": 0}, "fetched": 0, "failed": []}

        today = date.today()
        start = (today - timedelta(days=365 * 2)) if full else (today - timedelta(days=days - 1))
        sd, ed = start.strftime("%Y%m%d"), today.strftime("%Y%m%d")

        records = parse_sport_records(extract_tool_text(
            client.call_tool("querySportRecords",
                             {"startDate": sd, "endDate": ed, "sportTypeCodes": [65535],
                              "limit": 500, "timezone": self.timezone})))
        existing = storage.existing_coros_label_ids()
        new_records = [r for r in records if r["label_id"] not in existing]

        session_rows, failed = [], []
        lap_total = 0
        for r in new_records:
            label_id, stype = r["label_id"], r["sport_type"]
            try:
                detail = parse_activity_detail(extract_tool_text(
                    client.call_tool("getActivityDetail", {"labelId": label_id, "sportType": stype})))
                laps = parse_activity_laps(extract_tool_text(
                    client.call_tool("queryActivityLapData", {"labelId": label_id, "sportType": stype})))
            except Exception:
                failed.append(label_id)
                continue
            session_rows.append({
                "label_id": label_id, "sport_type": stype, "sport": r["sport"],
                "start_time": _ts_to_local(r["start_ts"]),
                "distance_km": detail.get("distance_km") or r["distance_km"],
                "avg_hr": detail.get("avg_hr") or r["avg_hr"],
                "avg_pace_sec": detail.get("avg_pace_sec") or r["avg_pace_sec"],
                "duration_sec": r["duration_sec"], "calories": detail.get("calories") or r["calories"],
                "training_effect": detail.get("aerobic_te"), "anaerobic_te": detail.get("anaerobic_te"),
            })
            # laps 需 session_id，先 upsert session 再回填（见下）
            lap_total += len(laps)
            r["_laps"] = laps  # 暂存，session 入库后回填

        n_session = storage.upsert_coros_sessions(session_rows)
        # 回填 laps：查刚写入的 session_id
        _backfill_laps(session_rows)

        return {"success": True,
                "persisted": {"sessions": n_session, "laps": lap_total},
                "fetched": len(records), "failed": failed}


def _ts_to_local(ts: int) -> str:
    from datetime import datetime
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _backfill_laps(session_rows: list[dict]):
    from training.storage.db import get_conn
    conn = get_conn()
    try:
        for r in session_rows:
            row = conn.execute(
                "SELECT id FROM sessions WHERE filename=?", (f"coros_{r['label_id']}.fit",)
            ).fetchone()
            if row:
                storage.upsert_laps(row["id"], r.get("_laps", []))
    finally:
        conn.close()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m pytest tests/test_coros_activity.py::test_activity_sync_persists -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add training/coros/activity.py tests/test_coros_activity.py
git commit -m "feat(coros): ActivitySyncService 4步管线+去重增量" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: FIT 下载 + parse_fit_file 衔接

**Files:** Modify `training/coros/activity.py`；Test `tests/test_coros_activity.py`

**先实测确认格式（手动一步）：**
```bash
SSL_CERT_FILE=/opt/homebrew/lib/python3.14/site-packages/certifi/cacert.pem python3 -c "
from training.coros.token_health import get_valid_token
from training.coros.client import CorosMcpClient
import json
c = CorosMcpClient(access_token=get_valid_token()[0]); c.initialize()
r = c.call_tool('queryActivityFitFileDownloadUrls', {'startDate':'20260624','endDate':'20260624','sportType':101,'limit':1})
print(json.dumps(r, ensure_ascii=False)[:800])
"
```
- 若返回下载 URL 列表 → 用 `urllib.request` + `SSL_CERT_FILE` 下载到 `config.COROS_FIT_DIR/coros_<labelId>.fit`。
- 若 `downloadActivityFitFiles` 直接返回 base64 二进制 content → 解码落盘。
- **选可行的那种**，写入 `activity.py` 的 `_download_fit(label_id, ...)`。

- [ ] **Step 1: 写失败测试**（mock 下载 + 验证 parse_fit_file 被调用并写 track_points）

```python
# tests/test_coros_activity.py 追加
def test_fit_download_and_parse(monkeypatch, tmp_path):
    _temp_db(monkeypatch, tmp_path)
    monkeypatch.setenv("TRAIN_FIT_DIR", str(tmp_path / "fit"))
    (tmp_path / "fit").mkdir()
    from training.coros import activity

    called = {}
    def fake_download(self, label_id, **kw):
        p = tmp_path / "fit" / f"coros_{label_id}.fit"
        p.write_bytes(b"FAKEFIT")
        return p
    def fake_parse(fpath):
        called["parsed"] = fpath
        return {"session": {"has_track_points": 1, "has_gait": 1},
                "track_points": [{"hr": 100}], "gait": {"sample_count": 1}}
    monkeypatch.setattr(activity.ActivitySyncService, "_download_fit", fake_download)
    monkeypatch.setattr("training.coros.activity.parse_fit_file", fake_parse)

    svc = activity.ActivitySyncService(client=object())
    sid = svc._ingest_fit("123")  # 先 upsert 一条 session 再测，或此函数内部处理
    assert called["parsed"].name == "coros_123.fit"
```

- [ ] **Step 2: 跑测试确认失败** → Expected FAIL（方法未实现）

- [ ] **Step 3: 实现** `_download_fit` + `_ingest_fit`

```python
# training/coros/activity.py 顶部 import 补充
import urllib.request, ssl
from training import config
from training.data_import.fit_parser import parse_fit_file
from training.storage.writers import upsert_track_points, upsert_gait
from training.storage.db import get_conn

    # ActivitySyncService 方法
    def _download_fit(self, label_id: str, start: str, end: str, sport_type: int):
        """下载单个活动的 FIT 到 COROS_FIT_DIR。实现依 Task6 实测格式二选一。"""
        config.COROS_FIT_DIR.mkdir(parents=True, exist_ok=True)
        dest = config.COROS_FIT_DIR / f"coros_{label_id}.fit"
        if dest.exists():
            return dest
        # 方案A（URL）：
        r = self.client.call_tool("queryActivityFitFileDownloadUrls",
                                  {"labelId": label_id, "sportType": sport_type})
        url = _extract_first_url(r)  # 解析返回里的下载 URL
        ctx = ssl.create_default_context(cafile=__import__("certifi").where())
        with urllib.request.urlopen(url, timeout=60, context=ctx) as resp, open(dest, "wb") as f:
            f.write(resp.read())
        return dest

    def _ingest_fit(self, label_id: str):
        conn = get_conn()
        try:
            row = conn.execute("SELECT id FROM sessions WHERE filename=?",
                               (f"coros_{label_id}.fit",)).fetchone()
            if not row:
                return None
            sid = row["id"]
        finally:
            conn.close()
        result = parse_fit_file(str(config.COROS_FIT_DIR / f"coros_{label_id}.fit"))
        if not result:
            return sid
        upsert_track_points(sid, result.get("track_points", []))
        upsert_gait(sid, result.get("gait") or {})
        return sid
```
> `_extract_first_url(r)` 按 Task6 实测的 URL 字段实现（正则 https URL 或 JSON path）。

- [ ] **Step 4: 跑测试确认通过** → Expected PASS

- [ ] **Step 5: 提交**

```bash
git add training/coros/activity.py tests/test_coros_activity.py
git commit -m "feat(coros): FIT 下载 + parse_fit_file 衔接 track_points/gait" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: CLI activity-sync 子命令

**Files:** Modify `training/cli.py`；Test 手动跑

**Interfaces:** `python -m training.cli activity-sync [days] [--full]`

- [ ] **Step 1: 实现**（参照 cli.py 现有 `coros-sync` 分支模式，约 line 120）

```python
# training/cli.py 的命令分发里加
    elif cmd == 'activity-sync':
        from training.coros.activity import ActivitySyncService
        full = '--full' in sys.argv
        days = 7
        for a in sys.argv[2:]:
            if a.isdigit():
                days = int(a)
        result = ActivitySyncService().sync(days=days, full=full)
        print("COROS Activity 同步完成")
        for k, v in (result.get("persisted") or {}).items():
            print(f"  {k}: {v}")
        if result.get("failed"):
            print(f"  failed_labelIds: {len(result['failed'])}")
```
并在 `usage` 帮助文本（line ~22）加：`print("  activity-sync [days] [--full]  从COROS采集训练session明细(FIT)")`

- [ ] **Step 2: 增量实测**

Run: `SSL_CERT_FILE=/opt/homebrew/lib/python3.14/site-packages/certifi/cacert.pem python3 -m training.cli activity-sync 7`
Expected: 打印 `sessions: N`（近 7 天新训练入库）

- [ ] **Step 3: 验证入库**

Run: `python3 -c "from training.storage.queries import get_all_sessions; [print(s['start_time'], s['distance_km'], s['avg_hr']) for s in get_all_sessions(limit=5)]"`
Expected: 出现 2026-06 的训练记录（不再停在 4 月）

- [ ] **Step 4: 提交**

```bash
git add training/cli.py
git commit -m "feat(cli): activity-sync 子命令(增量/--full全量)" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: 全量回填实测 + cron 接入

**Files:** 部署脚本/launchd plist（服务器 cron 已有 coros-sync，追加 activity-sync）

- [ ] **Step 1: 实测 COROS 历史范围**

Run: `SSL_CERT_FILE=... python3 -c "..."` 调 `querySportRecords({'startDate':'20230101','endDate':'20260625','sportTypeCodes':[65535],'limit':500})`，看返回记录数与最早日期 → 确定真实可回填范围。若 limit 截断，分页拉。

- [ ] **Step 2: 全量回填**

Run: `SSL_CERT_FILE=... python3 -m training.cli activity-sync --full`
Expected: 历史训练批量入库（首次较慢，含 FIT 下载）

- [ ] **Step 3: 接入 cron**（服务器 03:33 调度，coros-sync 后追加）

服务器上编辑现有 coros 调度脚本，在 `coros-sync` 后加一行 `activity-sync 2`（增量近 2 天）。或本地 launchd 同步追加。

- [ ] **Step 4: 全量测试回归**

Run: `python3 -m pytest --tb=short -q`
Expected: 全部通过（原 177 + 新增 activity 测试）

- [ ] **Step 5: 提交调度配置**

```bash
git add <调度脚本/plist>
git commit -m "chore(coros): activity-sync 接入 03:33 调度 + 全量回填" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 9: 服务器部署 + FIT rsync 同步

**前提：** 服务器 `git pull` 受 GitHub 连接超时阻碍（已验证 `Failed to connect github.com:443`）。代码部署待服务器网络恢复或换镜像/Codeup。

- [ ] **Step 1: FIT 文件 rsync 同步**（FIT 不入 git，单独同步）

Run: `sshpass -p '...' rsync -avz --include='coros_*.fit' --exclude='*' <本地COROS_FIT_DIR>/ root@101.37.238.138:/opt/training-system/高驰的运动数据导出/`

- [ ] **Step 2: 代码部署**（待 GitHub 连通后）

Run: 标准 `git push origin main` + SSH `cd /opt/training-system && git pull && systemctl restart training-web`。若持续不通，改用阿里云 Codeup 镜像或 rsync 代码目录。

- [ ] **Step 3: 服务器健康检查**

Run: `curl -s -o /dev/null -w "%{http_code}" http://localhost:8082/`（服务器内部）+ 公网 `https://bigtree.ink/training/`
Expected: 200

- [ ] **Step 4: 服务器跑一次 activity-sync --full 验证**

确认服务器端 sessions 表也回填了历史训练。

---

## Self-Review

**1. Spec 覆盖：** 4 步管线（Task 5）✓；数据映射（Task 1-4 解析+存储）✓；去重/增量/全量回填（Task 4/5/8）✓；FIT 存储（Task 6）✓；调度（Task 8）✓；模块组织 activity.py（Task 5）✓；错误处理 failed_labelIds（Task 5）✓；测试策略（每 Task TDD）✓。

**2. Placeholder 扫描：** Task 6 的 `_extract_first_url` 依赖实测格式——已显式标注「先实测二选一」并提供两套方案，非空洞 TODO。其余步骤含完整代码。

**3. 类型一致性：** `label_id` 全程 str；`sport_type` int；`parse_*` 返回字段名（`avg_pace_sec`/`distance_km`/`aerobic_te`）在解析器、storage、service 间一致。`existing_coros_label_ids`/`upsert_coros_sessions`/`upsert_laps` 签名 Task4 定义、Task5 消费一致。
