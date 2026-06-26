"""Parsers for COROS MCP text responses."""
from __future__ import annotations

import json
import re
from typing import Any


def clean_text(text: Any) -> str:
    if text is None:
        return ""
    if not isinstance(text, str):
        return str(text)
    value = text.strip()
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = value[1:-1]
    return value.replace("\\n", "\n").strip()


def extract_tool_text(result: Any) -> str:
    if isinstance(result, str):
        return clean_text(result)
    if isinstance(result, dict):
        content = result.get("content")
        if isinstance(content, list):
            return "\n".join(
                clean_text(item.get("text", ""))
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            ).strip()
        if "text" in result:
            return clean_text(result["text"])
    return clean_text(result)


def parse_date(value: str) -> str:
    text = value.strip()
    if re.fullmatch(r"\d{8}", text):
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return text


def parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    cleaned = value.replace(",", "").strip()
    if cleaned == "":
        return None
    return int(float(cleaned))


def parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    cleaned = value.replace(",", "").strip()
    if cleaned == "":
        return None
    return float(cleaned)


def parse_duration_min(value: str | None) -> float | None:
    if not value:
        return None
    text = value.strip()
    hm = re.search(r"(?:(\d+)\s*h)?\s*(?:(\d+)\s*min)?", text, re.I)
    if hm and (hm.group(1) or hm.group(2)):
        return float((int(hm.group(1) or 0) * 60) + int(hm.group(2) or 0))
    parts = [int(p) for p in text.split(":") if p.isdigit()]
    if len(parts) == 3:
        return parts[0] * 60 + parts[1] + parts[2] / 60
    if len(parts) == 2:
        return parts[0] + parts[1] / 60
    return None


def parse_time_to_sec(value: str | None) -> int | None:
    if not value:
        return None
    parts = [int(p) for p in value.strip().split(":") if p.isdigit()]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return None


def parse_recovery(text: str) -> dict:
    body = clean_text(text)
    return {
        "recovery_pct": parse_int(_match(body, r"Recovery:\s*([\d.]+)%")),
        "level": _match(body, r"Level:\s*(.+)"),
        "estimated_full_recovery_hours": parse_duration_min(
            _match(body, r"Estimated Full Recovery:\s*(.+)")
        ) / 60
        if _match(body, r"Estimated Full Recovery:\s*(.+)")
        else None,
    }


def parse_fitness(text: str) -> dict:
    body = clean_text(text)
    return {
        "vo2max": parse_float(_match(body, r"VO2max:\s*([\d.]+)")),
        "running_level": parse_float(_match(body, r"Running Level:\s*([\d.]+)")),
        "threshold_pace_sec": parse_time_to_sec(_match(body, r"Threshold Pace:\s*([0-9:]+)")),
        "five_k_prediction_sec": parse_time_to_sec(_match(body, r"^5 km Prediction:\s*([0-9:]+)")),
        "ten_k_prediction_sec": parse_time_to_sec(_match(body, r"^10 km Prediction:\s*([0-9:]+)")),
        "half_marathon_prediction_sec": parse_time_to_sec(
            _match(body, r"^Half Marathon Prediction:\s*([0-9:]+)")
        ),
        "marathon_prediction_sec": parse_time_to_sec(_match(body, r"^Marathon Prediction:\s*([0-9:]+)")),
    }


def parse_training_load(text: str) -> list[dict]:
    body = clean_text(text)
    rows = []
    for date, block in _date_blocks(body):
        rows.append(
            {
                "date": date,
                "comment": _match(block, r"Comment:\s*(.+)"),
                "short_term_load": parse_float(_match(block, r"Short-Term Load:\s*([\d.]+)")),
                "long_term_load": parse_float(_match(block, r"Long-Term Load:\s*([\d.]+)")),
                "load_ratio": parse_float(_match(block, r"Load Ratio:\s*([\d.]+)")),
            }
        )
    return rows


def parse_sleep(text: str) -> list[dict]:
    body = clean_text(text)
    rows = []
    for date, block in _date_blocks(body):
        rows.append(
            {
                "date": date,
                "sleep_score": parse_int(_match(block, r"Sleep Score:\s*(\d+)")),
                "main_sleep_min": _duration_int(_match(block, r"Main Sleep:\s*(.+)")),
                "deep_sleep_pct": parse_int(_match(block, r"Deep Sleep Ratio:\s*(\d+)%")),
                "light_sleep_pct": parse_int(_match(block, r"Light Sleep Ratio:\s*(\d+)%")),
                "rem_pct": parse_int(_match(block, r"REM Ratio:\s*(\d+)%")),
                "awake_pct": parse_int(_match(block, r"Awake Ratio:\s*(\d+)%")),
                "awake_min": _duration_int(_match(block, r"Awake Time:\s*(.+)")),
                "awake_count": parse_int(_match(block, r"Awake Count \(>5 min\):\s*(\d+)")),
                "sleep_window": _match(block, r"Main Sleep Window:\s*(.+)"),
                "naps_total_min": _duration_int(_match(block, r"Naps Total:\s*(.+)")),
            }
        )
    return rows


