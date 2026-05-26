"""结构化输出 schema（dataclass，避免引入 pydantic v2 依赖）

这些 schema 既被规则引擎直接消费，也被 LLM few-shot 引用为期望输出格式。
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class LoadProfile:
    """训练负荷剖面（基于 Friel PMC + Banister 模型）"""
    ctl: float           # Chronic Training Load (42d EWMA)
    atl: float           # Acute Training Load (7d EWMA)
    tsb: float           # Training Stress Balance = CTL - ATL
    acwr_7_28: Optional[float]  # 7d:28d 滚动 ACWR
    monotony: Optional[float]   # 7d mean / 7d std
    strain: Optional[float]     # monotony × weekly_load
    verdict: str         # 文字结论：safe/build/peak/overreach/detrain

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PolarizationCheck:
    """80/20 极化训练检查（Seiler 2009/2014）"""
    easy_pct: float      # Z1+Z2 时间占比
    moderate_pct: float  # Z3
    hard_pct: float      # Z4+Z5
    polarization_index: Optional[float]  # PI = log10(time_z1×time_z3/time_z2²)，Treff 2019
    verdict: str         # polarized/threshold-heavy/easy-heavy/balanced
    days_window: int = 7

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ReturnToRunStage:
    """术后/伤后返跑梯度（5 阶模型）

    阶段：
      0 = 完全休息 / 仅康复训练
      1 = 步行 + 康复
      2 = 走跑交替 1:4
      3 = 走跑交替 1:1（连续慢跑前夜）
      4 = 连续慢跑（仅 Z1-Z2）
      5 = 节奏跑/比赛配速
    """
    stage: int            # 0-5
    stage_name: str
    capacity_pct: Optional[float]  # 当前组织承载力相对基线百分比
    last_pain_vas: Optional[float] # 最近 VAS 0-10
    next_milestone_date: Optional[str] = None
    today_action: str = "keep"     # keep / advance / back-off / stop
    do: list[str] = field(default_factory=list)
    avoid: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EnergyBalanceReport:
    """能量平衡报告（IOC Sports Nutrition 2018 + RED-S 2023）"""
    tdee_kcal: float          # 总日消耗
    intake_kcal: Optional[float]
    exercise_kcal: float
    ea_kcal_per_kg_ffm: Optional[float]  # 能量可用性
    reds_flag: str             # green / yellow / red
    macros_target: dict        # {cho_g, pro_g, fat_g}
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SciencePrescription:
    """跨学科聚合处方（用于 today/decision 页消费）"""
    date: str
    training: Optional[dict] = None    # LoadProfile + PolarizationCheck
    rehab: Optional[dict] = None        # ReturnToRunStage + 当日红线
    nutrition: Optional[dict] = None    # EnergyBalanceReport
    confidence: float = 1.0             # 0-1，反映输入数据可信度
    verdict: str = ""                   # 一句话结论
    why: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)
