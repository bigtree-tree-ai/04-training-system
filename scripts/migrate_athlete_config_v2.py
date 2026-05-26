"""athlete_config.json v1 → v2 迁移（幂等）

v2 新增：
- _schema_version: 2
- injuries[]: 从 injury_history / current_injury 文本反推
- zones: 按 Karvonen 法回退
- vdot, weekly_volume_target_km, sweat_rate_ml_per_h, gi_tolerance_cho_g_per_h, ...

用法：
  python -m scripts.migrate_athlete_config_v2            # 直接写
  python -m scripts.migrate_athlete_config_v2 --dry-run  # 仅打印结果
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training.config import ATHLETE_CONFIG_PATH


def _zones_from_hr(max_hr: int, rhr: int) -> dict:
    hrr = max(max_hr - rhr, 1)
    return {
        "z1_max": int(rhr + 0.60 * hrr),
        "z2_max": int(rhr + 0.70 * hrr),
        "z3_max": int(rhr + 0.80 * hrr),
        "z4_max": int(rhr + 0.90 * hrr),
        "z5_max": max_hr,
        "lt_hr": int(rhr + 0.88 * hrr),
        "cv_pace_sec": None,
    }


# 简单中文 / 英文部位映射
_SITE_PATTERNS = [
    (re.compile(r"左膝|left\s*knee"), "L_knee"),
    (re.compile(r"右膝|right\s*knee"), "R_knee"),
    (re.compile(r"膝(?!关节)?|knee"), "L_knee"),
    (re.compile(r"踝|ankle"), "ankle"),
    (re.compile(r"髋|hip"), "hip"),
    (re.compile(r"跟腱|achilles"), "achilles"),
    (re.compile(r"itb|髂胫"), "ITB"),
    (re.compile(r"足底|plantar"), "plantar_fascia"),
    (re.compile(r"后背|腰|low.*back"), "lower_back"),
]


def _infer_site(text: str) -> str:
    if not text:
        return "unknown"
    s = text.lower()
    for pat, site in _SITE_PATTERNS:
        if pat.search(s):
            return site
    return "unknown"


def _infer_injuries(history: str, current: str) -> list[dict]:
    out: list[dict] = []
    # 从 history 找术后伤病
    if history:
        onset = re.search(r"(\d{4}-\d{2}-\d{2})", history)
        surgery = re.search(r"(\d{4}-\d{2}-\d{2})手术", history) or re.search(r"手术[修复]?[:：]?\s*(\d{4}-\d{2}-\d{2})", history)
        # 退化匹配：取出现在"手术"后面的第二个日期
        all_dates = re.findall(r"\d{4}-\d{2}-\d{2}", history)
        surgery_date = None
        if "手术" in history and len(all_dates) >= 2:
            surgery_date = all_dates[1]
        elif surgery:
            surgery_date = surgery.group(1)

        if onset and "断裂" in history or "韧带" in history:
            out.append({
                "site": _infer_site(history),
                "grade": "III post-op" if surgery_date else "III",
                "onset": onset.group(1) if onset else None,
                "surgery_date": surgery_date,
                "current_stage": 4,
                "capacity_pct": 80.0,
                "last_pain_vas": 1.0,
                "note": history,
            })

    # 当前症状（轻微痛）
    if current:
        # 拆分按全角逗号 / 顿号 / 分号
        parts = re.split(r"[，,；;、]", current)
        for p in parts:
            p = p.strip()
            if not p:
                continue
            site = _infer_site(p)
            if site == "unknown":
                continue
            # 避免与 history 重复
            if any(i["site"] == site for i in out):
                continue
            vas = 2.0 if any(k in p for k in ["微痛", "酸"]) else (3.0 if "痛" in p else 1.0)
            out.append({
                "site": site,
                "grade": "I",
                "onset": None,
                "surgery_date": None,
                "current_stage": 5,
                "capacity_pct": 90.0,
                "last_pain_vas": vas,
                "note": p,
            })
    return out


def migrate(path: Path, dry_run: bool = False) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if int(raw.get("_schema_version", 1)) >= 2:
        print("[skip] 已是 v2", flush=True)
        return raw

    out = dict(raw)
    out["_schema_version"] = 2

    max_hr = int(raw.get("max_heart_rate", 173))
    rhr = int(raw.get("resting_heart_rate", 56))
    out.setdefault("zones", _zones_from_hr(max_hr, rhr))
    out.setdefault("vdot", None)
    out.setdefault("weekly_volume_target_km", None)
    out.setdefault("body_fat_pct", 12.0)
    out.setdefault("ffm_kg", round(float(raw.get("weight_kg", 65)) * 0.88, 2))
    out.setdefault("pal", 1.55)
    out.setdefault("sweat_rate_ml_per_h", 800.0)
    out.setdefault("sweat_na_mg_per_l", 1000.0)
    out.setdefault("gi_tolerance_cho_g_per_h", 60)
    out.setdefault("caffeine_response", "ok")
    out.setdefault("reds_history", False)
    out.setdefault("injuries", _infer_injuries(raw.get("injury_history", ""), raw.get("current_injury", "")))

    if dry_run:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[done] 已升级 {path}")
    return out


def main():
    dry = "--dry-run" in sys.argv
    migrate(Path(ATHLETE_CONFIG_PATH), dry_run=dry)


if __name__ == "__main__":
    main()
