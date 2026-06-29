"""Professional sports-science dashboard aggregation.

This module builds the first version of the professional surface without
changing the productized beginner flow.  It deliberately reuses the existing
agentic Today service, SQLite tables, and curated evidence store so every page
can explain where a recommendation came from.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from training import config
from training.adapters.sqlite_repositories import SQLiteTrainingRepository
from training.application.serializers import to_plain
from training.application.today import TodayService
from training.evidence.retriever import CuratedEvidenceRetriever
from training.storage.db import get_conn, init_db


FRAMEWORK_MODULES = [
    {
        "key": "training_science",
        "title": "运动训练学",
        "question": "负荷是否推动适应，而不是制造不可恢复的疲劳？",
        "signals": ["CTL/ATL/TSB", "ACWR", "周跑量", "心率分区", "专项长距离"],
        "rules": ["负荷快速上升优先降载", "低强度基线优先于频繁强度", "关键课只在低风险日执行"],
        "source": "ACSM / IOC load consensus",
    },
    {
        "key": "return_to_sport",
        "title": "运动康复与返场",
        "question": "膝关节术后和当前疼痛是否允许今天的训练刺激？",
        "signals": ["膝痛/背痛 0-10", "跑后反应", "连续跑步天数", "红旗描述"],
        "rules": ["疼痛升级阻断强度", "返场按参与-专项-表现连续进阶", "恢复不足时先保组织耐受"],
        "source": "Return-to-sport consensus / IOC pain",
    },
    {
        "key": "sports_nutrition",
        "title": "运动营养学",
        "question": "今天的能量、水盐和咖啡因策略是否匹配训练负荷？",
        "signals": ["饮水", "咖啡因", "睡眠", "长距离/多日负荷", "饮食备注"],
        "rules": ["长距离补给必须训练中演练", "睡眠差时咖啡因不掩盖疲劳", "REDs 风险只提示不诊断"],
        "source": "ISSN ultra-marathon nutrition / IOC REDs",
    },
    {
        "key": "strength_mobility",
        "title": "力量与灵活性",
        "question": "跑步外是否有足够的髋膝踝稳定和核心支撑？",
        "signals": ["术后背景", "疼痛部位", "训练类型分布", "连续跑步天数"],
        "rules": ["跑量之外保留抗阻训练", "膝/背风险日优先低冲击力量", "动作选择服从疼痛反应"],
        "source": "ACSM resistance training position stand",
    },
    {
        "key": "explainable_ai",
        "title": "数据质量与可解释 AI",
        "question": "结论是否能追溯到原始数据、规则和证据？",
        "signals": ["FIT 文件", "COROS MCP", "主观晨检", "课表", "输入版本"],
        "rules": ["缺数据时降低置信度", "建议保留审计记录", "医疗红旗只触发线下评估建议"],
        "source": "FIT SDK / COROS MCP / local audit trail",
    },
]


class ProfessionalDashboardService:
    """Build professional-page contracts for HTML and JSON consumers."""

    def __init__(self, repository: SQLiteTrainingRepository | None = None):
        self.repository = repository or SQLiteTrainingRepository()
        self.today_service = TodayService(repository=self.repository)
        self.evidence = CuratedEvidenceRetriever(self.repository)

    def get_today_decision(
        self,
        day: date | None = None,
        phase: str = "morning",
        refresh: bool = False,
    ) -> dict[str, Any]:
        day = day or date.today()
        today = self.today_service.get_today(day=day, phase=phase, refresh=refresh)
        features = today["features"]
        recommendation = today["recommendation"]
        checkin = today.get("checkin") or {}
        plan = today.get("plan")
        athlete = today.get("athlete") or {}

        load_rows = _daily_load_rows(day, 90)
        weekly_rows = _weekly_rows(12)
        recent_sessions = _recent_sessions(12)
        coros = _coros_context(day)
        quality = _data_quality(day, checkin, plan, load_rows, coros)
        charts = _chart_payload(load_rows, weekly_rows, day)
        charts["readiness_waterfall"] = _readiness_waterfall(features, checkin)
        risk_matrix = _risk_matrix(features, checkin, athlete, plan, load_rows)
        nutrition = _nutrition_context(checkin, features, risk_matrix, plan)
        narrative = _narrative(today, risk_matrix, quality, nutrition, load_rows, weekly_rows)
        evidence_matrix = _evidence_matrix(self.evidence)
        audit = _recommendation_audit(recommendation, features, quality)

        return {
            "date": day.isoformat(),
            "phase": phase,
            "today": today,
            "athlete": athlete,
            "features": features,
            "recommendation": recommendation,
            "checkin": checkin,
            "plan": plan,
            "narrative": narrative,
            "data_quality": quality,
            "risk_matrix": risk_matrix,
            "nutrition": nutrition,
            "charts": charts,
            "framework_modules": FRAMEWORK_MODULES,
            "evidence_matrix": evidence_matrix,
            "audit": audit,
            "recent_sessions": recent_sessions,
            "source_timeline": quality["source_timeline"],
            "legacy_links": [
                {"label": "传统仪表板", "href": "/dashboard"},
                {"label": "训练记录", "href": "/sessions"},
                {"label": "COROS全景", "href": "/coros"},
            ],
        }

    def get_data_center(self) -> dict[str, Any]:
        context = self.get_today_decision()
        context["raw_ingest"] = _raw_ingest_summary()
        context["fit_library"] = _fit_library_summary()
        return context

    def get_performance(self) -> dict[str, Any]:
        context = self.get_today_decision()
        context["performance"] = _performance_summary(context["charts"], context["recent_sessions"])
        return context

    def get_rehab(self) -> dict[str, Any]:
        context = self.get_today_decision()
        context["rehab"] = _rehab_summary(context)
        return context

    def get_nutrition(self) -> dict[str, Any]:
        context = self.get_today_decision()
        context["nutrition_plan"] = _nutrition_plan(context)
        return context

    def get_evidence_model(self) -> dict[str, Any]:
        context = self.get_today_decision()
        context["recommendations"] = _recent_recommendations(8)
        context["model_card"] = _model_card(context)
        return context


def _daily_load_rows(day: date, days: int) -> list[dict[str, Any]]:
    init_db()
    from_date = (day - timedelta(days=days - 1)).isoformat()
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT * FROM daily_load
            WHERE date >= ? AND date <= ?
            ORDER BY date
            """,
            (from_date, day.isoformat()),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _weekly_rows(limit: int) -> list[dict[str, Any]]:
    init_db()
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT * FROM weekly_summaries
            ORDER BY year DESC, week_number DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in reversed(rows)]
    finally:
        conn.close()


