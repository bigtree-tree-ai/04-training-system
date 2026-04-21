"""单次训练服务 — 训练详情+历史对比"""
from training.storage.db import get_conn, init_db
from training.storage.queries import (
    get_session_by_id, get_laps_for_session, get_hr_zones_for_session,
    get_similar_sessions,
)


def get_session_detail(session_id: int) -> dict | None:
    """获取训练详情（含对比数据）"""
    session = get_session_by_id(session_id)
    if not session:
        return None

    laps = get_laps_for_session(session_id)
    hr_zones = get_hr_zones_for_session(session_id)

    # 历史对比
    comparison = None
    if session.get('sport') == 'running' and session.get('distance_km'):
        comparison = _compare_with_history(session)

    return {
        'session': session,
        'laps': laps,
        'hr_zones': hr_zones,
        'comparison': comparison,
    }


def _compare_with_history(session: dict) -> dict | None:
    """与历史同类训练对比"""
    distance = session.get('distance_km', 0)
    if not distance or distance < 1:
        return None

    similar = get_similar_sessions(
        session_id=session['id'],
        sport='running',
        distance_range=(distance * 0.8, distance * 1.2),
        limit=10,
    )

    if len(similar) < 2:
        return None

    # 计算各维度均值
    avg_pace = _avg(similar, 'avg_pace_sec')
    avg_hr = _avg(similar, 'avg_hr')
    avg_tss = _avg(similar, 'hr_tss')
    avg_vo2 = _avg(similar, 'vo2max')

    metrics = []

    # 配速对比
    if session.get('avg_pace_sec') and avg_pace:
        diff = session['avg_pace_sec'] - avg_pace
        pct = diff / avg_pace * 100
        metrics.append({
            'name': '平均配速',
            'current': session['avg_pace_sec'],
            'historical_avg': round(avg_pace, 1),
            'diff': round(diff, 1),
            'diff_pct': round(pct, 1),
            'trend': 'better' if diff < 0 else ('worse' if diff > 0 else 'same'),
            'unit': 'sec/km',
            'note': '配速降低=更快=进步' if diff < 0 else '配速升高=更慢',
        })

    # 心率对比
    if session.get('avg_hr') and avg_hr:
        diff = session['avg_hr'] - avg_hr
        pct = diff / avg_hr * 100
        # 同配速下心率降低=有氧效率提升
        metrics.append({
            'name': '平均心率',
            'current': session['avg_hr'],
            'historical_avg': round(avg_hr, 1),
            'diff': round(diff, 1),
            'diff_pct': round(pct, 1),
            'trend': 'better' if diff < 0 else ('worse' if diff > 0 else 'same'),
            'unit': 'bpm',
            'note': '同配速下心率降低=有氧效率提升',
        })

    # hrTSS对比
    if session.get('hr_tss') and avg_tss:
        diff = session['hr_tss'] - avg_tss
        pct = diff / avg_tss * 100
        metrics.append({
            'name': '训练负荷(hrTSS)',
            'current': round(session['hr_tss'], 1),
            'historical_avg': round(avg_tss, 1),
            'diff': round(diff, 1),
            'diff_pct': round(pct, 1),
            'trend': 'neutral',
            'unit': '',
            'note': 'TSS更高=训练刺激更大',
        })

    # VO2max对比
    if session.get('vo2max') and avg_vo2:
        diff = session['vo2max'] - avg_vo2
        pct = diff / avg_vo2 * 100
        metrics.append({
            'name': 'VO2max估算',
            'current': session['vo2max'],
            'historical_avg': round(avg_vo2, 1),
            'diff': round(diff, 1),
            'diff_pct': round(pct, 1),
            'trend': 'better' if diff > 0 else ('worse' if diff < 0 else 'same'),
            'unit': 'ml/kg/min',
            'note': 'VO2max上升=有氧能力提升',
        })

    # 总体判定
    better_count = sum(1 for m in metrics if m['trend'] == 'better')
    worse_count = sum(1 for m in metrics if m['trend'] == 'worse')

    if better_count > worse_count:
        overall = 'improving'
        overall_text = '整体表现优于历史同类训练，训练效果良好'
    elif worse_count > better_count:
        overall = 'declining'
        overall_text = '整体表现低于历史水平，可能需要关注恢复和训练强度'
    else:
        overall = 'stable'
        overall_text = '整体表现与历史水平持平，训练状态稳定'

    return {
        'metrics': metrics,
        'sample_count': len(similar),
        'overall': overall,
        'overall_text': overall_text,
    }


def _avg(rows: list[dict], key: str) -> float | None:
    vals = [r[key] for r in rows if r.get(key) is not None]
    return sum(vals) / len(vals) if vals else None
