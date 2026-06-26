"""Tests for COROS Activity (session-level) sync: parsers, storage, service, FIT."""
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
