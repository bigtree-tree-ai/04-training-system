"""三大营养素目标 — Burke et al. CHO periodization

碳水分级（g/kg/day）：
  Easy/休息: 5
  Moderate: 7
  Hard: 8-10
  Long race day: 10

蛋白：1.6-2.0 g/kg
脂肪：0.8-1.2 g/kg
"""
from __future__ import annotations


def macros_target(weight_kg: float, hr_tss: float = 0.0, long_session: bool = False) -> dict:
    if long_session or hr_tss >= 100:
        cho_per_kg = 9.0
    elif hr_tss >= 60:
        cho_per_kg = 7.0
    elif hr_tss >= 30:
        cho_per_kg = 6.0
    else:
        cho_per_kg = 5.0
    pro_per_kg = 1.8
    fat_per_kg = 1.0
    return {
        "cho_g": round(weight_kg * cho_per_kg, 0),
        "pro_g": round(weight_kg * pro_per_kg, 0),
        "fat_g": round(weight_kg * fat_per_kg, 0),
        "cho_per_kg": cho_per_kg,
        "pro_per_kg": pro_per_kg,
        "fat_per_kg": fat_per_kg,
    }
