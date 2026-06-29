"""JSON API v3.0 — Chart.js数据源 + 业务API"""
from datetime import date

from fastapi import APIRouter, Body, HTTPException
from training.storage.queries import get_daily_load, get_weekly_summaries
from training.storage.db import get_conn, RUN_SPORT_PREDICATE
from training.adapters.sqlite_repositories import SQLiteTrainingRepository
from training.application.heartbeat import AgenticHeartbeatScheduler
from training.application.professional import ProfessionalDashboardService
from training.application.serializers import to_plain
from training.application.today import TodayService
from training.domain.models import SubjectiveCheckin
from training.evidence.retriever import CuratedEvidenceRetriever
from training.services.pipeline_service import run_refresh_pipeline

router = APIRouter()


@router.get("/pmc")
async def pmc_data(days: int = 90):
    """PMC曲线数据 (ATL/CTL/TSB + ACWR/Training Status)"""
    from datetime import datetime, timedelta
    from_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    data = get_daily_load(from_date=from_date)
    return {
        "dates": [d['date'] for d in data],
        "atl": [d['atl'] for d in data],
        "ctl": [d['ctl'] for d in data],
        "tsb": [d['tsb'] for d in data],
        "tss": [d['daily_tss'] for d in data],
        "acwr": [d.get('acwr') for d in data],
        "training_status": [d.get('training_status') for d in data],
    }


@router.get("/weekly-volume")
async def weekly_volume(weeks: int = 12):
    data = get_weekly_summaries(limit=weeks)
    data.reverse()
    return {
        "labels": [f"W{d['week_number']}" for d in data],
        "run_km": [d['run_distance_km'] or 0 for d in data],
        "total_km": [d['total_distance_km'] or 0 for d in data],
        "hr_tss": [d['total_hr_tss'] or 0 for d in data],
    }


@router.get("/zone-distribution")
async def zone_distribution(days: int = 14):
    from datetime import datetime, timedelta
    from_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

    conn = get_conn()
    try:
        row = conn.execute("""
            SELECT
                ROUND(SUM(h.zone1_sec), 0) as z1,
                ROUND(SUM(h.zone2_sec), 0) as z2,
                ROUND(SUM(h.zone3_sec), 0) as z3,
                ROUND(SUM(h.zone4_sec), 0) as z4,
                ROUND(SUM(h.zone5_sec), 0) as z5
            FROM sessions s
            JOIN hr_zone_splits h ON s.id = h.session_id
            WHERE (s.sport='running' OR s.sport LIKE '%Run%') AND s.start_time >= ? AND h.zone1_pct IS NOT NULL
        """, (from_date,)).fetchone()
    finally:
        conn.close()

    if not row or row['z1'] is None:
        return {"labels": [], "values": [], "colors": []}

    total = sum([row['z1'], row['z2'], row['z3'], row['z4'], row['z5']])
    if total == 0:
        return {"labels": [], "values": [], "colors": []}

    return {
        "labels": ["Z1 恢复", "Z2 有氧", "Z3 节奏", "Z4 阈值", "Z5 极量"],
        "values": [
            round(row['z1'] / total * 100, 1),
            round(row['z2'] / total * 100, 1),
            round(row['z3'] / total * 100, 1),
            round(row['z4'] / total * 100, 1),
            round(row['z5'] / total * 100, 1),
        ],
        "colors": ["#4CAF50", "#2196F3", "#FF9800", "#f44336", "#9C27B0"],
    }


@router.get("/pace-trend")
async def pace_trend(limit: int = 20):
    conn = get_conn()
    try:
        rows = conn.execute(f"""
            SELECT DATE(start_time) as date, avg_pace_sec, distance_km, avg_hr
            FROM sessions
            WHERE {RUN_SPORT_PREDICATE} AND avg_pace_sec IS NOT NULL AND avg_pace_sec > 330
            ORDER BY start_time DESC LIMIT ?
        """, (limit,)).fetchall()
    finally:
        conn.close()

    rows = list(reversed(rows))
    return {
        "dates": [r['date'] for r in rows],
        "pace": [r['avg_pace_sec'] for r in rows],
        "hr": [r['avg_hr'] for r in rows],
        "distance": [r['distance_km'] for r in rows],
    }


@router.get("/vo2max-trend")
async def vo2max_trend(limit: int = 30):
    """VO2max趋势数据"""
    conn = get_conn()
    try:
        rows = conn.execute(f"""
            SELECT DATE(start_time) as date, vo2max
            FROM sessions
            WHERE {RUN_SPORT_PREDICATE} AND vo2max IS NOT NULL
            ORDER BY start_time DESC LIMIT ?
        """, (limit,)).fetchall()
    finally:
        conn.close()

    rows = list(reversed(rows))
    return {
        "dates": [r['date'] for r in rows],
        "vo2max": [r['vo2max'] for r in rows],
    }


@router.get("/comparison")
async def comparison_api(days: int = 30):
    """环比分析API"""
    from training.services.comparison_service import compare_periods
    return compare_periods(days=days)


@router.get("/session/{session_id}/comparison")
async def session_comparison(session_id: int):
    """单次训练历史对比API"""
    from training.services.session_service import get_session_detail
    from fastapi import HTTPException
    data = get_session_detail(session_id)
    if not data:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"comparison": data.get('comparison')}


@router.post("/analyze/macro")
def trigger_macro_analysis(days: int = 30):
    from training.ai_coach.coach import macro_review
    result = macro_review(days=days)
    if result.startswith("[错误]"):
        return {"success": False, "error": result}
    return {"success": True, "preview": result[:200] + "..."}


