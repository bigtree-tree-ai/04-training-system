"""运动营养学子包 — IOC 2018 / RED-S 2023 / Burke / Jeukendrup"""

from training.science.nutrition.energy_balance import (
    compute_tdee,
    compute_energy_availability,
    energy_balance_report,
)
from training.science.nutrition.macros import macros_target
from training.science.nutrition.fueling import fueling_plan

__all__ = [
    "compute_tdee",
    "compute_energy_availability",
    "energy_balance_report",
    "macros_target",
    "fueling_plan",
]
