"""训练分析系统 v3.0 — 统一CLI入口"""
import sys


def main():
    if len(sys.argv) < 2:
        print("训练分析系统 v3.0")
        print("用法: python3 -m training.cli <命令>")
        print()
        print("  import-csv             从CSV冷启动导入")
        print("  import-fit             批量扫描FIT文件导入")
        print("  analyze                计算所有分析指标(含专业指标)")
        print("  warnings               检查训练预警")
        print("  ai macro [days]        AI宏观训练回顾(默认30天)")
        print("  ai session <id>        AI单次训练点评")
        print("  compare [days]         30天环比分析(默认30天)")
        print("  compare-session <id>   单次训练历史对比")
        print("  plan [weeks]           生成训练计划(默认4周)")
        print("  recovery               身体恢复状态报告")
        print("  today                  查看AI教练团今日建议")
        print("  heartbeat [phase]      运行一次AI教练团心跳(默认morning)")
        print("  coros-login            授权COROS MCP并保存本地刷新凭据")
        print("  coros-sync [days]      通过COROS MCP同步健康/训练数据")
        print("  activity-sync [days] [--full]  从COROS采集训练session明细(含FIT/GPS/步态)")
        print("  coros-overview         查看COROS结构化数据概览")
        print("  coros-bridge [db]      从coros-collect采集库桥接数据进AI教练数据源")
        print("  activity-sync-collect [days] [db]  从coros-collect采集库补齐训练session(GPS/心率轨迹)")
        print("  serve                  启动Web服务")
        return

    cmd = sys.argv[1]

    if cmd == 'import-csv':
        from training.data_import.csv_importer import import_csv
        import_csv()

    elif cmd == 'import-fit':
        reparse = '--reparse-all' in sys.argv
        from training.data_import.batch_import import scan_and_import
        scan_and_import(reparse_all=reparse)

    elif cmd == 'analyze':
        from training.analysis.session_metrics import compute_all_session_metrics
        from training.analysis.macro_metrics import compute_daily_load
        from training.analysis.weekly_summary import compute_weekly_summaries
        from training.analysis.pro_metrics import compute_all_pro_metrics
        print("=== Step 1: Session指标 ===")
        compute_all_session_metrics()
        print("\n=== Step 2: 每日负荷 + PMC ===")
        compute_daily_load()
        print("\n=== Step 3: 周汇总 ===")
        compute_weekly_summaries()
        print("\n=== Step 4: 专业指标(VO2max/ACWR/Training Status) ===")
        compute_all_pro_metrics()

    elif cmd == 'warnings':
        from training.analysis.trend_detector import print_warnings
        print_warnings()

    elif cmd == 'ai':
        from training.ai_coach.coach import macro_review, session_review
        if len(sys.argv) < 3:
            print("用法: python3 -m training.cli ai macro [days] | ai session <id>")
            return
        sub = sys.argv[2]
        if sub == 'macro':
            days = int(sys.argv[3]) if len(sys.argv) > 3 else 30
            print(macro_review(days=days))
        elif sub == 'session':
            if len(sys.argv) < 4:
                print("请指定session_id")
                return
            print(session_review(int(sys.argv[3])))
        else:
            print(f"未知AI子命令: {sub}")

    elif cmd == 'compare':
        from training.services.comparison_service import compare_periods, format_comparison_report
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 30
        data = compare_periods(days=days)
        print(format_comparison_report(data))

    elif cmd == 'compare-session':
        if len(sys.argv) < 3:
            print("请指定session_id")
            return
        from training.services.session_service import get_session_detail
        session_id = int(sys.argv[2])
        data = get_session_detail(session_id)
        if not data:
            print(f"未找到session_id={session_id}")
            return
        comparison = data.get('comparison')
        if not comparison:
            print("暂无足够历史数据进行对比")
            return
        _print_session_comparison(data['session'], comparison)

    elif cmd == 'plan':
        from training.planning.generator import generate_plan
        weeks = int(sys.argv[2]) if len(sys.argv) > 2 else 4
        plan = generate_plan(weeks=weeks)
        print(plan)

    elif cmd == 'recovery':
        from training.planning.recovery import get_recovery_report
        print(get_recovery_report())

    elif cmd == 'today':
        import json
        from training.application.today import TodayService
        print(json.dumps(TodayService().get_today(), ensure_ascii=False, indent=2))

    elif cmd == 'heartbeat':
        import json
        from training.application.heartbeat import AgenticHeartbeatScheduler
        from training.application.serializers import to_plain
        phase = sys.argv[2] if len(sys.argv) > 2 else "morning"
        rec = AgenticHeartbeatScheduler().run(phase=phase)
        print(json.dumps(to_plain(rec), ensure_ascii=False, indent=2))

    elif cmd == 'coros-sync':
        from training.coros.sync import CorosSyncService
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 14
        result = CorosSyncService().sync(days=days)
        print("COROS MCP同步完成")
        for name, count in result["persisted"].items():
            print(f"  {name}: {count}")

    elif cmd == 'activity-sync':
        from training.coros.activity import ActivitySyncService
        full = '--full' in sys.argv
        days = 7
        for a in sys.argv[2:]:
            if a.isdigit():
                days = int(a)
        result = ActivitySyncService().sync(days=days, full=full, with_fit=True)
        print("COROS Activity 同步完成")
        for name, count in (result.get("persisted") or {}).items():
            print(f"  {name}: {count}")
        if result.get("failed"):
            print(f"  failed_labelIds: {len(result['failed'])}")

    elif cmd == 'coros-bridge':
        from training.coros.collect_bridge import bridge_from_collect
        collect_db = sys.argv[2] if len(sys.argv) > 2 else '/opt/coros-collect/data/coros.sqlite'
        result = bridge_from_collect(collect_db)
        print("COROS采集数据桥接完成(从coros-collect)")
        for name, count in result.items():
            print(f"  {name}: {count}")

    elif cmd == 'activity-sync-collect':
        from training.coros.activity_collect_bridge import sync_activities_from_collect
        collect_db = '/opt/coros-collect/data/coros.sqlite'
        days = 7
        for a in sys.argv[2:]:
            if a.isdigit():
                days = int(a)
            elif not a.startswith('--'):
                collect_db = a
        result = sync_activities_from_collect(collect_db, days=days)
        print("COROS Activity 采集库补齐完成(从coros-collect)")
        for name, value in result.items():
            if name == "skipped":
                print(f"  skipped: {len(value)} 条")
            else:
                print(f"  {name}: {value}")

    elif cmd == 'coros-login':
        from training.coros.oauth import login_with_browser
        result = login_with_browser()
        print(f"COROS授权完成: {result['auth_file']}")
        print(f"Refresh token: {'yes' if result['has_refresh_token'] else 'no'}")

    elif cmd == 'coros-overview':
        import json
        from training.coros.storage import get_coros_overview
        from training.services.coros_service import get_coros_dashboard_data
        print(json.dumps(get_coros_dashboard_data(get_coros_overview()), ensure_ascii=False, indent=2))

    elif cmd == 'serve':
        import uvicorn
        from training import config
        port = config.WEB_PORT
        if '--port' in sys.argv:
            idx = sys.argv.index('--port')
            port = int(sys.argv[idx + 1])
        print(f"启动Web服务: http://localhost:{port}")
        uvicorn.run("training.web.app:app", host="0.0.0.0", port=port, reload=True)

    else:
        print(f"未知命令: {cmd}")