def _recent_sessions(limit: int) -> list[dict[str, Any]]:
    init_db()
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT id, filename, sport, start_time, duration_sec, distance_km,
                   avg_hr, max_hr, avg_pace_sec, avg_cadence, total_ascent,
                   hr_tss, pace_cv, hr_drift_pct, efficiency_factor, vo2max,
                   training_type, training_effect_label, recovery_hours
            FROM sessions
            ORDER BY start_time DESC, id DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _coros_context(day: date) -> dict[str, Any]:
    init_db()
    conn = get_conn()
    try:
        date_str = day.isoformat()
        return {
            "latest_sync": _one(
                conn,
                "SELECT * FROM coros_sync_runs ORDER BY started_at DESC, id DESC LIMIT 1",
            ),
            "daily_health": _one(conn, "SELECT * FROM coros_daily_health WHERE date=?", (date_str,)),
            "sleep": _one(conn, "SELECT * FROM coros_sleep WHERE date=?", (date_str,)),
            "hrv": _one(conn, "SELECT * FROM coros_hrv WHERE date=?", (date_str,)),
            "heart_rate": _one(conn, "SELECT * FROM coros_heart_rate_daily WHERE date=?", (date_str,)),
            "stress": _one(conn, "SELECT * FROM coros_stress_daily WHERE date=?", (date_str,)),
            "recovery": _one(
                conn,
                "SELECT * FROM coros_recovery_snapshots ORDER BY captured_at DESC, id DESC LIMIT 1",
            ),
            "fitness": _one(
                conn,
                "SELECT * FROM coros_fitness_snapshots ORDER BY captured_at DESC, id DESC LIMIT 1",
            ),
            "schedule_count": _count(conn, "SELECT COUNT(*) FROM coros_training_schedule"),
            "device_count": _count(conn, "SELECT COUNT(*) FROM coros_devices"),
        }
    finally:
        conn.close()


