"""Tests for COROS Activity (session-level) sync: parsers, storage, service, FIT."""
import json

from training.coros.parsers import (
    parse_activity_detail,
    parse_activity_laps,
    parse_sport_records,
)

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


DETAIL = """🏃 Indoor Run Activity Details
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


LAPS_JSON = json.dumps(
    {
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
    },
    ensure_ascii=False,
)


def test_parse_activity_laps():
    laps = parse_activity_laps(LAPS_JSON)
    assert len(laps) == 2
    assert laps[0]["lap_index"] == 1
    assert laps[0]["distance_m"] == 1000
    assert laps[0]["avg_hr"] == 148
    assert laps[1]["avg_cadence"] == 192


def _temp_db(monkeypatch, tmp_path):
    from training.storage import db

    test_db = tmp_path / "t.db"
    monkeypatch.setattr(db, "DB_PATH", test_db)
    db.init_db(str(test_db))


def test_upsert_coros_sessions_dedup(monkeypatch, tmp_path):
    _temp_db(monkeypatch, tmp_path)
    from training.coros.storage import existing_coros_label_ids, upsert_coros_sessions

    row = {
        "label_id": "111",
        "sport_type": 101,
        "sport": "Indoor Run",
        "start_time": "2026-06-24 13:00:00",
        "distance_km": 14.25,
        "avg_hr": 151,
        "avg_pace_sec": 274,
        "duration_sec": 3902,
        "calories": 584,
        "training_effect": 3.4,
        "anaerobic_te": 4.2,
    }
    assert upsert_coros_sessions([row]) == 1
    assert "111" in existing_coros_label_ids()
    assert upsert_coros_sessions([row]) == 0
    assert len(existing_coros_label_ids()) == 1
