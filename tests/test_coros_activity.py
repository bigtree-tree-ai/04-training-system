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
            {"name": "lapIndex"},
            {"name": "distance"},
            {"name": "avgPace"},
            {"name": "avgHr"},
            {"name": "maxHr"},
            {"name": "avgCadence"},
        ],
        "lapGroups": [
            {
                "type": 10,
                "laps": [
                    {
                        "lapIndex": 1,
                        "distance": 86355,
                        "avgPace": 347.4,
                        "avgHr": 114,
                        "maxHr": 124,
                        "avgCadence": 186,
                    },
                    {
                        "lapIndex": 2,
                        "distance": 94497,
                        "avgPace": 317.28,
                        "avgHr": 121,
                        "maxHr": 130,
                        "avgCadence": 189,
                    },
                ],
            }
        ],
    },
    ensure_ascii=False,
)


def test_parse_activity_laps():
    laps = parse_activity_laps(LAPS_JSON)
    assert len(laps) == 2
    assert laps[0]["lap_index"] == 1
    assert laps[0]["distance_m"] == 863.55  # 86355 cm -> 863.55 m
    assert laps[0]["avg_hr"] == 114
    assert laps[1]["avg_cadence"] == 189


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


def test_activity_sync_persists(monkeypatch, tmp_path):
    _temp_db(monkeypatch, tmp_path)
    from training.coros.activity import ActivitySyncService
    from training.coros.storage import existing_coros_label_ids
    from training.storage.db import get_conn

    sample_records = (
        "1. Indoor Run — 2026-06-24\n"
        "   Location: x\n"
        "   Time Window: startTimestamp=1782273830 | endTimestamp=1782277731\n"
        "   Duration: 1:05:02 | Distance: 14.25 km\n"
        "   Average Pace: 4:34 /km | Avg HR: 151 bpm | Calories: 584 kcal\n"
        "   LabelId: 478426540852413118 | SportType: 101\n"
    )
    detail = (
        "Distance: 14.25 km\nAverage Heart Rate: 151 bpm\nAverage Cadence: 193 spm\n"
        "Calories: 584 kcal\nAerobic TE: 3.4\nAnaerobic TE: 4.2\nTraining Focus: Threshold\n"
    )
    laps = '{"columns":[{"name":"lapIndex"},{"name":"distance"},{"name":"avgHr"}],"lapGroups":[{"type":10,"laps":[{"lapIndex":1,"distance":100000,"avgHr":150}]}]}'

    class FakeClient:
        def call_tool(self, name, arguments=None):
            return {
                "content": [{"type": "text", "text": {
                    "querySportRecords": sample_records,
                    "getActivityDetail": detail,
                    "queryActivityLapData": laps,
                }[name]}],
                "isError": False,
            }

    res = ActivitySyncService(FakeClient()).sync(days=7)
    assert res["success"] is True
    assert res["persisted"]["sessions"] == 1
    assert res["persisted"]["laps"] == 1
    assert "478426540852413118" in existing_coros_label_ids()

    # laps must be written into the laps table (guards against the backfill bug)
    conn = get_conn()
    n_laps = conn.execute("SELECT COUNT(*) c FROM laps").fetchone()["c"]
    conn.close()
    assert n_laps == 1


def test_extract_fit_url():
    from training.coros.activity import _extract_fit_url

    text = (
        "Activity FIT file download URL(s):\n"
        "1. 478426540852413118.fit\n"
        "   https://oss.coros.com/fit/472868445151576164/478426540852413118.fit"
    )
    assert (
        _extract_fit_url(text)
        == "https://oss.coros.com/fit/472868445151576164/478426540852413118.fit"
    )
    assert _extract_fit_url("no url here") is None


def test_fit_ingest_parses_and_writes_track_points(monkeypatch, tmp_path):
    from pathlib import Path

    _temp_db(monkeypatch, tmp_path)
    fit_dir = tmp_path / "fit"
    fit_dir.mkdir()
    monkeypatch.setattr("training.config.COROS_FIT_DIR", fit_dir)

    from training.coros import activity
    from training.coros.storage import upsert_coros_sessions
    from training.storage.db import get_conn

    upsert_coros_sessions(
        [
            {
                "label_id": "123",
                "start_time": "2026-01-01 00:00:00",
                "sport": "Run",
                "distance_km": 5.0,
            }
        ]
    )
    (fit_dir / "coros_123.fit").write_bytes(b"FAKEFIT")

    called = {}

    def fake_parse(fpath):
        called["parsed"] = Path(fpath)
        return {
            "session": {"has_track_points": 1, "has_gait": 1},
            "track_points": [
                {
                    "t_offset_s": 0,
                    "lat": 30.0,
                    "lon": 120.0,
                    "altitude_m": 50.0,
                    "hr": 100,
                    "speed_mps": 3.0,
                    "cadence": 180,
                    "distance_m": 0,
                }
            ],
            "gait": {"sample_count": 1},
        }

    monkeypatch.setattr("training.coros.activity.parse_fit_file", fake_parse)

    svc = activity.ActivitySyncService(client=object())
    sid = svc._ingest_fit("123")
    assert sid is not None
    assert called["parsed"].name == "coros_123.fit"

    conn = get_conn()
    n_tp = conn.execute(
        "SELECT COUNT(*) c FROM session_track_points WHERE session_id=?", (sid,)
    ).fetchone()["c"]
    n_gait = conn.execute(
        "SELECT COUNT(*) c FROM session_gait WHERE session_id=?", (sid,)
    ).fetchone()["c"]
    conn.close()
    assert n_tp == 1
    assert n_gait == 1


def test_existing_label_ids_handles_bare_and_prefixed(monkeypatch, tmp_path):
    _temp_db(monkeypatch, tmp_path)
    from training.coros.storage import existing_coros_label_ids
    from training.storage.db import get_conn

    conn = get_conn()
    # mix: legacy bare labelId, new prefixed, and manual-named FITs (must be excluded)
    for fn in [
        "476612698851803136.fit",
        "coros_478426540852413118.fit",
        "(日常)有氧跑8-12km20260407071518.fit",
        "杭州市跑步20260406084447.fit",
    ]:
        conn.execute(
            "INSERT INTO sessions (filename, start_time) VALUES (?, '2026-01-01')", (fn,)
        )
    conn.commit()
    conn.close()

    ids = existing_coros_label_ids()
    assert "476612698851803136" in ids  # legacy bare filename
    assert "478426540852413118" in ids  # new prefixed
    assert len(ids) == 2  # manual-named FITs excluded
