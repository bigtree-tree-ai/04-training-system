"""Operational refresh pipeline shared by web API and CLI."""
from __future__ import annotations


def run_refresh_pipeline(sync_coros: bool = True, coros_days: int = 14) -> list[str]:
    results: list[str] = []

    if sync_coros:
        try:
            from training.coros.sync import CorosSyncService

            coros = CorosSyncService().sync(days=coros_days)
            results.append(f"COROS同步完成: {sum(coros['persisted'].values())}项")
        except Exception as e:
            results.append(f"COROS同步跳过/失败: {e}")

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

    return results
