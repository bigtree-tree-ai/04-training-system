"""Deterministic agentic coach team for v1."""
from __future__ import annotations

from training.domain.models import (
    CoachRecommendation,
    EvidenceDocument,
    ExpertContribution,
    ReadinessFeatures,
    SubjectiveCheckin,
    TrainingPlanItem,
)

HIGH_INTENSITY_TYPES = {"Interval", "Threshold", "Tempo", "Long Run"}


class AgenticCoachTeam:
    """A traceable multi-expert coach.

    v1 keeps the decision logic deterministic and auditable. LLM adapters can be
    added behind CoachAgentPort later without changing API consumers.
    """

    def recommend(
        self,
        features: ReadinessFeatures,
        plan_item: TrainingPlanItem | None,
        checkin: SubjectiveCheckin | None,
        evidence: list[EvidenceDocument],
        phase: str = "morning",
    ) -> CoachRecommendation:
        planned_type = plan_item.workout_type if plan_item else None
        risk_level = _overall_risk(features)
        has_high_intensity = planned_type in HIGH_INTENSITY_TYPES
        needs_confirmation = risk_level in {"moderate", "high"} or has_high_intensity

        if risk_level == "high":
            title = "今天优先保护恢复"
            action = "建议取消高强度训练，改为完全休息、轻度活动或康复力量，并记录疼痛变化。"
            workout_type = "Recovery / Rest"
        elif risk_level == "moderate":
            title = "今天建议降载执行"
            action = "建议把计划改成Z1-Z2轻松跑或低冲击交叉训练，结束后补充跑后反馈。"
            workout_type = "Easy / Recovery"
        elif planned_type:
            title = "可以按计划训练"
            action = f"按今日课表执行：{planned_type}。训练中持续观察膝盖、后背和心率漂移。"
            workout_type = planned_type
        else:
            title = "今天需要补一个轻量课表"
            action = "没有找到今日课表。若身体感觉正常，建议30-45分钟Z2轻松跑或力量灵活性训练。"
            workout_type = "Easy / Strength"

        input_evidence = _input_evidence(features, plan_item, checkin)
        experts = _expert_votes(features, plan_item, checkin, risk_level)
        summary = _summary(features, plan_item, risk_level)

        return CoachRecommendation(
            id=None,
            recommendation_date=features.date,
            phase=phase,
            risk_level=risk_level,
            title=title,
            summary=summary,
            recommended_action=action,
            workout_type=workout_type,
            needs_confirmation=needs_confirmation,
            input_evidence=input_evidence,
            evidence_refs=evidence[:5],
            expert_votes=experts,
        )


def _overall_risk(features: ReadinessFeatures) -> str:
    risks = {features.load_risk, features.injury_risk, features.pain_risk}
    if "high" in risks or features.readiness_score < 35:
        return "high"
    if "moderate" in risks or features.readiness_score < 60:
        return "moderate"
    return "low"


def _summary(features: ReadinessFeatures, plan_item: TrainingPlanItem | None, risk_level: str) -> str:
    plan_text = plan_item.workout_type if plan_item else "无课表"
    return (
        f"Readiness {features.readiness_score}/100，恢复 {features.recovery_score}/100，"
        f"负荷风险 {features.load_risk}，伤病风险 {features.injury_risk}，"
        f"疼痛风险 {features.pain_risk}。今日计划：{plan_text}。综合风险：{risk_level}。"
    )


def _input_evidence(
    features: ReadinessFeatures,
    plan_item: TrainingPlanItem | None,
    checkin: SubjectiveCheckin | None,
) -> list[str]:
    factors = features.factors
    load = factors.get("latest_load", {})
    canonical = factors.get("canonical", {})
    evidence = [
        f"readiness_score={features.readiness_score}",
        f"recovery_score={features.recovery_score}",
        f"load_risk={features.load_risk}, injury_risk={features.injury_risk}, pain_risk={features.pain_risk}",
    ]
    if load:
        evidence.append(
            "PMC: "
            f"CTL={load.get('ctl')}, ATL={load.get('atl')}, TSB={load.get('tsb')}, "
            f"ACWR={load.get('acwr')}, monotony={load.get('monotony')}"
        )
    if canonical:
        evidence.append(
            "daily metrics: "
            f"sleep_score={canonical.get('sleep_score')}, hrv={canonical.get('hrv_ms')}, "
            f"resting_hr={canonical.get('resting_hr')}, stress={canonical.get('stress_avg')}"
        )
    if checkin:
        evidence.append(
            "subjective: "
            f"fatigue={checkin.fatigue_level}, soreness={checkin.soreness_level}, "
            f"knee={checkin.pain_knee}, back={checkin.pain_back}, notes={checkin.injury_notes or '-'}"
        )
    if plan_item:
        evidence.append(
            "plan: "
            f"{plan_item.workout_type}, distance={plan_item.target_distance_km}, "
            f"zone={plan_item.target_hr_zone}, source={plan_item.source}"
        )
    return evidence


def _expert_votes(
    features: ReadinessFeatures,
    plan_item: TrainingPlanItem | None,
    checkin: SubjectiveCheckin | None,
    risk_level: str,
) -> list[ExpertContribution]:
    planned_type = plan_item.workout_type if plan_item else "无课表"
    pain_note = checkin.injury_notes if checkin and checkin.injury_notes else "无新增疼痛备注"

    return [
        ExpertContribution(
            expert="数据质检",
            stance="可用" if features.input_version_hash else "需补充",
            rationale=f"已生成输入版本 {features.input_version_hash}，可追溯到 canonical/features 表。",
            confidence=0.82,
        ),
        ExpertContribution(
            expert="恢复康复",
            stance="保守" if features.injury_risk in {"moderate", "high"} else "放行",
            rationale=f"疼痛风险 {features.pain_risk}，伤病风险 {features.injury_risk}；备注：{pain_note}。",
            confidence=0.84,
        ),
        ExpertContribution(
            expert="马拉松/戈21训练",
            stance="降载" if risk_level != "low" else "执行",
            rationale=f"今日计划 {planned_type}，readiness={features.readiness_score}。",
            confidence=0.78,
        ),
        ExpertContribution(
            expert="力量灵活性",
            stance="建议加入",
            rationale="膝关节术后背景下，跑步训练外保留低冲击力量、髋膝踝稳定和灵活性工作。",
            confidence=0.76,
        ),
        ExpertContribution(
            expert="营养补给",
            stance="记录优先",
            rationale="v1先记录水、咖啡因、饮食备注；长距离和多日赛事补给策略后续按个人耐受迭代。",
            confidence=0.68,
        ),
        ExpertContribution(
            expert="计划调整",
            stance="需确认" if risk_level != "low" or planned_type in HIGH_INTENSITY_TYPES else "无需确认",
            rationale="高强度、降载和伤痛相关调整默认进入人工确认。",
            confidence=0.88,
        ),
        ExpertContribution(
            expert="安全审核",
            stance="阻断高强度" if risk_level == "high" else "通过",
            rationale=f"综合风险为 {risk_level}，AI不做医疗诊断，红旗症状只触发降载和线下评估提醒。",
            confidence=0.9,
        ),
        ExpertContribution(
            expert="证据检索",
            stance="已引用",
            rationale="建议来自精选证据库条目，后续可通过PubMed API定期刷新。",
            confidence=0.72,
        ),
    ]
