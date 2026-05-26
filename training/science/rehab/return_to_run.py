"""返跑梯度模型（5 阶 + 0 阶静养）

理论参考：
- ACSM/APTA Return-to-Sport Continuum
- van Melick KNGF 2016 ACL 术后康复指南
- Pain Monitoring Model (Thomeé)：VAS≤2 持续 3 课且第二天晨痛 ≤1 → 进阶；VAS>4 → 退阶

阶段：
  0 = 完全休息（仅康复训练 / 物理治疗）
  1 = 步行 + 物理治疗
  2 = 走跑交替 1:4（走 4 分钟跑 1 分钟）
  3 = 走跑交替 1:1
  4 = 连续慢跑（仅 Z1-Z2，时长上限按阶段）
  5 = 节奏跑 / 比赛配速

每阶通关条件：连续 3 节训练 VAS ≤ 2，且最近 7 天没有 VAS > 4 事件，
且距上次手术天数满足该阶要求。

可执行规则：
- R-R1：术后 < 6 个月且本周 z4+z5 时间 > 20 min → 阻断（强制降到阶段 4）
- R-R2：今日疼痛 VAS ≥ 4 → today_action = back-off，今日替换 cross-training
- R-R3：负荷-痛矩阵高负荷+痛升 ≥ 2 次/周 → 强制 7 天减量 50%
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from training.science.common.athlete_profile import AthleteProfile, Injury
from training.science.common.schemas import ReturnToRunStage


_STAGE_NAMES = {
    0: "完全休息（仅康复训练）",
    1: "步行 + 物理治疗",
    2: "走跑交替 1:4",
    3: "走跑交替 1:1",
    4: "连续慢跑（Z1-Z2）",
    5: "节奏跑 / 比赛配速",
}


# 每阶最早允许进入所需的术后天数（适用于 III post-op 级别伤病）
_STAGE_MIN_DAYS_POSTOP = {
    0: 0,
    1: 14,    # 术后 2 周可步行
    2: 60,    # 术后 8-9 周
    3: 90,    # 术后 12 周
    4: 120,   # 术后 16 周
    5: 180,   # 术后 6 个月
}


def _safe_to_advance(
    recent_vas: list[float],
    today_vas: float,
    stage: int,
    days_since_surgery: Optional[int],
    grade: str,
) -> bool:
    """是否可以从 stage 进 stage+1"""
    if stage >= 5:
        return False
    if today_vas > 2:
        return False
    if recent_vas and any(v > 4 for v in recent_vas[-7:]):
        return False
    last3 = [v for v in recent_vas[-3:] if v is not None]
    if len(last3) >= 3 and any(v > 2 for v in last3):
        return False
    if "post-op" in grade.lower() and days_since_surgery is not None:
        if days_since_surgery < _STAGE_MIN_DAYS_POSTOP.get(stage + 1, 0):
            return False
    return True


def assess_return_to_run(
    injury: Optional[Injury],
    today_vas: float = 0.0,
    recent_vas: Optional[list[float]] = None,
    weekly_hard_min: float = 0.0,
) -> ReturnToRunStage:
    """主入口：根据当前伤病、近期 VAS、本周高强度时长判断返跑阶段与今日动作"""
    recent_vas = recent_vas or []

    if injury is None:
        return ReturnToRunStage(
            stage=5,
            stage_name=_STAGE_NAMES[5],
            capacity_pct=100.0,
            last_pain_vas=today_vas,
            today_action="keep",
            do=["保持当前训练", "正常 80/20 极化"],
            avoid=[],
        )

    grade = injury.grade or "I"
    cur_stage = max(0, min(int(injury.current_stage), 5))
    days_post = None
    if injury.surgery_date:
        try:
            days_post = (date.today() - date.fromisoformat(injury.surgery_date)).days
        except ValueError:
            days_post = None

    # R-R2: 今日强痛 → back-off
    if today_vas >= 4:
        return ReturnToRunStage(
            stage=max(cur_stage - 1, 0),
            stage_name=_STAGE_NAMES.get(max(cur_stage - 1, 0), ""),
            capacity_pct=injury.capacity_pct or 50.0,
            last_pain_vas=today_vas,
            today_action="back-off",
            do=["今日改为 cross-training（游泳 / 椭圆机 / 上肢力量）", "冰敷 + 抗炎评估"],
            avoid=["跑步", "下楼梯负重", "深蹲", "下坡"],
        )

    # R-R1: 术后 < 6 月且本周高强度 >20 min → 强制降阶
    if "post-op" in grade.lower() and days_post is not None and days_post < 180 and weekly_hard_min > 20:
        return ReturnToRunStage(
            stage=min(cur_stage, 4),
            stage_name=_STAGE_NAMES[min(cur_stage, 4)],
            capacity_pct=injury.capacity_pct,
            last_pain_vas=today_vas,
            today_action="back-off",
            do=["本周内禁止 Z4+Z5", "改为纯 Z1-Z2 有氧"],
            avoid=["间歇训练", "节奏跑", "比赛配速"],
        )

    # 是否可进阶
    can_advance = _safe_to_advance(recent_vas, today_vas, cur_stage, days_post, grade)
    if can_advance:
        new_stage = cur_stage + 1
        return ReturnToRunStage(
            stage=new_stage,
            stage_name=_STAGE_NAMES[new_stage],
            capacity_pct=injury.capacity_pct,
            last_pain_vas=today_vas,
            today_action="advance",
            do=[f"今日按阶段 {new_stage} 执行", "记录晨痛 VAS"],
            avoid=["跨阶段尝试比赛配速"],
        )

    # 默认保持
    return ReturnToRunStage(
        stage=cur_stage,
        stage_name=_STAGE_NAMES[cur_stage],
        capacity_pct=injury.capacity_pct,
        last_pain_vas=today_vas,
        today_action="keep",
        do=[f"按阶段 {cur_stage} 维持", "晨痛连续 3 天 ≤2 可考虑进阶"],
        avoid=["突然加量", "高冲击落地"],
    )


def advance_stage_if_safe(profile: AthleteProfile, site: str, today_vas: float, recent_vas: list[float], weekly_hard_min: float = 0.0) -> ReturnToRunStage:
    """便捷入口：从 profile 中找到目标 site 的伤病并评估"""
    target = next((i for i in profile.injuries if i.site == site), None)
    return assess_return_to_run(target, today_vas, recent_vas, weekly_hard_min)
