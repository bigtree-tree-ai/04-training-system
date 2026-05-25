"""SQLite repository for productized user flows."""
from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Any

from training.storage.db import get_conn, init_db


PROFILE_FIELDS = (
    "goal_type",
    "target_race",
    "race_date",
    "running_level",
    "weekly_availability",
    "injury_history",
    "current_injury",
    "max_hr",
    "resting_hr",
    "height_cm",
    "weight_kg",
)


class ProductRepository:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path

    def init(self):
        init_db(self.db_path)

    def save_profile(self, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        self.init()
        values = _profile_values(payload)
        onboarding_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        conn = get_conn(self.db_path)
        try:
            conn.execute(
                """
                INSERT INTO product_user_profiles (
                    user_id, goal_type, target_race, race_date, running_level,
                    weekly_availability, injury_history, current_injury, max_hr,
                    resting_hr, height_cm, weight_kg, onboarding_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    goal_type=excluded.goal_type,
                    target_race=excluded.target_race,
                    race_date=excluded.race_date,
                    running_level=excluded.running_level,
                    weekly_availability=excluded.weekly_availability,
                    injury_history=excluded.injury_history,
                    current_injury=excluded.current_injury,
                    max_hr=excluded.max_hr,
                    resting_hr=excluded.resting_hr,
                    height_cm=excluded.height_cm,
                    weight_kg=excluded.weight_kg,
                    onboarding_json=excluded.onboarding_json,
                    updated_at=datetime('now')
                """,
                (user_id, *values, onboarding_json),
            )
            conn.execute(
                """
                UPDATE product_users
                SET onboarding_completed=1,
                    accepted_terms_at=COALESCE(accepted_terms_at, datetime('now')),
                    updated_at=datetime('now')
                WHERE id=?
                """,
                (user_id,),
            )
            self.log_admin_action(user_id, "onboarding_saved", {"goal_type": payload.get("goal_type")}, conn=conn)
            conn.commit()
            return self.get_profile(user_id, conn=conn) or {}
        finally:
            conn.close()

    def get_profile(self, user_id: int, conn=None) -> dict[str, Any] | None:
        own_conn = conn is None
        conn = conn or get_conn(self.db_path)
        try:
            row = conn.execute("SELECT * FROM product_user_profiles WHERE user_id=?", (user_id,)).fetchone()
            if not row:
                return None
            data = dict(row)
            data["onboarding"] = json.loads(data.pop("onboarding_json") or "{}")
            return data
        finally:
            if own_conn:
                conn.close()

    def create_upload(
        self,
        user_id: int,
        filename: str,
        stored_path: str,
        file_hash: str,
        size_bytes: int,
        status: str = "processing",
        message: str = "",
    ) -> int:
        self.init()
        conn = get_conn(self.db_path)
        try:
            cur = conn.execute(
                """
                INSERT INTO product_fit_uploads (
                    user_id, filename, stored_path, file_hash, size_bytes, status, message
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, filename, stored_path, file_hash, size_bytes, status, message),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    def finish_upload(
        self,
        upload_id: int,
        status: str,
        message: str,
        session_id: int | None = None,
        first_report: dict[str, Any] | None = None,
    ):
        conn = get_conn(self.db_path)
        try:
            conn.execute(
                """
                UPDATE product_fit_uploads
                SET status=?, message=?, session_id=?, first_report_json=?
                WHERE id=?
                """,
                (
                    status,
                    message,
                    session_id,
                    json.dumps(first_report or {}, ensure_ascii=False, sort_keys=True, default=str),
                    upload_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_upload(self, upload_id: int, user_id: int | None = None) -> dict[str, Any] | None:
        self.init()
        conn = get_conn(self.db_path)
        try:
            if user_id is None:
                row = conn.execute("SELECT * FROM product_fit_uploads WHERE id=?", (upload_id,)).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM product_fit_uploads WHERE id=? AND user_id=?",
                    (upload_id, user_id),
                ).fetchone()
            return _upload_from_row(row) if row else None
        finally:
            conn.close()

    def list_uploads(self, user_id: int, limit: int = 10) -> list[dict[str, Any]]:
        self.init()
        conn = get_conn(self.db_path)
        try:
            rows = conn.execute(
                """
                SELECT * FROM product_fit_uploads
                WHERE user_id=?
                ORDER BY uploaded_at DESC, id DESC LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
            return [_upload_from_row(row) for row in rows]
        finally:
            conn.close()

    def list_user_sessions(self, user_id: int, limit: int = 20) -> list[dict[str, Any]]:
        self.init()
        conn = get_conn(self.db_path)
        try:
            rows = conn.execute(
                """
                SELECT id, filename, sport, start_time, duration_sec, distance_km,
                       avg_hr, max_hr, avg_pace_sec, total_ascent, total_descent,
                       training_effect, hr_tss, pace_cv, hr_drift_pct, efficiency_factor
                FROM sessions
                WHERE owner_user_id=?
                ORDER BY start_time DESC, id DESC LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def latest_session(self, user_id: int) -> dict[str, Any] | None:
        sessions = self.list_user_sessions(user_id, limit=1)
        return sessions[0] if sessions else None

    def build_simple_today(self, user: dict[str, Any]) -> dict[str, Any]:
        profile = self.get_profile(user["id"]) or {}
        sessions = self.list_user_sessions(user["id"], limit=5)
        uploads = self.list_uploads(user["id"], limit=3)
        latest = sessions[0] if sessions else None
        readiness, risk_level, reasons = _readiness_from_context(profile, latest)
        action = _today_action(profile, latest, risk_level)
        return {
            "date": date.today().isoformat(),
            "user": user,
            "profile": profile,
            "onboarding_completed": bool(user.get("onboarding_completed")),
            "has_fit": bool(sessions),
            "readiness_score": readiness,
            "risk_level": risk_level,
            "title": action["title"],
            "today_workout": action["workout"],
            "reason": action["reason"],
            "needs_confirmation": risk_level == "high",
            "next_steps": action["next_steps"],
            "risk_reasons": reasons,
            "recent_sessions": sessions,
            "recent_uploads": uploads,
            "disclaimer": "AI 教练建议不能替代医疗诊断；出现胸痛、晕厥、进行性疼痛或术后异常反应时，停止训练并线下就医/评估。",
        }

    def export_user_data(self, user: dict[str, Any]) -> dict[str, Any]:
        self.init()
        user_id = user["id"]
        conn = get_conn(self.db_path)
        try:
            export = {
                "exported_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
                "user": user,
                "profile": self.get_profile(user_id, conn=conn),
                "fit_uploads": [
                    _upload_from_row(row)
                    for row in conn.execute(
                        "SELECT * FROM product_fit_uploads WHERE user_id=? ORDER BY uploaded_at DESC",
                        (user_id,),
                    ).fetchall()
                ],
                "sessions": [
                    dict(row)
                    for row in conn.execute(
                        "SELECT * FROM sessions WHERE owner_user_id=? ORDER BY start_time DESC",
                        (user_id,),
                    ).fetchall()
                ],
                "raw_ingest_events": [
                    dict(row)
                    for row in conn.execute(
                        "SELECT * FROM raw_ingest_events WHERE owner_user_id=? ORDER BY captured_at DESC",
                        (user_id,),
                    ).fetchall()
                ],
                "notification_subscriptions": [
                    dict(row)
                    for row in conn.execute(
                        "SELECT id, endpoint, user_agent, created_at FROM product_notification_subscriptions WHERE user_id=?",
                        (user_id,),
                    ).fetchall()
                ],
                "notifications": [
                    dict(row)
                    for row in conn.execute(
                        "SELECT * FROM product_notifications WHERE user_id=? ORDER BY created_at DESC",
                        (user_id,),
                    ).fetchall()
                ],
            }
            conn.execute(
                "INSERT INTO product_data_exports (user_id, export_json) VALUES (?, ?)",
                (user_id, json.dumps(export, ensure_ascii=False, sort_keys=True, default=str)),
            )
            self.log_admin_action(user_id, "privacy_export", {"session_count": len(export["sessions"])}, conn=conn)
            conn.commit()
            return export
        finally:
            conn.close()

    def delete_user_data(self, user_id: int) -> dict[str, int]:
        self.init()
        conn = get_conn(self.db_path)
        try:
            counts: dict[str, int] = {}
            session_ids = [
                row["id"]
                for row in conn.execute("SELECT id FROM sessions WHERE owner_user_id=?", (user_id,)).fetchall()
            ]
            if session_ids:
                placeholders = ",".join("?" for _ in session_ids)
                counts["hr_zone_splits"] = conn.execute(
                    f"DELETE FROM hr_zone_splits WHERE session_id IN ({placeholders})",
                    session_ids,
                ).rowcount
                counts["laps"] = conn.execute(
                    f"DELETE FROM laps WHERE session_id IN ({placeholders})",
                    session_ids,
                ).rowcount
            else:
                counts["hr_zone_splits"] = 0
                counts["laps"] = 0
            for table in (
                "sessions",
                "raw_ingest_events",
                "athlete_checkins",
                "canonical_daily_metrics",
                "daily_features",
                "coach_recommendations",
                "heartbeat_runs",
                "product_fit_uploads",
                "product_data_exports",
                "product_notification_subscriptions",
                "product_notifications",
            ):
                counts[table] = conn.execute(f"DELETE FROM {table} WHERE owner_user_id=?" if table in {
                    "sessions",
                    "raw_ingest_events",
                    "athlete_checkins",
                    "canonical_daily_metrics",
                    "daily_features",
                    "coach_recommendations",
                    "heartbeat_runs",
                } else f"DELETE FROM {table} WHERE user_id=?", (user_id,)).rowcount
            counts["product_user_profiles"] = conn.execute(
                "DELETE FROM product_user_profiles WHERE user_id=?",
                (user_id,),
            ).rowcount
            counts["product_auth_sessions"] = conn.execute(
                "DELETE FROM product_auth_sessions WHERE user_id=?",
                (user_id,),
            ).rowcount
            counts["product_users"] = conn.execute("DELETE FROM product_users WHERE id=?", (user_id,)).rowcount
            conn.execute(
                """
                INSERT INTO product_admin_audit_log (user_id, action, details_json)
                VALUES (?, 'privacy_delete', ?)
                """,
                (None, json.dumps({"deleted_user_id": user_id, "counts": counts}, ensure_ascii=False)),
            )
            conn.commit()
            return counts
        finally:
            conn.close()

    def upsert_notification_subscription(
        self,
        user_id: int,
        endpoint: str,
        p256dh: str = "",
        auth: str = "",
        user_agent: str = "",
    ) -> dict[str, Any]:
        self.init()
        conn = get_conn(self.db_path)
        try:
            conn.execute(
                """
                INSERT INTO product_notification_subscriptions (user_id, endpoint, p256dh, auth, user_agent)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, endpoint) DO UPDATE SET
                    p256dh=excluded.p256dh,
                    auth=excluded.auth,
                    user_agent=excluded.user_agent,
                    created_at=datetime('now')
                """,
                (user_id, endpoint, p256dh, auth, user_agent),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM product_notification_subscriptions WHERE user_id=? AND endpoint=?",
                (user_id, endpoint),
            ).fetchone()
            return dict(row)
        finally:
            conn.close()

    def queue_notification(self, user_id: int, title: str, body: str, url: str = "/product/today") -> dict[str, Any]:
        self.init()
        conn = get_conn(self.db_path)
        try:
            cur = conn.execute(
                """
                INSERT INTO product_notifications (user_id, title, body, url, status)
                VALUES (?, ?, ?, ?, 'queued')
                """,
                (user_id, title, body, url),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM product_notifications WHERE id=?", (int(cur.lastrowid),)).fetchone()
            return dict(row)
        finally:
            conn.close()

    def list_users(self) -> list[dict[str, Any]]:
        self.init()
        conn = get_conn(self.db_path)
        try:
            rows = conn.execute(
                """
                SELECT u.id, u.email, u.display_name, u.role, u.status,
                       u.onboarding_completed, u.created_at,
                       COUNT(DISTINCT s.id) AS session_count,
                       COUNT(DISTINCT f.id) AS upload_count,
                       MAX(s.start_time) AS latest_session_at
                FROM product_users u
                LEFT JOIN sessions s ON s.owner_user_id=u.id
                LEFT JOIN product_fit_uploads f ON f.user_id=u.id
                GROUP BY u.id
                ORDER BY u.created_at DESC, u.id DESC
                """
            ).fetchall()
            return [
                {
                    **dict(row),
                    "onboarding_completed": bool(row["onboarding_completed"]),
                }
                for row in rows
            ]
        finally:
            conn.close()

    def log_admin_action(self, user_id: int | None, action: str, details: dict[str, Any], conn=None):
        own_conn = conn is None
        conn = conn or get_conn(self.db_path)
        try:
            conn.execute(
                """
                INSERT INTO product_admin_audit_log (user_id, action, details_json)
                VALUES (?, ?, ?)
                """,
                (user_id, action, json.dumps(details, ensure_ascii=False, sort_keys=True, default=str)),
            )
            if own_conn:
                conn.commit()
        finally:
            if own_conn:
                conn.close()


def _profile_values(payload: dict[str, Any]) -> tuple[Any, ...]:
    values = []
    for field in PROFILE_FIELDS:
        value = payload.get(field)
        if field in {"max_hr", "resting_hr"}:
            value = _int_or_none(value)
        elif field in {"height_cm", "weight_kg"}:
            value = _float_or_none(value)
        elif value is not None:
            value = str(value).strip()
        values.append(value)
    return tuple(values)


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _upload_from_row(row) -> dict[str, Any]:
    data = dict(row)
    data["first_report"] = json.loads(data.pop("first_report_json") or "{}")
    return data


def _readiness_from_context(profile: dict[str, Any], latest: dict[str, Any] | None) -> tuple[int, str, list[str]]:
    score = 72
    reasons: list[str] = []
    current_injury = (profile.get("current_injury") or "").strip()
    if _has_actionable_injury(current_injury):
        score -= 20
        reasons.append(f"当前伤痛/不适：{current_injury}")
    if latest:
        duration = latest.get("duration_sec") or 0
        distance = latest.get("distance_km") or 0
        avg_hr = latest.get("avg_hr") or 0
        if duration >= 7200 or distance >= 21:
            score -= 14
            reasons.append("最近一次训练较长，需要恢复窗口")
        if avg_hr >= 160:
            score -= 10
            reasons.append("最近一次平均心率偏高")
        days = _days_since(latest.get("start_time"))
        if days == 0:
            score -= 8
            reasons.append("今天已经有训练记录")
        elif days >= 4:
            score += 8
            reasons.append("最近训练间隔较长，适合低强度重启")
    else:
        score = 55
        reasons.append("还没有可分析的 FIT 训练记录")
    score = max(20, min(95, score))
    if score < 50:
        risk = "high"
    elif score < 70:
        risk = "moderate"
    else:
        risk = "low"
    if not reasons:
        reasons.append("近期训练负荷和伤痛输入没有明显红旗")
    return score, risk, reasons


def _today_action(profile: dict[str, Any], latest: dict[str, Any] | None, risk: str) -> dict[str, Any]:
    goal = profile.get("goal_type") or "跑步能力"
    if not latest:
        return {
            "title": "先建立你的第一份训练基线",
            "workout": "上传最近一份 FIT 文件；今天只做 20-30 分钟轻松走跑或灵活性训练。",
            "reason": "没有训练文件时，系统不能可靠判断配速、心率和恢复负荷。",
            "next_steps": ["上传 FIT", "完成身体状态输入", "等待首份报告生成"],
        }
    if risk == "high":
        return {
            "title": "今天不做强度训练",
            "workout": "休息或 20-30 分钟低强度活动；加入髋、臀、核心和膝周稳定练习。",
            "reason": "当前输入存在高风险信号，优先保护康复连续性。",
            "next_steps": ["记录疼痛 0-10 分", "避免冲刺/下坡/间歇", "必要时线下评估"],
        }
    if risk == "moderate":
        return {
            "title": "今天做可控有氧",
            "workout": "Z1-Z2 轻松跑 30-45 分钟；全程能完整说话，跑后做 10 分钟拉伸。",
            "reason": "适合维持训练连续性，但暂不叠加强刺激。",
            "next_steps": ["跑前确认疼痛低于 3/10", "跑后提交主观反馈", "睡眠不足则改步行"],
        }
    return {
        "title": f"今天可以推进{goal}",
        "workout": "Z2 轻松跑 40-55 分钟；状态好可加 4-6 组 15 秒放松加速跑。",
        "reason": "当前没有明显红旗，优先积累稳定有氧和跑姿经济性。",
        "next_steps": ["保持低强度占比", "跑后补水和碳水", "记录膝盖/后背感受"],
    }


def _days_since(start_time: str | None) -> int:
    if not start_time:
        return 99
    try:
        parsed = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.strptime(start_time[:10], "%Y-%m-%d")
        except ValueError:
            return 99
    return max(0, (date.today() - parsed.date()).days)


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