def _data_quality(day: date, checkin: dict, plan: dict | None, load_rows: list[dict], coros: dict) -> dict:
    init_db()
    conn = get_conn()
    try:
        session_count = _count(conn, "SELECT COUNT(*) FROM sessions")
        running_count = _count(conn, "SELECT COUNT(*) FROM sessions WHERE (sport='running' OR sport LIKE '%Run%')")
        latest_session = _one(
            conn,
            """
            SELECT filename, start_time, sport, distance_km
            FROM sessions ORDER BY start_time DESC, id DESC LIMIT 1
            """,
        )
        evidence_count = _count(conn, "SELECT COUNT(*) FROM evidence_documents")
        raw_count = _count(conn, "SELECT COUNT(*) FROM raw_ingest_events")
    finally:
        conn.close()

    latest_load = load_rows[-1] if load_rows else {}
    latest_sync = coros.get("latest_sync") or {}
    sync_status = latest_sync.get("status") or "missing"
    sync_at = latest_sync.get("finished_at") or latest_sync.get("started_at")

    source_scores = [
        _source_score("FIT 文件", bool(session_count), latest_session.get("start_time")),
        _source_score("COROS MCP", sync_status == "success", sync_at),
        _source_score("主观晨检", bool(checkin), day.isoformat() if checkin else None),
        _source_score("训练课表", bool(plan), day.isoformat() if plan else None),
        _source_score("分析特征", bool(latest_load), latest_load.get("date")),
    ]

    confidence = 45
    confidence += 15 if session_count else 0
    confidence += 15 if latest_load else 0
    confidence += 15 if sync_status == "success" else 0
    confidence += 10 if checkin else 0
    confidence += 8 if plan else 0
    confidence += 7 if evidence_count else 0
    confidence = min(confidence, 100)

    input_gaps = []
    if not checkin:
        input_gaps.append("缺少今日主观晨检，疼痛/疲劳/营养判断置信度下降")
    if not plan:
        input_gaps.append("缺少今日课表，系统只能给默认训练建议")
    if not latest_load:
        input_gaps.append("缺少 PMC 负荷曲线，训练负荷趋势不可判定")
    if sync_status != "success":
        input_gaps.append("COROS MCP 最近未成功同步，睡眠/HRV/恢复可能不是最新")
    if not evidence_count:
        input_gaps.append("证据库尚未初始化")

    return {
        "confidence": confidence,
        "level": _quality_level(confidence),
        "session_count": session_count,
        "running_count": running_count,
        "raw_ingest_count": raw_count,
        "evidence_count": evidence_count,
        "latest_session": latest_session,
        "latest_load": latest_load,
        "coros_sync": {
            "status": sync_status,
            "updated_at": sync_at,
            "message": latest_sync.get("message") or "",
        },
        "source_timeline": source_scores,
        "input_gaps": input_gaps,
    }


def _chart_payload(load_rows: list[dict], weekly_rows: list[dict], day: date) -> dict[str, Any]:
    return {
        "readiness_waterfall": {},
        "pmc": {
            "labels": [row["date"] for row in load_rows],
            "ctl": [_round(row.get("ctl")) for row in load_rows],
            "atl": [_round(row.get("atl")) for row in load_rows],
            "tsb": [_round(row.get("tsb")) for row in load_rows],
            "acwr": [_round(row.get("acwr")) for row in load_rows],
            "tss": [_round(row.get("daily_tss")) for row in load_rows],
        },
        "weekly": {
            "labels": [f"{row.get('year')}-W{row.get('week_number')}" for row in weekly_rows],
            "run_km": [_round(row.get("run_distance_km")) for row in weekly_rows],
            "total_tss": [_round(row.get("total_hr_tss")) for row in weekly_rows],
            "sessions": [row.get("total_sessions") or 0 for row in weekly_rows],
        },
        "zones": _zone_distribution(day, 28),
        "sleep_recovery": _sleep_recovery_chart(day, 28),
        "pain_load": _pain_load_chart(day, 42),
        "nutrition_timeline": _nutrition_timeline_chart(),
    }


