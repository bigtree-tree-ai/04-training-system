"""阶段 A 验收 demo — 用真实数据演示三学科核心模块输出

用法：
  python -m scripts.science_demo

输出：
  1. LoadProfile（CTL/ATL/TSB/ACWR/Monotony/Strain）
  2. PolarizationCheck（80/20 极化）
  3. ReturnToRunStage（返跑阶段）
  4. EnergyBalanceReport（能量平衡 + REDs）
  5. DataConfidence（数据可信度）
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from training.science.common.athlete_profile import load_athlete_profile
from training.science.common.confidence import score_confidence
from training.science.training.load_model import compute_load_profile
from training.science.training.pyramid import polarization_check
from training.science.rehab.return_to_run import advance_stage_if_safe
from training.science.nutrition.energy_balance import energy_balance_report
from training.storage.db import get_conn


def _section(title: str):
    print(f"\n{'=' * 70}")
    print(f" {title}")
    print('=' * 70)


def main():
    profile = load_athlete_profile()
    _section("Athlete Profile (v2)")
    print(f"姓名: {profile.name}, 体重: {profile.weight_kg}kg, FFM: {profile.ffm_kg}kg")
    print(f"MaxHR: {profile.max_heart_rate}, RHR: {profile.resting_heart_rate}, LTHR: {profile.lactate_threshold_hr}")
    print(f"Zones: Z1<{profile.zones.z1_max}, Z2<{profile.zones.z2_max}, Z3<{profile.zones.z3_max}, Z4<{profile.zones.z4_max}, Z5<{profile.zones.z5_max}")
    print(f"伤病数: {len(profile.injuries)}")
    for inj in profile.injuries:
        print(f"  - {inj.site} | grade={inj.grade} | stage={inj.current_stage} | VAS={inj.last_pain_vas} | 术后{profile.days_since_surgery}天" if inj.surgery_date else f"  - {inj.site} | grade={inj.grade} | VAS={inj.last_pain_vas}")

    # === 训练负荷 ===
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT date, COALESCE(daily_tss, 0) AS load FROM daily_load ORDER BY date"
        ).fetchall()
    finally:
        conn.close()

    series = [(r["date"], r["load"]) for r in rows]

    _section("LoadProfile (CTL/ATL/TSB)")
    if series:
        lp = compute_load_profile(series)
        print(f"日期范围: {series[0][0]} → {series[-1][0]} ({len(series)} 天)")
        print(json.dumps(lp.to_dict(), ensure_ascii=False, indent=2))
    else:
        print("(无 daily_load 数据)")

    # === 80/20 极化 ===
    _section("PolarizationCheck (近 7 天 z1-z5 时间)")
    conn = get_conn()
    try:
        cutoff = (date.today() - timedelta(days=7)).isoformat()
        sums = conn.execute(
            """SELECT
                COALESCE(SUM(z.zone1_sec),0) z1, COALESCE(SUM(z.zone2_sec),0) z2,
                COALESCE(SUM(z.zone3_sec),0) z3, COALESCE(SUM(z.zone4_sec),0) z4,
                COALESCE(SUM(z.zone5_sec),0) z5
               FROM hr_zone_splits z JOIN sessions s ON z.session_id=s.id
               WHERE s.start_time >= ?""",
            (cutoff,),
        ).fetchone()
    finally:
        conn.close()
    poly = polarization_check(sums["z1"], sums["z2"], sums["z3"], sums["z4"], sums["z5"])
    print(json.dumps(poly.to_dict(), ensure_ascii=False, indent=2))

    # === 返跑阶段 ===
    _section("ReturnToRunStage (左膝)")
    rtr = advance_stage_if_safe(profile, site="L_knee", today_vas=1.0, recent_vas=[1, 1, 2], weekly_hard_min=10)
    print(json.dumps(rtr.to_dict(), ensure_ascii=False, indent=2))

    # === 能量平衡 ===
    _section("EnergyBalanceReport (今日 hr_tss=60, 摄入 2400 kcal)")
    eb = energy_balance_report(profile, age=35, hr_tss_today=60, intake_kcal=2400)
    print(json.dumps(eb.to_dict(), ensure_ascii=False, indent=2))

    # === 数据可信度 ===
    _section("DataConfidence")
    conn = get_conn()
    try:
        last_session = conn.execute("SELECT MAX(start_time) AS t FROM sessions").fetchone()["t"]
        last_load = conn.execute("SELECT MAX(date) AS d FROM daily_load").fetchone()["d"]
        last_hrv = conn.execute("SELECT MAX(date) AS d FROM coros_hrv").fetchone()["d"]
        last_rhr = conn.execute("SELECT MAX(date) AS d FROM coros_heart_rate_daily").fetchone()["d"]
        last_sleep = conn.execute("SELECT MAX(date) AS d FROM coros_sleep").fetchone()["d"]
        today_checkin = conn.execute(
            "SELECT 1 FROM athlete_checkins WHERE date=? LIMIT 1", (date.today().isoformat(),)
        ).fetchone()
    finally:
        conn.close()
    dc = score_confidence(
        has_today_load=bool(last_load and last_load >= date.today().isoformat()),
        has_today_checkin=bool(today_checkin),
        hrv_latest_date=last_hrv,
        rhr_latest_date=last_rhr,
        sleep_latest_date=last_sleep,
        last_session_date=last_session,
        profile_complete=profile.weight_kg > 0,
        injuries_structured=len(profile.injuries) > 0,
    )
    print(f"score={dc.score}  level={dc.level}")
    print(f"missing={dc.missing}")
    print(f"stale={dc.stale}")

    print("\n[demo done]")


if __name__ == "__main__":
    main()
