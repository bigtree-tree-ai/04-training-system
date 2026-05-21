"""COROS MCP daily synchronization service."""
from __future__ import annotations

from datetime import date, timedelta

from training.coros.client import CorosMcpClient
from training.coros.parsers import (
    extract_tool_text,
    parse_avg_heart_rate,
    parse_daily_health,
    parse_devices,
    parse_fitness,
    parse_hrv,
    parse_recovery,
    parse_resting_heart_rate,
    parse_sleep,
    parse_stress,
    parse_training_load,
    parse_training_schedule,
    parse_user_info,
)
from training.coros import storage
from training.storage.writers import store_raw_ingest_event


class CorosSyncService:
    def __init__(self, client=None, timezone: str = "Asia/Shanghai"):
        self.client = client
        self.timezone = timezone

    def sync(self, days: int = 14) -> dict:
        run_id = storage.start_sync_run(days)
        tool_results: dict[str, str] = {}
        persisted = {
            "recovery": 0,
            "fitness": 0,
            "training_load": 0,
            "daily_health": 0,
            "sleep": 0,
            "hrv": 0,
            "resting_hr": 0,
            "avg_hr": 0,
            "stress": 0,
            "schedule": 0,
            "devices": 0,
            "profile": 0,
        }

        try:
            if self.client is None:
                self.client = CorosMcpClient()

            today = date.today()
            start_date = (today - timedelta(days=days - 1)).strftime("%Y%m%d")
            end_date = today.strftime("%Y%m%d")
            schedule_end = (today + timedelta(days=6)).strftime("%Y%m%d")

            persisted["recovery"] = self._call_parse_store(
                "queryRecoveryStatus", {}, parse_recovery, storage.upsert_recovery, tool_results
            )
            persisted["fitness"] = self._call_parse_store(
                "queryFitnessAssessmentOverview", {}, parse_fitness, storage.upsert_fitness, tool_results
            )
            persisted["training_load"] = self._call_parse_store(
                "queryTrainingLoadAssessment",
                {"days": max(days, 28)},
                parse_training_load,
                storage.upsert_training_load,
                tool_results,
            )
            persisted["daily_health"] = self._call_parse_store(
                "queryDailyHealthData",
                {"days": days, "timezone": self.timezone},
                parse_daily_health,
                storage.upsert_daily_health,
                tool_results,
            )
            persisted["sleep"] = self._call_parse_store(
                "querySleepData",
                {"startDate": start_date, "endDate": end_date, "days": days, "timezone": self.timezone},
                parse_sleep,
                storage.upsert_sleep,
                tool_results,
            )
            persisted["hrv"] = self._call_parse_store(
                "queryHrvAssessment",
                {"days": days, "timezone": self.timezone},
                parse_hrv,
                storage.upsert_hrv,
                tool_results,
            )
            persisted["resting_hr"] = self._call_parse_store(
                "queryRestingHeartRate",
                {"days": days, "timezone": self.timezone},
                parse_resting_heart_rate,
                storage.upsert_resting_hr,
                tool_results,
            )
            persisted["avg_hr"] = self._call_parse_store(
                "queryAvgHeartRate",
                {"days": days, "timezone": self.timezone},
                parse_avg_heart_rate,
                storage.upsert_avg_hr,
                tool_results,
            )
            persisted["stress"] = self._call_parse_store(
                "queryStressLevel",
                {"days": days, "timezone": self.timezone},
                parse_stress,
                storage.upsert_stress,
                tool_results,
            )
            persisted["schedule"] = self._call_parse_store(
                "queryTrainingSchedule",
                {"startDate": today.strftime("%Y%m%d"), "endDate": schedule_end, "timezone": self.timezone},
                parse_training_schedule,
                storage.upsert_training_schedule,
                tool_results,
            )
            persisted["devices"] = self._call_parse_store(
                "queryDevices", {}, parse_devices, storage.upsert_devices, tool_results
            )
            profile = self._call("queryUserInfo", {}, tool_results)
            storage.upsert_profile(parse_user_info(profile))
            persisted["profile"] = 1

            storage.finish_sync_run(run_id, "success", "COROS MCP sync completed", tool_results)
            return {"success": True, "run_id": run_id, "persisted": persisted, "tools": tool_results}
        except Exception as exc:
            storage.finish_sync_run(run_id, "failed", str(exc), tool_results)
            raise

    def _call_parse_store(self, tool_name, arguments, parser, writer, tool_results) -> int:
        text = self._call(tool_name, arguments, tool_results)
        parsed = parser(text)
        return writer(parsed)

    def _call(self, tool_name: str, arguments: dict, tool_results: dict[str, str]) -> str:
        result = self.client.call_tool(tool_name, arguments)
        text = extract_tool_text(result)
        store_raw_ingest_event(
            source="coros_mcp",
            external_id=tool_name,
            payload={
                "tool_name": tool_name,
                "arguments": arguments,
                "text": text,
                "is_error": bool(isinstance(result, dict) and result.get("isError")),
            },
            status="error" if isinstance(result, dict) and result.get("isError") else "stored",
        )
        tool_results[tool_name] = "ok"
        if isinstance(result, dict) and result.get("isError"):
            tool_results[tool_name] = "error"
            raise RuntimeError(f"{tool_name} returned MCP error: {text}")
        if "Sorry, an error occurred" in text:
            tool_results[tool_name] = "error"
            raise RuntimeError(f"{tool_name} failed: {text}")
        return text
