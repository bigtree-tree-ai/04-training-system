"""运动员档案统一入口 — 兼容 v1（旧 athlete_config.json）和 v2（结构化）

v2 新增字段：
- _schema_version: 2
- injuries[]: 结构化伤病数组
- zones: {z1..z5, lt_hr, cv_pace_sec}
- vdot: float
- weekly_volume_target_km
- sweat_rate_ml_per_h
- gi_tolerance: {cho_g_per_h_max}
- caffeine_response: ok/sensitive
- reds_history: bool
- ffm_kg, body_fat_pct, pal

v1 字段（保留兼容）：name/height_cm/weight_kg/max_heart_rate/resting_heart_rate/
  lactate_threshold_hr/half_marathon_pb/injury_history/current_injury/
  target_race/race_date/target_pace
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

from training.config import ATHLETE_CONFIG_PATH


@dataclass
class Injury:
    site: str                        # L_knee / R_knee / lower_back / achilles / ITB / plantar_fascia
    grade: str = "I"                 # I / II / III / III post-op
    onset: Optional[str] = None      # YYYY-MM-DD
    surgery_date: Optional[str] = None
    current_stage: int = 5           # 0-5 返跑阶段
    capacity_pct: Optional[float] = 100.0
    last_pain_vas: Optional[float] = 0.0
    note: str = ""


@dataclass
class HRZones:
    z1_max: int = 0
    z2_max: int = 0
    z3_max: int = 0
    z4_max: int = 0
    z5_max: int = 0
    lt_hr: int = 0
    cv_pace_sec: Optional[float] = None  # 每公里秒数


@dataclass
class AthleteProfile:
    name: str = ""
    schema_version: int = 1
    height_cm: float = 0.0
    weight_kg: float = 0.0
    body_fat_pct: Optional[float] = None
    ffm_kg: Optional[float] = None
    pal: float = 1.55                 # 物理活动水平默认 light-active
    max_heart_rate: int = 0
    resting_heart_rate: int = 0
    lactate_threshold_hr: int = 0
    zones: HRZones = field(default_factory=HRZones)
    vdot: Optional[float] = None
    half_marathon_pb: str = ""
    weekly_volume_target_km: Optional[float] = None
    sweat_rate_ml_per_h: float = 800.0
    sweat_na_mg_per_l: float = 1000.0
    gi_tolerance_cho_g_per_h: int = 60
    caffeine_response: str = "ok"
    reds_history: bool = False
    injuries: list[Injury] = field(default_factory=list)
    injury_history_text: str = ""
    current_injury_text: str = ""
    target_race: str = ""
    race_date: Optional[str] = None
    target_pace: str = ""

    @property
    def hr_reserve(self) -> int:
        return max(self.max_heart_rate - self.resting_heart_rate, 1)

    @property
    def has_active_injury(self) -> bool:
        return any(i.last_pain_vas and i.last_pain_vas > 0 for i in self.injuries)

    @property
    def days_since_surgery(self) -> Optional[int]:
        for i in self.injuries:
            if i.surgery_date:
                try:
                    d = date.fromisoformat(i.surgery_date)
                    return (date.today() - d).days
                except ValueError:
                    continue
        return None


def _ffm(weight_kg: float, body_fat_pct: Optional[float]) -> Optional[float]:
    if not weight_kg:
        return None
    bf = body_fat_pct if body_fat_pct is not None else 12.0  # 男性精英耐力跑者经验值
    return round(weight_kg * (1 - bf / 100), 2)


def _zones_from_hr(max_hr: int, rhr: int) -> HRZones:
    """Karvonen 法回退：当 v1 没有结构化 zones 时按公式生成"""
    hrr = max(max_hr - rhr, 1)
    return HRZones(
        z1_max=int(rhr + 0.60 * hrr),
        z2_max=int(rhr + 0.70 * hrr),
        z3_max=int(rhr + 0.80 * hrr),
        z4_max=int(rhr + 0.90 * hrr),
        z5_max=max_hr,
        lt_hr=int(rhr + 0.88 * hrr),
    )


def load_athlete_profile(path: Optional[Path] = None) -> AthleteProfile:
    """读取 athlete_config.json，自动适配 v1 / v2"""
    p = Path(path) if path else ATHLETE_CONFIG_PATH
    if not p.exists():
        return AthleteProfile()
    raw = json.loads(p.read_text(encoding="utf-8"))

    schema_version = int(raw.get("_schema_version", 1))

    weight = float(raw.get("weight_kg", 0) or 0)
    body_fat = raw.get("body_fat_pct")
    ffm = raw.get("ffm_kg") or _ffm(weight, body_fat)

    max_hr = int(raw.get("max_heart_rate", 0) or 0)
    rhr = int(raw.get("resting_heart_rate", 0) or 0)
    lt_hr = int(raw.get("lactate_threshold_hr", 0) or 0)

    if schema_version >= 2 and isinstance(raw.get("zones"), dict):
        z = raw["zones"]
        zones = HRZones(
            z1_max=int(z.get("z1_max", 0)),
            z2_max=int(z.get("z2_max", 0)),
            z3_max=int(z.get("z3_max", 0)),
            z4_max=int(z.get("z4_max", 0)),
            z5_max=int(z.get("z5_max", max_hr)),
            lt_hr=int(z.get("lt_hr", lt_hr)),
            cv_pace_sec=z.get("cv_pace_sec"),
        )
    else:
        zones = _zones_from_hr(max_hr, rhr)

    injuries: list[Injury] = []
    for item in raw.get("injuries", []) or []:
        injuries.append(Injury(
            site=str(item.get("site", "unknown")),
            grade=str(item.get("grade", "I")),
            onset=item.get("onset"),
            surgery_date=item.get("surgery_date"),
            current_stage=int(item.get("current_stage", 5)),
            capacity_pct=item.get("capacity_pct"),
            last_pain_vas=item.get("last_pain_vas"),
            note=item.get("note", ""),
        ))

    return AthleteProfile(
        name=raw.get("name", ""),
        schema_version=schema_version,
        height_cm=float(raw.get("height_cm", 0) or 0),
        weight_kg=weight,
        body_fat_pct=body_fat,
        ffm_kg=ffm,
        pal=float(raw.get("pal", 1.55)),
        max_heart_rate=max_hr,
        resting_heart_rate=rhr,
        lactate_threshold_hr=lt_hr or zones.lt_hr,
        zones=zones,
        vdot=raw.get("vdot"),
        half_marathon_pb=raw.get("half_marathon_pb", ""),
        weekly_volume_target_km=raw.get("weekly_volume_target_km"),
        sweat_rate_ml_per_h=float(raw.get("sweat_rate_ml_per_h", 800)),
        sweat_na_mg_per_l=float(raw.get("sweat_na_mg_per_l", 1000)),
        gi_tolerance_cho_g_per_h=int(raw.get("gi_tolerance_cho_g_per_h", 60)),
        caffeine_response=raw.get("caffeine_response", "ok"),
        reds_history=bool(raw.get("reds_history", False)),
        injuries=injuries,
        injury_history_text=raw.get("injury_history", ""),
        current_injury_text=raw.get("current_injury", ""),
        target_race=raw.get("target_race", ""),
        race_date=raw.get("race_date"),
        target_pace=raw.get("target_pace", ""),
    )