def _readiness_waterfall(features: dict[str, Any], checkin: dict[str, Any]) -> dict[str, Any]:
    factors = features.get("factors") or {}
    pain_score = factors.get("pain_score") or 0
    fatigue = checkin.get("fatigue_level") if checkin else None
    recovery = features.get("recovery_score") or 0
    sleep = features.get("sleep_score")
    load_penalty = {
        "high": -22,
        "moderate": -10,
        "detraining": -4,
        "low": 0,
    }.get(features.get("load_risk"), 0)
    sleep_delta = round((sleep - recovery) * 0.35, 1) if sleep is not None else 0
    pain_penalty = -pain_score * 4
    fatigue_penalty = -max((fatigue or 0) - 2, 0) * 6 if fatigue is not None else 0
    return {
        "labels": ["恢复基础", "睡眠调整", "负荷调整", "疼痛调整", "疲劳调整", "最终"],
        "values": [
            recovery,
            sleep_delta,
            load_penalty,
            pain_penalty,
            fatigue_penalty,
            features.get("readiness_score") or 0,
        ],
    }


def _zone_distribution(day: date, days: int) -> dict[str, Any]:
    from_date = (day - timedelta(days=days - 1)).isoformat()
    init_db()
    conn = get_conn()
    try:
        row = conn.execute(
            """
            SELECT
                SUM(h.zone1_sec) as z1,
                SUM(h.zone2_sec) as z2,
                SUM(h.zone3_sec) as z3,
                SUM(h.zone4_sec) as z4,
                SUM(h.zone5_sec) as z5
            FROM sessions s
            JOIN hr_zone_splits h ON s.id = h.session_id
            WHERE (s.sport='running' OR s.sport LIKE '%Run%') AND DATE(s.start_time) >= ?
            """,
            (from_date,),
        ).fetchone()
    finally:
        conn.close()

    values = [row[key] or 0 for key in ("z1", "z2", "z3", "z4", "z5")] if row else [0, 0, 0, 0, 0]
    total = sum(values)
    percentages = [round(value / total * 100, 1) if total else 0 for value in values]
    return {
        "labels": ["Z1 恢复", "Z2 有氧", "Z3 节奏", "Z4 阈值", "Z5 极量"],
        "values": percentages,
        "seconds": [round(v or 0, 1) for v in values],
        "easy_pct": round(sum(percentages[:2]), 1) if total else None,
    }


def _sleep_recovery_chart(day: date, days: int) -> dict[str, Any]:
    from_date = (day - timedelta(days=days - 1)).isoformat()
    init_db()
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT d.date,
                   COALESCE(s.sleep_score, d.sleep_score) as sleep_score,
                   ROUND(COALESCE(s.main_sleep_min, d.sleep_total_min) / 60.0, 2) as sleep_hours,
                   h.hrv_avg_ms,
                   r.resting_hr,
                   st.stress_avg
            FROM coros_daily_health d
            LEFT JOIN coros_sleep s ON s.date=d.date
            LEFT JOIN coros_hrv h ON h.date=d.date
            LEFT JOIN coros_heart_rate_daily r ON r.date=d.date
            LEFT JOIN coros_stress_daily st ON st.date=d.date
            WHERE d.date >= ? AND d.date <= ?
            ORDER BY d.date
            """,
            (from_date, day.isoformat()),
        ).fetchall()
        data = [dict(row) for row in rows]
    finally:
        conn.close()

    return {
        "labels": [row["date"] for row in data],
        "sleep_score": [row.get("sleep_score") for row in data],
        "sleep_hours": [row.get("sleep_hours") for row in data],
        "hrv": [row.get("hrv_avg_ms") for row in data],
        "resting_hr": [row.get("resting_hr") for row in data],
        "stress": [row.get("stress_avg") for row in data],
    }


def _pain_load_chart(day: date, days: int) -> dict[str, Any]:
    from_date = (day - timedelta(days=days - 1)).isoformat()
    init_db()
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT c.date,
                   MAX(COALESCE(c.pain_knee, 0), COALESCE(c.pain_back, 0), COALESCE(c.soreness_level, 0)) as pain,
                   COALESCE(l.daily_tss, 0) as tss,
                   COALESCE(l.acwr, 0) as acwr
            FROM athlete_checkins c
            LEFT JOIN daily_load l ON l.date=c.date
            WHERE c.date >= ? AND c.date <= ?
            ORDER BY c.date
            """,
            (from_date, day.isoformat()),
        ).fetchall()
        data = [dict(row) for row in rows]
    finally:
        conn.close()
    return {
        "points": [
            {
                "x": _round(row.get("tss")) or 0,
                "y": row.get("pain") or 0,
                "date": row.get("date"),
                "acwr": _round(row.get("acwr")),
            }
            for row in data
        ],
        "labels": [row.get("date") for row in data],
    }


