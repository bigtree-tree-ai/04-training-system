"""专业数据解读文案系统"""
from training.content.interpretations import (
    interpret_ctl,
    interpret_tsb,
    interpret_acwr,
    interpret_vo2max,
    interpret_training_status,
    interpret_hr_drift,
    interpret_marathon_shape,
    interpret_recovery_score,
    interpret_zone_distribution,
    interpret_comparison_metric,
)

__all__ = [
    "interpret_ctl",
    "interpret_tsb",
    "interpret_acwr",
    "interpret_vo2max",
    "interpret_training_status",
    "interpret_hr_drift",
    "interpret_marathon_shape",
    "interpret_recovery_score",
    "interpret_zone_distribution",
    "interpret_comparison_metric",
]