def _print_session_comparison(session: dict, comparison: dict):
    """格式化输出单次训练对比"""
    def pace_str(sec):
        if not sec: return "N/A"
        return f"{int(sec // 60)}:{int(sec % 60):02d}"

    print("=" * 60)
    print(f"  单次训练历史对比")
    print(f"  训练: {session.get('start_time', '')[:10]} {session.get('training_type', '')}")
    print(f"  距离: {session.get('distance_km', 0):.1f}km  配速: {pace_str(session.get('avg_pace_sec'))}")
    print(f"  对比样本: {comparison['sample_count']}次同类训练")
    print("=" * 60)

    for m in comparison['metrics']:
        cur = m['current']
        avg = m['historical_avg']
        if m['unit'] == 'sec/km':
            cur = pace_str(cur)
            avg = pace_str(avg)

        arrow = '↑' if m['diff'] > 0 else ('↓' if m['diff'] < 0 else '→')
        tag = '✓进步' if m['trend'] == 'better' else ('✗退步' if m['trend'] == 'worse' else '→持平')

        print(f"\n  {m['name']}:")
        print(f"    本次: {cur} {m['unit']}  |  历史均值: {avg} {m['unit']}")
        print(f"    变化: {arrow} {m['diff_pct']:+.1f}% {tag}")
        if m.get('note'):
            print(f"    解读: {m['note']}")

    print(f"\n{'─' * 60}")
    print(f"  综合判定: {comparison['overall_text']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