def _nutrition_timeline_chart() -> dict[str, Any]:
    return {
        "labels": ["训练前", "训练中", "训练后", "睡前"],
        "items": [
            {"phase": "训练前", "focus": "碳水 + 水", "window": "2-3h / 15min"},
            {"phase": "训练中", "focus": "水盐 + 碳水演练", "window": ">75min"},
            {"phase": "训练后", "focus": "碳水 + 蛋白 + 复盘", "window": "0-2h"},
            {"phase": "睡前", "focus": "睡眠恢复", "window": "固定作息"},
        ],
    }


def _risk_matrix(
    features: dict[str, Any],
    checkin: dict[str, Any],
    athlete: dict[str, Any],
    plan: dict | None,
    load_rows: list[dict],
) -> list[dict[str, Any]]:
    latest_load = load_rows[-1] if load_rows else {}
    pain_score = max(
        checkin.get("pain_knee") or 0,
        checkin.get("pain_back") or 0,
        checkin.get("soreness_level") or 0,
    ) if checkin else None
    load_risk = features.get("load_risk", "unknown")
    pain_risk = features.get("pain_risk", "unknown")
    injury_risk = features.get("injury_risk", "unknown")
    sleep_score = features.get("sleep_score")
    nutrition_level = "unknown"
    if checkin:
        nutrition_level = "low"
        if (checkin.get("hydration_ml") is not None and checkin.get("hydration_ml") < 800) or (
            sleep_score is not None and sleep_score < 65
        ):
            nutrition_level = "moderate"
        if sleep_score is not None and sleep_score < 45:
            nutrition_level = "high"

    return [
        {
            "domain": "负荷风险",
            "level": load_risk,
            "signal": _format_load_signal(latest_load),
            "rule": "ACWR>1.3 或 TSB<-20 时降载；ACWR>=1.5 或 TSB<=-30 时阻断强度。",
            "action": "调整今日训练量和强度，避免在高疲劳日叠加强刺激。",
        },
        {
            "domain": "疼痛风险",
            "level": pain_risk,
            "signal": "今日最大疼痛/酸痛 " + ("-" if pain_score is None else str(pain_score)),
            "rule": "疼痛>=4/10 进入降载，疼痛>=7/10 或刺痛/肿胀/跛行进入高风险。",
            "action": "训练中疼痛上升、步态改变或局部肿胀时立即停止。",
        },
        {
            "domain": "康复风险",
            "level": injury_risk,
            "signal": athlete.get("current_injury") or athlete.get("injury_history") or "未记录伤病史",
            "rule": "膝关节术后返跑按参与、专项、表现逐级推进，不用单次感觉良好替代标准。",
            "action": "保留低冲击力量、髋膝踝稳定和跑后 24h 反应记录。",
        },
        {
            "domain": "营养恢复",
            "level": nutrition_level,
            "signal": _nutrition_signal(checkin, sleep_score),
            "rule": "长距离和多日赛补给需要训练中演练；低能量可用性只做风险提示不诊断。",
            "action": "补充水盐、碳水和睡眠策略，避免用咖啡因掩盖疲劳。",
        },
    ]


def _nutrition_context(checkin: dict[str, Any], features: dict[str, Any], risk_matrix: list[dict], plan: dict | None) -> dict:
    hydration = checkin.get("hydration_ml") if checkin else None
    caffeine = checkin.get("caffeine_mg") if checkin else None
    sleep_score = features.get("sleep_score")
    workout_type = plan.get("workout_type") if plan else ""
    long_or_hard = workout_type in {"Long Run", "Tempo", "Threshold", "Interval"}
    risk = next((item for item in risk_matrix if item["domain"] == "营养恢复"), {})
    return {
        "level": risk.get("level", "unknown"),
        "hydration_ml": hydration,
        "caffeine_mg": caffeine,
        "sleep_score": sleep_score,
        "long_or_hard": long_or_hard,
        "notes": checkin.get("nutrition_notes") if checkin else "",
        "recommendations": _nutrition_recommendations(hydration, caffeine, sleep_score, long_or_hard),
        "reds_flags": _reds_screen(checkin, features),
    }


