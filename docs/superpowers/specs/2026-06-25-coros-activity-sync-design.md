# COROS Activity 自动采集链路 — 设计文档

- **日期**: 2026-06-25
- **状态**: design（待评审）
- **关联**: `training/coros/sync.py`、`scripts/reparse_fit_v2.py`、`training/storage/schema.sql`

## 1. 背景与问题

- **现状**：`coros-sync`（`sync.py`）只调用了 COROS MCP 的 **12 个汇总统计工具**（恢复/体能/训练负荷/每日健康/睡眠/HRV/静息心率/平均心率/压力/计划/设备/资料）。
- **缺口**：COROS MCP 另有 **9 个 activity/session 级工具**（`querySportRecords`、`getActivityDetail`、`queryActivityLapData`、`downloadActivityFitFiles` 等）**完全未接入**。
- **后果**：训练 session 明细（距离/配速/心率/分段/步态）只能靠**手动导出手表 FIT** 再导入，本地 `sessions` 表最新记录停在 **2026-04-06**，之后约 2.5 个月训练未自动入库。
- **事实**：平台数据完整且可自动拉取。实测 `querySportRecords` 已返回结构化训练记录（含 2026-06-24 的 14.25km 强度课）。token 有效期约 30 天。

## 2. 目标与非目标

**目标**
- 自动从 COROS 平台采集训练 session 全量明细，入库 `sessions` / `laps` / `track_points` / `gait`。
- 全量回填历史（从最早可拉记录起，跨 1–2 年）。
- 之后每日增量自动采新训练。

**非目标（YAGNI，本期不做）**
- `analyzeActivityDetail`（教练式文本分析）→ `ai_summary` 留待后续独立 AI 分析环节。
- `queryHealthCheckTimeSeries` / `queryStressTimeSeries`（秒级原始序列）→ 暂不采集。

## 3. 关键事实（COROS MCP 实测，2026-06-25）

| 工具 | 入参 | 返回要点 |
|------|------|----------|
| `querySportRecords` | startDate/endDate(yyyyMMdd, 默认近7天), sportTypeCodes[], limit, timezone | 文本列表：每条 LabelId、SportType、start/endTimestamp、Duration、Distance、Average Pace、Avg HR、Calories、Location |
| `getActivityDetail` | **labelId, sportType**(均必填) | Workout Time、Distance、Avg/Moving/Best Pace、Avg HR、Avg Cadence、Stride Length、Calories、**Training Load、Aerobic TE、Anaerobic TE、Training Focus、Perceived Effort** |
| `queryActivityLapData` | **labelId, sportType**(均必填) | 结构化 JSON：columns 含 lapIndex/distance/time/avgPace/avgPower/avgHr/maxHr/groundTime/groundBalance/avgCadence/strideRatio/strideHeight/avgStrideLength… |
| `downloadActivityFitFiles` | startDate/endDate/sportType/labelId/limit（全可选） | FIT 二进制资源 |

> 注：`getActivityDetail`/`queryActivityLapData` 必须同时传 `labelId` 和 `sportType`，缺 `sportType` 会触发后端 NPE。

## 4. 架构：4 步采集管线

```
Step 1  querySportRecords(startDate, endDate)
        → 训练记录列表 [{labelId, sportType, startTs, distance, pace, hr, duration, calories}, ...]
            ↓ 过滤掉 sessions 表已有的 labelId（增量）
Step 2  对每个新 labelId:
        getActivityDetail(labelId, sportType)
        → 高级字段(TE / aerobic / anaerobic / cadence / stride / focus / load)
Step 3  queryActivityLapData(labelId, sportType)
        → JSON → 解析为 laps 行
Step 4  downloadActivityFitFiles(startDate, endDate)  (按日期批量)
        → FIT 文件落盘 config.COROS_FIT_DIR
        → 复用 parse_fit_file() + upsert_track_points() + upsert_gait()
```

复用现有基础设施：`CorosMcpClient`、`parse_fit_file`、`upsert_track_points/gait`、`laps` 表。

## 5. 数据映射（工具 → 表 → 字段）

