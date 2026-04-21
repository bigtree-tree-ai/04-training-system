"""JSON API v3.0 — Chart.js数据源 + 业务API"""
from fastapi import APIRouter
from training.storage.queries import get_daily_load, get_weekly_summaries
from training.storage.db import get_conn

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
            WHERE s.sport='running' AND s.start_time >= ? AND h.zone1_pct IS NOT NULL
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
        rows = conn.execute("""
            SELECT DATE(start_time) as date, avg_pace_sec, distance_km, avg_hr
            FROM sessions
            WHERE sport='running' AND avg_pace_sec IS NOT NULL AND avg_pace_sec > 330
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
        rows = conn.execute("""
            SELECT DATE(start_time) as date, vo2max
            FROM sessions
            WHERE sport='running' AND vo2max IS NOT NULL
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
    data = get_session_detail(session_id)
    if not data:
        return {"error": "Session not found"}
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
    """一键全流程: 导入→分析→专业指标"""
    results = []
    try:
        from training.data_import.batch_import import scan_and_import
        scan_and_import()
        results.append("FIT导入完成")
    except Exception as e:
        results.append(f"FIT导入失败: {e}")

    try:
        from training.analysis.session_metrics import compute_all_session_metrics
        from training.analysis.macro_metrics import compute_daily_load
        from training.analysis.weekly_summary import compute_weekly_summaries
        from training.analysis.pro_metrics import compute_all_pro_metrics
        compute_all_session_metrics()
        compute_daily_load()
        compute_weekly_summaries()
        compute_all_pro_metrics()
        results.append("分析计算完成(含专业指标)")
    except Exception as e:
        results.append(f"分析计算失败: {e}")

    try:
        from training.services.plan_service import match_plan_to_actual
        matched = match_plan_to_actual()
        results.append(f"计划匹配完成: {matched}条")
    except Exception as e:
        results.append(f"计划匹配失败: {e}")

    return {"success": True, "steps": results}


@router.get("/summary")
async def summary():
    from training.services.dashboard_service import get_summary_data
    return get_summary_data()