def parse_daily_health(text: str) -> list[dict]:
    body = clean_text(text)
    rows = []
    sections = list(re.finditer(r"---\s*(\d{8}|\d{4}-\d{2}-\d{2})\s*---", body))
    for index, marker in enumerate(sections):
        start = marker.end()
        end = sections[index + 1].start() if index + 1 < len(sections) else len(body)
        block = body[start:end]
        rows.append(
            {
                "date": parse_date(marker.group(1)),
                "steps": parse_int(_match(block, r"Steps:\s*([\d,]+)")),
                "calories_kcal": parse_int(_match(block, r"Calories:\s*([\d,]+)\s*kcal")),
                "exercise_min": _duration_int(_match(block, r"Exercise:\s*([^\n|]+)")),
                "stress_avg": parse_int(_match(block, r"Stress:\s*Avg\s*(\d+)")),
                "sleep_score": parse_int(_match(block, r"Sleep Summary:\s*\(Score:\s*(\d+)\)")),
                "sleep_total_min": _duration_int(_match(block, r"Total:\s*([^|]+)")),
                "sleep_awake_min": _duration_int(_match(block, r"Awake:\s*([^\n|]+)")),
                "sleep_deep_min": _duration_int(_match(block, r"Deep:\s*([^|]+)")),
                "sleep_light_min": _duration_int(_match(block, r"Light:\s*([^|]+)")),
                "sleep_rem_min": _duration_int(_match(block, r"REM:\s*([^\n|]+)")),
            }
        )
    return rows


def parse_hrv(text: str) -> list[dict]:
    body = clean_text(text)
    low = parse_int(_match(body, r"Normal Range:\s*(\d+)\s*-\s*\d+\s*ms"))
    high = parse_int(_match(body, r"Normal Range:\s*\d+\s*-\s*(\d+)\s*ms"))
    baseline = parse_int(_match(body, r"Baseline:\s*(\d+)\s*ms"))
    rows = []
    for match in re.finditer(
        r"(\d{4}-\d{2}-\d{2}):\s*\n\s*HRV Avg:\s*(\d+)\s*ms\s*[—-]\s*([^\n]+)",
        body,
    ):
        rows.append(
            {
                "date": match.group(1),
                "hrv_avg_ms": parse_int(match.group(2)),
                "evaluation": match.group(3).strip(),
                "normal_low_ms": low,
                "normal_high_ms": high,
                "baseline_ms": baseline,
            }
        )
    return rows


def parse_resting_heart_rate(text: str) -> list[dict]:
    return [
        {"date": date, "resting_hr": parse_int(hr)}
        for date, hr in re.findall(r"(\d{4}-\d{2}-\d{2}):\s*(\d+)\s*bpm", clean_text(text))
    ]


def parse_avg_heart_rate(text: str) -> list[dict]:
    rows = []
    for date, avg, min_hr, max_hr in re.findall(
        r"(\d{4}-\d{2}-\d{2}):\s*(\d+)\s*bpm\s*\(Min:\s*(\d+),\s*Max:\s*(\d+)\)",
        clean_text(text),
    ):
        rows.append(
            {
                "date": date,
                "avg_hr": parse_int(avg),
                "min_hr": parse_int(min_hr),
                "max_hr": parse_int(max_hr),
            }
        )
    return rows


def parse_stress(text: str) -> list[dict]:
    rows = []
    body = clean_text(text)
    for date, block in _date_blocks(body, allow_colon=True):
        rows.append(
            {
                "date": date,
                "stress_avg": parse_int(_match(block, r"Average Stress:\s*(\d+)")),
                "level": _match(block, r"Average Stress:\s*\d+\s*\(([^)]+)\)"),
            }
        )
    return rows


def parse_training_schedule(text: str) -> list[dict]:
    rows = []
    for date, block in _date_blocks(clean_text(text)):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        title = lines[0] if lines else None
        rows.append(
            {
                "date": date,
                "title": title,
                "distance_km": parse_float(_match(block, r"Distance:\s*([\d.]+)\s*km")),
                "estimated_time_min": parse_duration_min(_match(block, r"Estimated Time:\s*([0-9:]+)")),
                "load_tl": parse_float(_match(block, r"Load:\s*([\d.]+)\s*TL")),
            }
        )
    return rows