def _narrative(
    context: dict[str, Any],
    risk_matrix: list[dict],
    quality: dict,
    nutrition: dict,
    load_rows: list[dict],
    weekly_rows: list[dict],
) -> dict[str, Any]:
    rec = context["recommendation"]
    features = context["features"]
    plan = context.get("plan")
    trend = _trend_judgement(load_rows, weekly_rows)
    stop_conditions = _stop_conditions(rec.get("risk_level"), risk_matrix)
    actions = [
        rec.get("recommended_action", ""),
        "训练后记录膝盖、后背、疲劳和补给反应。",
        "若任何红旗信号出现，取消强度并转为低冲击恢复。",
    ]
    actions.extend(nutrition.get("recommendations", [])[:2])
    return {
        "conclusion": {
            "title": rec.get("title"),
            "action": rec.get("recommended_action"),
            "workout_type": rec.get("workout_type"),
            "planned": plan.get("workout_type") if plan else "无课表",
            "stop_conditions": stop_conditions,
        },
        "key_reasons": _key_reasons(features, risk_matrix, quality),
        "trend_judgement": trend,
        "risk_explanation": risk_matrix,
        "actions": [item for item in actions if item],
        "evidence_chain": [
            "输入版本：" + str(features.get("input_version_hash") or "-"),
            "数据置信度：" + str(quality["confidence"]) + "/100",
            "建议审计：专家投票、输入依据、证据引用均保存在 coach_recommendations。",
        ],
    }


def _evidence_matrix(retriever: CuratedEvidenceRetriever) -> dict[str, Any]:
    retriever.ensure_seeded()
    queries = {
        "运动训练学": "exercise prescription load ACWR endurance",
        "运动康复与返场": "return to sport pain rehabilitation injury",
        "运动营养学": "ultramarathon nutrition carbohydrate hydration REDs caffeine",
        "力量与灵活性": "resistance training strength neuromotor flexibility",
        "数据质量与可解释 AI": "FIT COROS MCP evidence API",
    }
    return {
        domain: [to_plain(item) for item in retriever.search(query, limit=4)]
        for domain, query in queries.items()
    }


def _recommendation_audit(recommendation: dict, features: dict, quality: dict) -> dict[str, Any]:
    return {
        "recommendation_id": recommendation.get("id"),
        "status": recommendation.get("status"),
        "risk_level": recommendation.get("risk_level"),
        "needs_confirmation": recommendation.get("needs_confirmation"),
        "input_version_hash": features.get("input_version_hash"),
        "confidence": quality.get("confidence"),
        "input_evidence": recommendation.get("input_evidence", []),
        "expert_votes": recommendation.get("expert_votes", []),
        "evidence_refs": recommendation.get("evidence_refs", []),
    }


