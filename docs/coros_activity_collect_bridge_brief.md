# COROS 活动同步修复简报 (2026-06-29)

## 背景

用户周末(06-27 周六 12.85km / 06-28 周日 8.96km,连续 tempo)做了训练,但 training-system 决策台看不到,一度误判为"恢复周"。穷尽排查(本地 + 服务器 training.db + 上游 `/opt/coros-collect` 库)发现**两个独立根因**,叠加导致决策台 PMC/ATL 长期失真(ATL≈0.19,误判"长期未训练")。

## 根因(实测验证)

| 根因 | 现象 | 影响 |
|------|------|------|
| `activity.py` 只走 MCP `querySportRecords` | MCP 返回空(拉 0 条),coros-collect 浏览器已采到完整活动但从不读 | 最近活动(含周末)丢失 |
| `session_metrics.py:131` `WHERE sport='running'` | coros session sport 是 `Outdoor Run`/`Indoor Run`,不匹配 | 147 条 coros session 的 `hr_tss` 从未计算 |

→ hr_tss 全 0 → `daily_load`(PMC/ATL/CTL)失真 → 决策台负荷曲线错误。

## coros-collect 字段可靠性(服务器实测确认)

- ✅ 可靠:`activities.distance_cm`(cm)、`activities.avg_hr`、`activity_samples.timestamp`(厘秒,相邻差 100 = 1/s)、`heart_rate`、`cadence`、`altitude`、`gps_lat_e7/gps_lon_e7`(deg×1e7,0 = 室内)
- ❌ 不可靠,一律弃用:`samples.distance_cm`(max 49980000 异常)、`pace`(全 NULL)、`speed`、`calories_kcal`(90 万异常)、`workout_time_s`(06-28=282148≈78h 异常)
- sport_type 编码:100=户外跑、101=室内跑、104=徒步、200/201=骑行、402=力量、900=健走

## 改动(commit `89c7b43`)

1. **新增 `training/coros/activity_collect_bridge.py`**:只读打开 coros-collect 库(`file:...?mode=ro`),读 `activities` + `activity_samples`,upsert 进 `sessions` + `session_track_points`。
   - duration 用 `(max_ts-min_ts)/100` 绕过 workout_time 异常
   - 室内 GPS=0 → lat/lon NULL(绝不写 0.0,避免画到几内亚湾)
   - calories/pace 等不可靠字段不用;不合成 laps(会污染 pace_cv/hr_drift)
   - 幂等:复用 `existing_coros_label_ids()` 去重(filename=`coros_<labelId>.fit`)
2. **修 `session_metrics.py:131`**:`WHERE sport='running'` → `OR sport LIKE '%Run%'`(覆盖 Outdoor/Indoor Run,排除 Hiking/Walking/Cycling)。
3. **CLI `activity-sync-collect [days] [db]`** 子命令(独立,不与 MCP activity-sync 耦合)。
4. **`storage.mark_session_has_track_points(sid)`** helper(upsert_coros_sessions 不写 has_track_points 列)。

## 验证(服务器实测)

| 验证项 | 结果 |
|--------|------|
| 周末入库 | ✅ 06-27 12.85km + 06-28 8.96km,含 6699 秒级 track_points |
| coros hr_tss | ✅ 周六 73.8 / 周日 54.4 / 周五 50.3(之前全 0) |
| daily_load PMC | ✅ ATL 41-58 恢复(之前 ≈0.19),专业指标 165/165 跑步更新 |
| 决策台 | ✅ today + session 页 HTTP 200 |
| 测试 | ✅ 全套件 206 passed(新增 36:collect_bridge 16 + session_metrics 4) |

部署:`git pull` 89c7b43 → 备份 training.db → `activity-sync-collect 7`(小窗验)→ `activity-sync-collect 90`(补齐 18 session/132540 track_points)→ `analyze` 重算。

## 遗留:系统性 `sport='running'` 过滤 bug(待 follow-up)

修 session_metrics 时 grep 发现 `sport='running'` 硬编码遍布 **6 处**,coros session 在这些地方仍被漏算(PMC/ATL 已对,但展示层未对):

- `analysis/weekly_summary.py:20-31`(周报跑步次/跑量=0,coros 被算成交叉训练)
- `ai_coach/prompt_builder.py:59-64`(**AI 教练 prompt 周跑量统计漏 coros**)
- `analysis/pro_metrics.py:281`(VO2max)、`analysis/trend_detector.py:73,94`(趋势)、`web/api.py:64,96,119`(决策台图表)

**修法**:统一 `sport='running' OR sport LIKE '%Run%'`,TDD + 全量 grep 确认无遗漏。

## 协作纪律

仅改 `training/coros/`、`training/analysis/session_metrics.py`、`training/cli.py`、`tests/`(我方独占区);`deploy_aliyun.sh` 未动;push 前 `git pull --rebase`(无冲突)。

---

## 后续(2026-06-29 #2):系统性 sport 过滤 bug 已全量修复(commit dc6e717)

上节"遗留"提到的系统性 `sport='running'` bug,全仓 grep 后发现实际遍布 **~28 处 / 14 文件**(远不止最初估计的 6),已全部修复:

- 共享 `RUN_SPORT_PREDICATE` 常量(`storage/db.py`):weekly_summary / pro_metrics / trend_detector / ai_coach prompt / web api 用 f-string 引用
- 内联 `(sport='running' OR sport LIKE '%Run%')`:thresholds / recovery / queries / csv_importer / professional / dashboard_service / plan_service / comparison_service
- 全套件 211 passed(新增 test_run_sport_filter 5 个);服务器部署 + analyze 重算后**周报跑量恢复**(W22 5次99.6km / W25 6次70.5km,之前全 0;coros 不再被误算交叉训练)
- **修复后浮现真实信号**:W25 跑量 **+218%**(6次70km,超 10% 递增法则),trend_detector 现在会预警(之前漏 coros 看不到)
- 遗留:session_service:39 `get_similar_sessions(sport='running')` 是 Python 参数(非 SQL),牵连函数签名,记后续