| sessions 字段 | 来源 |
|---------------|------|
| filename | 构造 `coros_<labelId>.fit`（UNIQUE 去重键） |
| sport / sub_sport | SportType 映射（101→running 等） |
| start_time | querySportRecords `startTimestamp` → ISO（Asia/Shanghai） |
| duration_sec | getActivityDetail Workout Time |
| distance_km | querySportRecords Distance |
| total_calories | querySportRecords Calories |
| avg_hr | querySportRecords Avg HR |
| max_hr | FIT 解析（parse_fit_file） |
| avg_pace_sec | querySportRecords Average Pace（mmss→秒） |
| avg_cadence | getActivityDetail Average Cadence |
| training_effect | getActivityDetail Aerobic TE |
| anaerobic_te | getActivityDetail Anaerobic TE |
| training_type / training_effect_label | getActivityDetail Training Focus |
| recovery_hours | getActivityDetail（若返回） |

| 其他表 | 来源 |
|--------|------|
| `laps` | queryActivityLapData JSON（lapIndex/distance/time/avgPace/avgHr/avgPower…） |
| `track_points` | FIT → parse_fit_file |
| `gait` | FIT → parse_fit_file |

## 6. 去重 / 增量 / 全量回填

- **去重键**：`sessions.filename = coros_<labelId>.fit`（UNIQUE 约束天然防重）。
- **增量**：Step 1 拉回的 labelId 集合，扣除 `sessions` 表已存在的 → 只处理新训练。
- **全量回填**：CLI `--full` 时 startDate 设最早（如 `20240101`），endDate=today，一次性拉齐。

## 7. FIT 存储与服务器同步

- 落盘 `config.COROS_FIT_DIR`（`reparse_fit_v2.find_fit` 已查此目录），文件名 `coros_<labelId>.fit`，与 sessions.filename 对齐。
- FIT 较大，**不入 git**。本地采集后用 rsync 同步到阿里云服务器对应目录（与代码部署解耦）。

## 8. 调度集成

- **CLI**：`training activity-sync [days]`（默认增量近 N 天）/ `activity-sync --full`（全量回填）。
- **cron**：并入现有 03:33 调度，在 `coros-sync` 之后自动跑 `activity-sync`（增量）。

## 9. 模块组织与接口

- **新建** `training/coros/activity.py`
  - `class ActivitySyncService(client=None, timezone="Asia/Shanghai")`
  - `sync(days=7, full=False) -> dict`：返回 success / persisted 计数 / failed_labelIds
  - 与 `sync.py`（汇总统计）分离，职责清晰，可独立测试。
- **扩展** `training/coros/parsers.py`
  - `parse_activity_detail(text) -> dict`
  - `parse_activity_laps(json_text) -> list[dict]`
  - `parse_sport_records(text) -> list[dict]`（含 labelId/sportType）
- **扩展** `training/coros/storage.py`
  - `upsert_session_from_coros(record)` / `upsert_laps(session_id, laps)`
- **复用** `training/data_import/fit_parser.parse_fit_file` + `training/storage/writers.upsert_track_points/upsert_gait`
- **扩展** `training/cli.py`：加 `activity-sync` 子命令。

## 10. 错误处理

- 单个 activity 任一步（detail/lap/fit）失败 **不中断整体**，记入 `failed_labelIds`，下次运行重试。
- FIT 下载失败 → sessions/laps 已入库的保留，track_points/gait 标 `has_*=0`，由 `reparse_fit_v2` 后续补。
- 复用 `sync.py` 的 token 失效优雅降级（`token_expired` 不崩）。

## 11. 测试策略

- **解析器单测**：用 2026-06-24 真实样本固定 `parse_sport_records` / `parse_activity_detail` / `parse_activity_laps`。
- **采集服务单测**：mock `CorosMcpClient.call_tool` 返回固定样本（参照 `test_coros_sync.py` 的 FakeClient 模式），验证入库字段、去重、增量过滤。
- **FIT 衔接测试**：mock FIT 下载 → 验证 `parse_fit_file` 被调用、track_points/gait 写入。
- **错误路径**：模拟 detail NPE / FIT 下载失败 → 验证不中断、failed_labelIds 记录。

## 12. 实现顺序建议

1. parsers（sport_records / activity_detail / activity_laps）+ 单测
2. storage upsert（session_from_coros / laps）
3. ActivitySyncService.sync（4 步管线 + 去重增量）
4. FIT 下载 + parse_fit_file 衔接
5. CLI `activity-sync` + `--full`
6. 全量回填实测 + cron 接入
7. 服务器 rsync FIT 同步