def _raw_ingest_summary() -> dict[str, Any]:
    init_db()
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT source, COUNT(*) as count, MAX(captured_at) as latest
            FROM raw_ingest_events
            GROUP BY source ORDER BY count DESC
            """
        ).fetchall()
        return {"sources": [dict(row) for row in rows]}
    finally:
        conn.close()


def _fit_library_summary() -> dict[str, Any]:
    files = []
    for directory in (config.COROS_FIT_DIR, config.EXTRA_FIT_DIR):
        if directory.exists():
            files.extend(path for path in directory.iterdir() if path.is_file() and path.suffix.lower() == ".fit")
    return {
        "configured_dirs": [str(config.COROS_FIT_DIR), str(config.EXTRA_FIT_DIR)],
        "file_count": len({str(path.resolve()) for path in files}),
        "latest_files": [path.name for path in sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)[:8]],
    }


def _performance_summary(charts: dict, recent_sessions: list[dict]) -> dict[str, Any]:
    pmc = charts["pmc"]
    latest = {
        "ctl": _last(pmc["ctl"]),
        "atl": _last(pmc["atl"]),
        "tsb": _last(pmc["tsb"]),
        "acwr": _last(pmc["acwr"]),
    }
    return {
        "latest": latest,
        "zone_easy_pct": charts["zones"].get("easy_pct"),
        "recent_key_sessions": [
            row for row in recent_sessions if row.get("sport") == "running" and row.get("distance_km")
        ][:6],
    }


def _rehab_summary(context: dict[str, Any]) -> dict[str, Any]:
    athlete = context["athlete"]
    risk_matrix = context["risk_matrix"]
    return {
        "injury_history": athlete.get("injury_history", ""),
        "current_injury": athlete.get("current_injury", ""),
        "status": next((row for row in risk_matrix if row["domain"] == "康复风险"), {}),
        "progression": [
            {"stage": "参与", "criterion": "疼痛<=3/10，跑后 24h 无升级", "action": "走跑、轻松跑、低冲击交叉训练"},
            {"stage": "专项", "criterion": "连续 2 周低风险，睡眠/HRV 稳定", "action": "加入节奏和长距离但保留恢复日"},
            {"stage": "表现", "criterion": "负荷稳定且关键课后无异常反应", "action": "再推进比赛配速和连续日耐受"},
        ],
        "red_flags": ["刺痛/肿胀/跛行", "疼痛逐次升级", "夜间痛或静息痛", "胸痛、晕厥或异常心悸"],
    }


def _nutrition_plan(context: dict[str, Any]) -> dict[str, Any]:
    nutrition = context["nutrition"]
    return {
        "today": nutrition,
        "race_rehearsal": [
            {"scenario": "45-60 分钟轻松跑", "focus": "跑后补水和常规正餐，记录胃肠反应"},
            {"scenario": "75-120 分钟长距离", "focus": "训练中演练碳水、水盐和携带方式"},
            {"scenario": "连续多日模拟", "focus": "每日恢复餐、睡眠、晨间体重和疲劳记录"},
        ],
        "caffeine_guardrails": [
            "睡眠不足时不把咖啡因当作训练许可",
            "关键训练前记录剂量和主观反应",
            "下午后谨慎使用，避免干扰夜间恢复",
        ],
    }


def _recent_recommendations(limit: int) -> list[dict[str, Any]]:
    return SQLiteTrainingRepository().list_recommendations(limit=limit)


def _model_card(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": "Professional Agentic Coach v1",
        "policy": "康复保守优先；AI 不做医疗诊断。",
        "inputs": ["FIT 文件", "COROS MCP", "主观晨检", "训练课表", "athlete_config.json", "精选证据库"],
        "outputs": ["今日建议", "风险矩阵", "专家投票", "证据引用", "输入缺口"],
        "known_limits": context["data_quality"]["input_gaps"],
    }


def _source_score(label: str, present: bool, updated_at: str | None) -> dict[str, Any]:
    freshness = _freshness_score(updated_at) if present else 0
    return {
        "label": label,
        "present": present,
        "updated_at": updated_at,
        "freshness": freshness,
        "status": "ready" if present and freshness >= 50 else ("stale" if present else "missing"),
    }


def _freshness_score(value: str | None) -> int:
    parsed = _parse_any_date(value)
    if parsed is None:
        return 40 if value else 0
    age = max((datetime.now().date() - parsed.date()).days, 0)
    if age <= 1:
        return 100
    if age <= 7:
        return 80
    if age <= 28:
        return 55
    if age <= 90:
        return 35
    return 15


def _quality_level(score: int) -> str:
    if score >= 85:
        return "high"
    if score >= 65:
        return "medium"
    return "low"


def _format_load_signal(load: dict[str, Any]) -> str:
    if not load:
        return "无负荷曲线"
    return (
        f"CTL={load.get('ctl') or '-'}, ATL={load.get('atl') or '-'}, "
        f"TSB={load.get('tsb') or '-'}, ACWR={load.get('acwr') or '-'}"
    )


def _nutrition_signal(checkin: dict[str, Any], sleep_score: int | None) -> str:
    if not checkin:
        return "未填写今日饮水/咖啡因/饮食备注"
    return (
        f"饮水 {checkin.get('hydration_ml') if checkin.get('hydration_ml') is not None else '-'} ml，"
        f"咖啡因 {checkin.get('caffeine_mg') if checkin.get('caffeine_mg') is not None else '-'} mg，"
        f"睡眠评分 {sleep_score if sleep_score is not None else '-'}"
    )


def _nutrition_recommendations(hydration, caffeine, sleep_score, long_or_hard: bool) -> list[str]:
    items = []
    if hydration is None:
        items.append("今天补录饮水量，后续才能判断补水习惯。")
    elif hydration < 800:
        items.append("今日饮水偏低，训练前先补水，长距离加入电解质演练。")
    if sleep_score is not None and sleep_score < 65:
        items.append("睡眠不足时降低强度，不用咖啡因掩盖恢复不足。")
    if caffeine is not None and caffeine > 300:
        items.append("咖啡因摄入偏高，关注心率、胃肠和夜间睡眠。")
    if long_or_hard:
        items.append("今天若执行长距离/强度课，需要明确训练前、训练中、训练后补给窗口。")
    if not items:
        items.append("维持跑后补水、碳水和蛋白恢复，并记录胃肠耐受。")
    return items


def _reds_screen(checkin: dict[str, Any], features: dict[str, Any]) -> list[str]:
    flags = []
    if features.get("sleep_score") is not None and features["sleep_score"] < 55:
        flags.append("持续睡眠差可能提示恢复和能量可用性风险")
    if checkin and checkin.get("nutrition_notes") and any(
        word in checkin["nutrition_notes"] for word in ("没吃", "空腹", "节食", "只喝咖啡")
    ):
        flags.append("饮食备注提示训练前能量摄入可能不足")
    return flags


def _trend_judgement(load_rows: list[dict], weekly_rows: list[dict]) -> dict[str, Any]:
    recent_7 = load_rows[-7:]
    recent_28 = load_rows[-28:]
    tss_7 = sum(row.get("daily_tss") or 0 for row in recent_7)
    tss_28_avg = sum(row.get("daily_tss") or 0 for row in recent_28) / 4 if recent_28 else 0
    latest = load_rows[-1] if load_rows else {}
    if not latest:
        message = "缺少负荷趋势，今日建议主要依据主观反馈和保守默认规则。"
    elif latest.get("tsb") is not None and latest["tsb"] < -20:
        message = "TSB 显示疲劳累积，趋势不支持追加高强度。"
    elif latest.get("acwr") is not None and latest["acwr"] > 1.3:
        message = "ACWR 高于理想区间，近期加量需要谨慎。"
    elif tss_7 and tss_28_avg and tss_7 < tss_28_avg * 0.7:
        message = "近 7 天负荷低于近 28 天均值，适合低强度重启，不宜突然强刺激。"
    else:
        message = "近期负荷没有明显红旗，可在低风险条件下执行计划。"
    return {
        "message": message,
        "tss_7": round(tss_7, 1),
        "weekly_tss_baseline": round(tss_28_avg, 1),
        "latest_status": latest.get("training_status") or "Unknown",
        "weeks_available": len(weekly_rows),
    }


def _key_reasons(features: dict[str, Any], risk_matrix: list[dict], quality: dict) -> list[str]:
    reasons = [
        f"Readiness {features.get('readiness_score')}/100，恢复 {features.get('recovery_score')}/100。",
        f"数据置信度 {quality.get('confidence')}/100，质量等级 {quality.get('level')}.",
    ]
    for item in risk_matrix:
        reasons.append(f"{item['domain']}={item['level']}：{item['signal']}")
    return reasons


def _stop_conditions(risk_level: str | None, risk_matrix: list[dict]) -> list[str]:
    items = ["胸痛、晕厥、异常心悸时停止训练并线下评估"]
    if risk_level in {"moderate", "high"}:
        items.append("膝盖或后背疼痛上升到 4/10 以上时停止跑步")
        items.append("出现刺痛、肿胀、跛行或动作代偿时停止强度")
    if any(row["level"] == "high" for row in risk_matrix):
        items.append("任一高风险域未解除前，不执行间歇、阈值或下坡冲击")
    return items


def _one(conn, sql: str, params: tuple = ()) -> dict[str, Any]:
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else {}


def _count(conn, sql: str, params: tuple = ()) -> int:
    row = conn.execute(sql, params).fetchone()
    if row is None:
        return 0
    return int(row[0] or 0)


def _round(value: Any, digits: int = 1):
    return round(float(value), digits) if value is not None else None


def _last(values: list[Any]):
    return values[-1] if values else None


def _parse_any_date(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    for parser in (
        lambda: datetime.fromisoformat(text),
        lambda: datetime.strptime(text[:10], "%Y-%m-%d"),
    ):
        try:
            return parser()
        except (ValueError, TypeError):
            continue
    return None
