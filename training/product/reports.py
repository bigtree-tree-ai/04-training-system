"""Product-facing report builders."""
from __future__ import annotations

from typing import Any


def build_first_report(
    session: dict[str, Any],
    laps: list[dict[str, Any]],
    hr_zones: dict[str, Any],
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a plain-language first report for a newly uploaded FIT activity."""
    profile = profile or {}
    distance = session.get("distance_km")
    duration = session.get("duration_sec")
    avg_hr = session.get("avg_hr")
    avg_pace = session.get("avg_pace_sec")
    ascent = session.get("total_ascent")
    risk_flags = _risk_flags(session, hr_zones, profile)
    report = {
        "title": _title(session),
        "summary": _summary(distance, duration, avg_hr, avg_pace),
        "metrics": {
            "distance_km": distance,
            "duration_min": round(duration / 60, 1) if duration else None,
            "avg_hr": avg_hr,
            "max_hr": session.get("max_hr"),
            "avg_pace_sec": avg_pace,
            "total_ascent_m": ascent,
            "hr_tss": session.get("hr_tss"),
            "pace_cv": session.get("pace_cv"),
            "hr_drift_pct": session.get("hr_drift_pct"),
            "efficiency_factor": session.get("efficiency_factor"),
        },
        "hr_zone_distribution": hr_zones or {},
        "lap_count": len(laps),
        "risk_level": _risk_level(risk_flags),
        "risk_flags": risk_flags,
        "next_steps": _next_steps(risk_flags),
        "evidence_basis": [
            "训练负荷优先按近期强度、时长、心率和主观伤痛共同判断。",
            "小白用户默认采用保守康复优先策略，高风险时不自动安排强度。",
            "有氧基础期优先保持多数训练在可交谈的低强度区间。",
        ],
        "disclaimer": "本报告用于训练管理，不构成医疗诊断；异常疼痛、胸痛、晕厥或术后异常反应需要线下专业评估。",
    }
    return report


def _title(session: dict[str, Any]) -> str:
    sport = session.get("sport") or "activity"
    if sport == "running":
        sport = "跑步"
    return f"首份{sport}训练报告"


def _summary(distance, duration, avg_hr, avg_pace) -> str:
    parts = []
    if distance:
        parts.append(f"{distance:.2f} km")
    if duration:
        parts.append(f"{duration / 60:.0f} 分钟")
    if avg_hr:
        parts.append(f"平均心率 {avg_hr}")
    if avg_pace:
        parts.append(f"平均配速 {_format_pace(avg_pace)}/km")
    if not parts:
        return "FIT 文件已解析，但可用指标较少；后续需要更多训练记录建立个人基线。"
    return "本次训练核心数据：" + "，".join(parts) + "。"


def _risk_flags(session: dict[str, Any], hr_zones: dict[str, Any], profile: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    duration = session.get("duration_sec") or 0
    distance = session.get("distance_km") or 0
    avg_hr = session.get("avg_hr") or 0
    z4 = hr_zones.get("zone4_pct") or 0 if hr_zones else 0
    z5 = hr_zones.get("zone5_pct") or 0 if hr_zones else 0
    current_injury = (profile.get("current_injury") or "").strip()
    if _has_actionable_injury(current_injury):
        flags.append(f"当前伤痛背景：{current_injury}")
    if duration >= 7200 or distance >= 21:
        flags.append("本次训练时长/距离较高，跑后 24-48 小时优先恢复")
    if avg_hr >= 160:
        flags.append("平均心率偏高，避免连续安排强度")
    if z4 + z5 >= 25:
        flags.append("高心率区占比较高，下一次训练建议降强度")
    if not session.get("avg_hr"):
        flags.append("缺少心率数据，负荷判断置信度下降")
    return flags


def _risk_level(flags: list[str]) -> str:
    if any("伤痛" in flag or "偏高" in flag or "高心率" in flag for flag in flags):
        return "high"
    if flags:
        return "moderate"
    return "low"


def _next_steps(flags: list[str]) -> list[str]:
    if _risk_level(flags) == "high":
        return ["今天不追加高强度", "记录疼痛和疲劳 0-10 分", "下一次训练从 Z1-Z2 开始"]
    if flags:
        return ["补水和碳水", "保证睡眠", "下一次以轻松跑或力量稳定训练为主"]
    return ["跑后补水", "记录主观感受", "继续积累低强度有氧基线"]


def _format_pace(seconds: float) -> str:
    minutes = int(seconds // 60)
    sec = int(seconds % 60)
    return f"{minutes}:{sec:02d}"


def _has_actionable_injury(text: str) -> bool:
    normalized = (text or "").strip().lower()
    if not normalized:
        return False
    no_issue_markers = (
        "无明显疼痛",
        "无疼痛",
        "无痛",
        "无不适",
        "没有疼痛",
        "没有不适",
        "不痛",
        "none",
        "no pain",
        "no issue",
    )
    return not any(marker in normalized for marker in no_issue_markers)
