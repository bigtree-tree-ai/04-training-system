"""能量平衡与 RED-S 风险评估

理论：
- Mifflin-St Jeor BMR (1990)
- ACSM PAL 系数表
- Mountjoy et al. RED-S IOC Consensus 2018/2023
- Loucks et al. EA 阈值：< 30 kcal/kg FFM 红灯 / 30-45 黄灯 / ≥45 绿灯

输出：EnergyBalanceReport dataclass
"""
from __future__ import annotations

from typing import Optional

from training.science.common.athlete_profile import AthleteProfile
from training.science.common.schemas import EnergyBalanceReport
from training.science.nutrition.macros import macros_target


def _bmr_mifflin(weight_kg: float, height_cm: float, age: int, sex: str = "M") -> float:
    """Mifflin-St Jeor 1990"""
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    return base + (5 if sex.upper() == "M" else -161)


def _exercise_kcal_from_hr_tss(hr_tss: float, weight_kg: float) -> float:
    """从 hr_tss 反推训练能量消耗

    经验校准（Banister TRIMP / Coggan TSS 与 EE 关系）：
      60 hr_tss × 65 kg ≈ 600-700 kcal（典型一小时 Z2 跑）
      1 hr_tss × 1 kg ≈ 0.16 kcal
    """
    return round(hr_tss * weight_kg * 0.16, 0)


def compute_tdee(profile: AthleteProfile, age: int, hr_tss_today: float = 0.0) -> tuple[float, float]:
    """返回 (bmr, tdee_with_exercise)"""
    bmr = _bmr_mifflin(profile.weight_kg, profile.height_cm, age)
    base_tdee = bmr * profile.pal
    ex = _exercise_kcal_from_hr_tss(hr_tss_today, profile.weight_kg)
    return round(bmr, 1), round(base_tdee + ex, 1)


def compute_energy_availability(intake_kcal: float, exercise_kcal: float, ffm_kg: float) -> Optional[float]:
    """EA = (intake - exercise) / FFM，单位 kcal/kg FFM"""
    if not ffm_kg or ffm_kg <= 0:
        return None
    return round((intake_kcal - exercise_kcal) / ffm_kg, 1)


def _reds_flag(ea: Optional[float], reds_history: bool) -> str:
    if ea is None:
        return "unknown"
    if ea < 30:
        return "red"
    if ea < 45:
        return "yellow" if not reds_history else "red"
    return "green"


def energy_balance_report(
    profile: AthleteProfile,
    age: int,
    hr_tss_today: float = 0.0,
    intake_kcal: Optional[float] = None,
    long_session_today: bool = False,
) -> EnergyBalanceReport:
    """主入口：综合 TDEE + EA + macros + REDs 标志"""
    bmr, tdee = compute_tdee(profile, age, hr_tss_today)
    exercise_kcal = _exercise_kcal_from_hr_tss(hr_tss_today, profile.weight_kg)
    ea = None
    if intake_kcal is not None and profile.ffm_kg:
        ea = compute_energy_availability(intake_kcal, exercise_kcal, profile.ffm_kg)
    reds = _reds_flag(ea, profile.reds_history)
    targets = macros_target(profile.weight_kg, hr_tss_today, long_session_today)

    notes: list[str] = []
    if reds == "red":
        notes.append("能量可用性低于 30 kcal/kg FFM — REDs 红灯，需立即增加摄入并复查 HRV/月经/睡眠")
    elif reds == "yellow":
        notes.append("能量可用性偏低（30-45）— 黄灯，关注连续 3-7 天趋势")
    if profile.has_active_injury and reds in ("red", "yellow"):
        notes.append("当前有伤情且能量不足，骨骼/软组织修复将受影响")
    if hr_tss_today > 100 and (intake_kcal or 0) < tdee * 0.9:
        notes.append("高负荷日摄入低于 90% TDEE，建议训练后 30 分钟内补碳水 1g/kg + 蛋白 0.3g/kg")

    return EnergyBalanceReport(
        tdee_kcal=tdee,
        intake_kcal=intake_kcal,
        exercise_kcal=exercise_kcal,
        ea_kcal_per_kg_ffm=ea,
        reds_flag=reds,
        macros_target=targets,
        notes=notes,
    )
