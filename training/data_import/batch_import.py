"""批量扫描并导入FIT文件"""
import sys
from pathlib import Path

from training import config
from training.storage.db import init_db
from training.storage.queries import get_imported_filenames
from training.storage.writers import upsert_session, upsert_laps, upsert_hr_zones
from training.data_import.fit_parser import parse_fit_file


def scan_and_import(reparse_all=False):
    """扫描FIT目录，导入新文件"""
    init_db()

    # 收集所有FIT文件
    fit_files = []

    # 1. 高驰导出目录
    if config.COROS_FIT_DIR.exists():
        for f in sorted(config.COROS_FIT_DIR.iterdir()):
            if f.suffix.lower() == '.fit':
                fit_files.append(str(f))

    # 2. 根目录下的单独FIT文件
    if config.EXTRA_FIT_DIR.exists():
        for f in sorted(config.EXTRA_FIT_DIR.iterdir()):
            if f.suffix.lower() == '.fit' and f.is_file():
                fit_files.append(str(f))

    print(f"发现 {len(fit_files)} 个FIT文件", file=sys.stderr)

    # 获取已导入的文件名
    if reparse_all:
        existing = set()
    else:
        existing = get_imported_filenames()
        print(f"已导入 {len(existing)} 个，跳过", file=sys.stderr)

    imported = 0
    skipped = 0
    errors = 0

    for i, fpath in enumerate(fit_files):
        fname = Path(fpath).name
        if fname in existing:
            skipped += 1
            continue

        result = parse_fit_file(fpath)
        if result is None:
            errors += 1
            continue

        # 写入数据库
        session_id = upsert_session(result['session'])

        if result['laps']:
            upsert_laps(session_id, result['laps'])

        if result['hr_zones'] and result['hr_zones'].get('zone1_pct') is not None:
            upsert_hr_zones(session_id, result['hr_zones'])

        imported += 1

        if (i + 1) % 50 == 0:
            print(f"  进度: {i+1}/{len(fit_files)}...", file=sys.stderr)

    print(f"\n批量导入完成:")
    print(f"  新导入: {imported}")
    print(f"  跳过(已存在): {skipped}")
    print(f"  错误: {errors}")
    print(f"  总扫描: {len(fit_files)}")
    return imported


if __name__ == "__main__":
    reparse = '--reparse-all' in sys.argv
    scan_and_import(reparse_all=reparse)
