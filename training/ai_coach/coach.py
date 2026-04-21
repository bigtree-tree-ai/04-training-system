"""AI教练 — 调用Claude API进行训练分析"""
import os
import sys
from datetime import datetime
from pathlib import Path

from training.storage.db import init_db, get_conn
from training.ai_coach.prompt_builder import build_athlete_profile, build_macro_context, build_session_context

TEMPLATES_DIR = Path(__file__).parent / "templates"


def load_template(name: str) -> str:
    return (TEMPLATES_DIR / name).read_text(encoding='utf-8')


def call_claude(prompt: str, max_tokens: int = 2000) -> str:
    """调用Claude API（支持标准API和代理模式）"""
    try:
        import anthropic
    except ImportError:
        return "[错误] anthropic库未安装，请运行: pip install anthropic"

    api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")
    base_url = os.getenv("ANTHROPIC_BASE_URL")
    if not api_key:
        return "[错误] 未设置ANTHROPIC_API_KEY或ANTHROPIC_AUTH_TOKEN环境变量"

    kwargs = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url

    model = os.getenv("ANTHROPIC_DEFAULT_SONNET_MODEL", "claude-sonnet-4-20250514")

    client = anthropic.Anthropic(**kwargs)
    try:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text
    except Exception as e:
        return f"[错误] API调用失败: {e}"


def macro_review(days: int = 30, save: bool = True) -> str:
    """宏观训练回顾"""
    init_db()

    template = load_template("macro_review.txt")
    profile = build_athlete_profile()
    context = build_macro_context(days=days)

    from training import config
    race_date = datetime.strptime(config.GOBI_RACE_DATE, '%Y-%m-%d')
    days_to_race = (race_date.date() - datetime.now().date()).days

    prompt = template.format(
        athlete_profile=profile,
        macro_context=context,
        days_to_race=days_to_race,
    )

    print(f"正在分析最近{days}天训练数据...", file=sys.stderr)
    result = call_claude(prompt)

    if save and not result.startswith("[错误]"):
        conn = get_conn()
        conn.execute("""
            INSERT INTO ai_reports (report_type, reference_id, reference_date, model_used, ai_response)
            VALUES (?, ?, DATE('now'), ?, ?)
        """, (f'macro_{days}d', f'last_{days}_days', os.getenv("ANTHROPIC_DEFAULT_SONNET_MODEL", "claude-sonnet-4-20250514"), result))
        conn.commit()
        conn.close()
        print("报告已保存到ai_reports表", file=sys.stderr)

    return result


def session_review(session_id: int, save: bool = True) -> str:
    """单次训练点评"""
    init_db()

    template = load_template("session_review.txt")
    profile = build_athlete_profile()
    context = build_session_context(session_id)

    if not context:
        return f"[错误] 未找到session_id={session_id}"

    prompt = template.format(
        athlete_profile=profile,
        session_context=context,
    )

    print(f"正在分析训练#{session_id}...", file=sys.stderr)
    result = call_claude(prompt, max_tokens=800)

    if save and not result.startswith("[错误]"):
        from training.storage.writers import update_session_metrics
        update_session_metrics(session_id, {
            'ai_summary': result,
            'ai_analyzed_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        })
        print("点评已保存到session", file=sys.stderr)

    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法:")
        print("  python3 -m training.ai_coach.coach macro [days]")
        print("  python3 -m training.ai_coach.coach session <id>")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == 'macro':
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 30
        print(macro_review(days=days))
    elif cmd == 'session':
        sid = int(sys.argv[2])
        print(session_review(sid))
