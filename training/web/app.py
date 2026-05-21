"""FastAPI Web应用 — 页面路由（v3.0 使用Service Layer）"""
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

from training import config
from training.storage.db import init_db
from training.storage.queries import get_weekly_summaries, get_ai_reports
from training.services.dashboard_service import get_dashboard_data
from training.services.session_service import get_session_detail
from training.services.plan_service import get_plan_calendar
from training.web.api import router as api_router
from training.web.auth import require_basic_auth
from training.content.interpretations import (
    interpret_ctl, interpret_tsb, interpret_acwr, interpret_vo2max,
    interpret_training_status, interpret_hr_drift, interpret_marathon_shape,
    interpret_recovery_score, interpret_zone_distribution,
    interpret_comparison_metric,
)

import os
ROOT_PATH = os.environ.get("ROOT_PATH", "")

app = FastAPI(title="训练分析系统 v3.0")


@app.middleware("http")
async def enforce_dashboard_auth(request: Request, call_next):
    auth_response = require_basic_auth(request)
    if auth_response is not None:
        return auth_response
    return await call_next(request)

templates_dir = Path(__file__).parent / "templates"
static_dir = Path(__file__).parent / "static"
templates = Jinja2Templates(directory=str(templates_dir))
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
app.include_router(api_router, prefix="/api")


def format_pace(seconds):
    if not seconds:
        return "-"
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m}:{s:02d}"


def format_duration(seconds):
    if not seconds:
        return "-"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def format_minutes(minutes):
    if minutes is None:
        return "-"
    total = int(round(minutes))
    h = total // 60
    m = total % 60
    if h > 0:
        return f"{h}h {m}min"
    return f"{m}min"


def format_race_time(seconds):
    if seconds is None:
        return "-"
    total = int(seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def format_sport(sport):
    mapping = {'running': '跑步', 'cycling': '骑行', 'training': '力量训练',
               'hiking': '徒步', 'walking': '步行'}
    return mapping.get(sport, sport or '未知')


templates.env.filters['pace'] = format_pace
templates.env.filters['duration'] = format_duration
templates.env.filters['minutes'] = format_minutes
templates.env.filters['race_time'] = format_race_time
templates.env.filters['sport_cn'] = format_sport
templates.env.globals['base'] = ROOT_PATH

# 注册专业解读文案函数为Jinja2全局函数
templates.env.globals['interpret_ctl'] = interpret_ctl
templates.env.globals['interpret_tsb'] = interpret_tsb
templates.env.globals['interpret_acwr'] = interpret_acwr
templates.env.globals['interpret_vo2max'] = interpret_vo2max
templates.env.globals['interpret_training_status'] = interpret_training_status
templates.env.globals['interpret_hr_drift'] = interpret_hr_drift
templates.env.globals['interpret_marathon_shape'] = interpret_marathon_shape
templates.env.globals['interpret_recovery_score'] = interpret_recovery_score
templates.env.globals['interpret_zone_distribution'] = interpret_zone_distribution
templates.env.globals['interpret_comparison_metric'] = interpret_comparison_metric


@app.on_event("startup")
def startup():
    init_db()


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    data = get_dashboard_data()
    return templates.TemplateResponse(request, "dashboard.html", data)


@app.get("/sessions", response_class=HTMLResponse)
async def session_list(request: Request, sport: str = None, page: int = 1):
    from training.storage.queries import get_all_sessions
    from training.storage.db import get_conn

    limit = 20
    offset = (page - 1) * limit
    sessions = get_all_sessions(sport=sport, limit=limit, offset=offset)

    conn = get_conn()
    try:
        total = conn.execute(
            "SELECT COUNT(*) as cnt FROM sessions" + (" WHERE sport=?" if sport else ""),
            (sport,) if sport else ()
        ).fetchone()['cnt']
    finally:
        conn.close()

    total_pages = (total + limit - 1) // limit

    return templates.TemplateResponse(request, "session_list.html", {
        "sessions": sessions,
        "sport": sport,
        "page": page,
        "total_pages": total_pages,
        "total": total,
    })


@app.get("/sessions/{session_id}", response_class=HTMLResponse)
async def session_detail(request: Request, session_id: int):
    data = get_session_detail(session_id)
    if data is None:
        return HTMLResponse("Session not found", status_code=404)
    return templates.TemplateResponse(request, "session_detail.html", data)


@app.get("/weekly", response_class=HTMLResponse)
async def weekly_view(request: Request):
    weeks = get_weekly_summaries(limit=15)
    return templates.TemplateResponse(request, "weekly_view.html", {"weeks": weeks})


@app.get("/ai-insights", response_class=HTMLResponse)
async def ai_insights(request: Request):
    reports = get_ai_reports(limit=20)
    return templates.TemplateResponse(request, "ai_insights.html", {"reports": reports})


@app.get("/comparison", response_class=HTMLResponse)
async def comparison_view(request: Request, days: int = 30):
    from training.services.comparison_service import compare_periods
    data = compare_periods(days=days)
    return templates.TemplateResponse(request, "comparison.html", {"data": data, "days": days})


@app.get("/plan", response_class=HTMLResponse)
async def plan_view(request: Request):
    calendar = get_plan_calendar()
    return templates.TemplateResponse(request, "plan.html", {"calendar": calendar})


@app.get("/recovery", response_class=HTMLResponse)
async def recovery_view(request: Request):
    from training.services.dashboard_service import get_dashboard_data
    data = get_dashboard_data()
    return templates.TemplateResponse(request, "recovery.html", {
        "pro": data.get('pro', {}),
        "pmc": data.get('pmc', {}),
    })


@app.get("/coros", response_class=HTMLResponse)
async def coros_view(request: Request):
    from training.coros.storage import get_coros_overview
    from training.services.coros_service import get_coros_dashboard_data
    data = get_coros_dashboard_data(get_coros_overview())
    return templates.TemplateResponse(request, "coros.html", {"coros": data})