@router.post("/analyze/session/{session_id}")
def trigger_session_analysis(session_id: int):
    from training.ai_coach.coach import session_review
    result = session_review(session_id)
    if result.startswith("[错误]"):
        return {"success": False, "error": result}
    return {"success": True, "preview": result[:200] + "..."}


@router.post("/pipeline")
def run_pipeline():
    """一键全流程: 导入→分析→专业指标。访问控制由Web认证中间件统一处理。"""
    results = run_refresh_pipeline(sync_coros=True, coros_days=14)
    return {"success": True, "steps": results}


@router.get("/summary")
async def summary():
    from training.services.dashboard_service import get_summary_data
    return get_summary_data()


@router.get("/coros/overview")
async def coros_overview():
    from training.coros.storage import get_coros_overview
    from training.services.coros_service import get_coros_dashboard_data
    return get_coros_dashboard_data(get_coros_overview())


@router.post("/coros/sync")
def coros_sync(days: int = 14):
    from training.coros.sync import CorosSyncService
    return CorosSyncService().sync(days=days)


@router.get("/v1/today")
def today_api(refresh: bool = False, phase: str = "morning"):
    return TodayService().get_today(refresh=refresh, phase=phase)


@router.get("/v1/pro/today")
def professional_today_api(refresh: bool = False, phase: str = "morning"):
    return ProfessionalDashboardService().get_today_decision(refresh=refresh, phase=phase)


@router.get("/v1/pro/data-center")
def professional_data_center_api():
    return ProfessionalDashboardService().get_data_center()


@router.get("/v1/pro/performance")
def professional_performance_api():
    return ProfessionalDashboardService().get_performance()


@router.get("/v1/pro/rehab")
def professional_rehab_api():
    return ProfessionalDashboardService().get_rehab()


@router.get("/v1/pro/nutrition")
def professional_nutrition_api():
    return ProfessionalDashboardService().get_nutrition()


@router.get("/v1/pro/evidence-model")
def professional_evidence_model_api():
    return ProfessionalDashboardService().get_evidence_model()


@router.get("/v1/checkins")
def get_checkin(date_str: str | None = None, phase: str = "morning"):
    day = _parse_date(date_str)
    checkin = SQLiteTrainingRepository().get_checkin(day, phase)
    return {"date": day.isoformat(), "phase": phase, "checkin": to_plain(checkin)}


@router.post("/v1/checkins")
def post_checkin(payload: dict = Body(...)):
    day = _parse_date(payload.get("date"))
    phase = payload.get("phase") or "morning"
    checkin = SubjectiveCheckin(
        date=day.isoformat(),
        phase=phase,
        sleep_hours=_float_or_none(payload.get("sleep_hours")),
        sleep_quality=_int_or_none(payload.get("sleep_quality")),
        soreness_level=_int_or_none(payload.get("soreness_level")),
        fatigue_level=_int_or_none(payload.get("fatigue_level")),
        mood=_int_or_none(payload.get("mood")),
        injury_notes=payload.get("injury_notes") or "",
        body_weight_kg=_float_or_none(payload.get("body_weight_kg")),
        pain_knee=_int_or_none(payload.get("pain_knee")),
        pain_back=_int_or_none(payload.get("pain_back")),
        hydration_ml=_int_or_none(payload.get("hydration_ml")),
        caffeine_mg=_int_or_none(payload.get("caffeine_mg")),
        nutrition_notes=payload.get("nutrition_notes") or "",
    )
    saved = SQLiteTrainingRepository().upsert_checkin(checkin)
    rec = AgenticHeartbeatScheduler().run(phase=phase, day=day)
    return {"success": True, "checkin": to_plain(saved), "recommendation": to_plain(rec)}


@router.post("/v1/sync/run")
def sync_run(payload: dict = Body(default={})):
    coros_days = int(payload.get("coros_days", 14))
    sync_coros = bool(payload.get("sync_coros", True))
    phase = payload.get("phase") or "morning"
    results = run_refresh_pipeline(sync_coros=sync_coros, coros_days=coros_days)
    rec = AgenticHeartbeatScheduler().run(phase=phase)
    return {"success": True, "steps": results, "recommendation": to_plain(rec)}


@router.get("/v1/coach/recommendations")
def list_coach_recommendations(limit: int = 20):
    return {"items": SQLiteTrainingRepository().list_recommendations(limit=limit)}


@router.post("/v1/coach/recommendations")
def run_coach_recommendation(payload: dict = Body(default={})):
    phase = payload.get("phase") or "morning"
    day = _parse_date(payload.get("date"))
    rec = AgenticHeartbeatScheduler().run(phase=phase, day=day)
    return {"success": True, "recommendation": to_plain(rec)}


@router.post("/v1/plan/confirm")
def confirm_plan_recommendation(payload: dict = Body(...)):
    recommendation_id = payload.get("recommendation_id")
    decision = payload.get("decision")
    if not recommendation_id or decision not in {"accept", "reject"}:
        raise HTTPException(status_code=400, detail="recommendation_id and decision=accept|reject are required")
    ok = SQLiteTrainingRepository().confirm_recommendation(int(recommendation_id), decision)
    if not ok:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    return {"success": True, "recommendation_id": int(recommendation_id), "decision": decision}


@router.get("/v1/evidence/search")
def evidence_search(q: str = "", limit: int = 5):
    results = CuratedEvidenceRetriever().search(q, limit=limit)
    return {"query": q, "items": to_plain(results)}


def _parse_date(value: str | None) -> date:
    if not value:
        return date.today()
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="date must use YYYY-MM-DD") from exc


def _int_or_none(value):
    if value in (None, ""):
        return None
    return int(value)


def _float_or_none(value):
    if value in (None, ""):
        return None
    return float(value)
