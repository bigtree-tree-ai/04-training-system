"""FIT upload handling for product users."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from training import config
from training.analysis.session_metrics import (
    compute_efficiency_factor,
    compute_hr_drift,
    compute_hr_tss,
    compute_pace_cv,
)
from training.data_import.fit_parser import parse_fit_file
from training.product.reports import build_first_report
from training.product.repository import ProductRepository
from training.storage.writers import (
    store_raw_ingest_event,
    update_session_metrics,
    upsert_hr_zones,
    upsert_laps,
    upsert_session,
)


class ProductFitUploadService:
    def __init__(self, repository: ProductRepository | None = None):
        self.repository = repository or ProductRepository()

    def upload_fit(self, user_id: int, filename: str, content: bytes) -> dict[str, Any]:
        safe_name = _safe_filename(filename)
        _validate_upload(safe_name, content)
        file_hash = hashlib.sha256(content).hexdigest()[:16]
        stored_path = _stored_path(user_id, safe_name, file_hash)
        stored_path.parent.mkdir(parents=True, exist_ok=True)
        stored_path.write_bytes(content)

        upload_id = self.repository.create_upload(
            user_id=user_id,
            filename=safe_name,
            stored_path=str(stored_path),
            file_hash=file_hash,
            size_bytes=len(content),
        )

        parsed = parse_fit_file(str(stored_path))
        if parsed is None:
            self.repository.finish_upload(upload_id, "failed", "FIT 文件无法解析")
            raise HTTPException(status_code=422, detail="FIT file could not be parsed")

        session = dict(parsed["session"])
        original_filename = session.get("filename") or safe_name
        session["filename"] = f"user-{user_id}-{file_hash}-{original_filename}"
        store_raw_ingest_event(
            source="product_fit_upload",
            external_id=session["filename"],
            occurred_at=session.get("start_time"),
            owner_user_id=user_id,
            payload={
                "owner_user_id": user_id,
                "original_filename": safe_name,
                "stored_filename": session["filename"],
                "file_hash": file_hash,
                "session": session,
                "lap_count": len(parsed.get("laps") or []),
                "has_hr_zones": bool(parsed.get("hr_zones")),
            },
        )
        session_id = upsert_session(session, owner_user_id=user_id)
        laps = parsed.get("laps") or []
        hr_zones = parsed.get("hr_zones") or {}
        if laps:
            upsert_laps(session_id, laps)
        if hr_zones and hr_zones.get("zone1_pct") is not None:
            upsert_hr_zones(session_id, hr_zones)

        metrics = _compute_uploaded_metrics(session, laps)
        if metrics:
            update_session_metrics(session_id, metrics)
            session.update(metrics)

        profile = self.repository.get_profile(user_id) or {}
        first_report = build_first_report(session, laps, hr_zones, profile)
        self.repository.finish_upload(upload_id, "completed", "首份报告已生成", session_id, first_report)
        return {
            "upload": self.repository.get_upload(upload_id, user_id=user_id),
            "session_id": session_id,
            "first_report": first_report,
        }


def _compute_uploaded_metrics(session: dict[str, Any], laps: list[dict[str, Any]]) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    hr_tss = compute_hr_tss(session.get("avg_hr"), session.get("duration_sec"))
    pace_cv = compute_pace_cv(laps)
    hr_drift = compute_hr_drift(laps)
    ef = compute_efficiency_factor(session.get("avg_speed_mps"), session.get("avg_hr"))
    if hr_tss is not None:
        metrics["hr_tss"] = hr_tss
    if pace_cv is not None:
        metrics["pace_cv"] = pace_cv
    if hr_drift is not None:
        metrics["hr_drift_pct"] = hr_drift
    if ef is not None:
        metrics["efficiency_factor"] = ef
    return metrics


def _validate_upload(filename: str, content: bytes):
    if not filename.lower().endswith(".fit"):
        raise HTTPException(status_code=400, detail="Only .fit files are supported")
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(content) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Uploaded file is too large")


def _safe_filename(filename: str) -> str:
    raw = Path(filename or "upload.fit").name
    path = Path(raw)
    suffix = path.suffix.lower()
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", path.stem).strip("._") or "upload"
    safe_suffix = ".fit" if suffix == ".fit" else re.sub(r"[^A-Za-z0-9.]+", "", suffix)
    return f"{stem}{safe_suffix}" if safe_suffix else stem


def _stored_path(user_id: int, filename: str, file_hash: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return config.USER_UPLOAD_DIR / f"user_{user_id}" / f"{stamp}_{file_hash}_{filename}"