def parse_devices(text: str) -> list[dict]:
    body = clean_text(text)
    markers = list(re.finditer(r"^\s*(\d+)\.\s+(.+)$", body, re.M))
    rows = []
    for index, marker in enumerate(markers):
        start = marker.end()
        end = markers[index + 1].start() if index + 1 < len(markers) else len(body)
        block = body[start:end]
        rows.append(
            {
                "name": marker.group(2).strip(),
                "bluetooth_id": _match(block, r"Bluetooth ID:\s*(.+)"),
                "model_name": _match(block, r"Model Name:\s*(.+)"),
                "serial_number": _match(block, r"Serial Number:\s*(.+)"),
                "warranty_expires": _match(block, r"Warranty Expires:\s*(.+)"),
            }
        )
    return rows


def parse_user_info(text: str) -> dict:
    body = clean_text(text)
    return {
        "height_cm": parse_float(_match(body, r"Height:\s*([\d.]+)\s*cm")),
        "weight_kg": parse_float(_match(body, r"Weight:\s*([\d.]+)\s*kg")),
        "birthday": _match(body, r"Birthday:\s*([0-9-]+)"),
        "age": parse_int(_match(body, r"Age:\s*(\d+)")),
        "gender": _match(body, r"Gender:\s*(.+)"),
        "nickname": _match(body, r"Nickname:\s*(.+)"),
    }


def _match(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, re.M)
    return match.group(1).strip() if match else None


def _duration_int(value: str | None) -> int | None:
    minutes = parse_duration_min(value)
    return int(round(minutes)) if minutes is not None else None


def _date_blocks(body: str, allow_colon: bool = False) -> list[tuple[str, str]]:
    suffix = r":?\s*" if allow_colon else r"\s*"
    markers = list(re.finditer(rf"^(\d{{4}}-\d{{2}}-\d{{2}}|\d{{8}}){suffix}$", body, re.M))
    blocks = []
    for index, marker in enumerate(markers):
        start = marker.end()
        end = markers[index + 1].start() if index + 1 < len(markers) else len(body)
        blocks.append((parse_date(marker.group(1)), body[start:end].strip()))
    return blocks


# --- Activity (session-level) parsers ---------------------------------------

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
    """'4:34' -> 274 ; '1:05:02' -> 3902."""
    sec = 0
    for part in s.split(":"):
        sec = sec * 60 + int(part)
    return sec


def parse_sport_records(text: str) -> list[dict]:
    """Parse querySportRecords text into a list of record dicts."""
    rows = []
    for m in _SPORT_RECORD_RE.finditer(clean_text(text)):
        rows.append(
            {
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
            }
        )
    return rows


def parse_activity_detail(text: str) -> dict:
    """Parse getActivityDetail text into a dict of high-level metrics."""
    body = clean_text(text)

    def num(label: str, cast=float):
        v = _match(body, rf"{re.escape(label)}:\s*([\d.]+)")
        return cast(v) if v else None

    def pace(label: str):
        v = _match(body, rf"{re.escape(label)}:\s*(\d+:\d+(?::\d+)?)")
        return _hhmmss_to_sec(v) if v else None

    return {
        "distance_km": num("Distance"),
        "avg_hr": num("Average Heart Rate", int),
        "avg_cadence": num("Average Cadence", int),
        "avg_stride_m": num("Average Stride Length"),
        "calories": num("Calories", int),
        "training_load": num("Training Load", int),
        "aerobic_te": num("Aerobic TE"),
        "anaerobic_te": num("Anaerobic TE"),
        "training_focus": _match(body, r"Training Focus:\s*(\D+?)\s*\n")
        or _match(body, r"Training Focus:\s*(\S+)"),
        "perceived_effort": _match(body, r"Perceived Effort:\s*(.+)"),
        "avg_pace_sec": pace("Average Pace"),
        "best_km_sec": pace("Best Kilometer"),
    }


_LAP_KEY = {
    "lapIndex": "lap_index",
    "distance": "distance_m",
    "avgPace": "avg_pace_sec",
    "avgHr": "avg_hr",
    "maxHr": "max_hr",
    "avgPower": "avg_power",
    "avgCadence": "avg_cadence",
    "groundTime": "ground_time",
    "groundBalance": "ground_balance",
    "strideHeight": "stride_height",
    "avgStrideLength": "avg_stride_m",
}


def parse_activity_laps(text: str) -> list[dict]:
    """Parse queryActivityLapData JSON ({columns:[{name}], data:[[...]]}) into lap dicts."""
    body = clean_text(text)
    if not body.startswith("{"):
        body = extract_tool_text(text)
    obj = json.loads(body)
    cols = [c.get("name") for c in obj.get("columns", [])]
    rows = []
    for raw in obj.get("data", []):
        rec = {}
        for name, val in zip(cols, raw):
            if name in _LAP_KEY:
                rec[_LAP_KEY[name]] = val
        rows.append(rec)
    return rows
