# COROS 采集链路补全简报 (2026-06-18)

## 背景

用户要求「每天自动化获取最新高驰运动数据」并让链路完整。深度诊断后发现:核心采集其实**已在健康运行**——`/opt/coros-collect` 由 systemd timer 每天 03:33 自动跑 `run-daily`,连续成功(06-18 拉到新数据,380 活动/百万采样/session 仍有效)。真正缺的是采集数据未打通进 AI 教练,外加几处遗留断点。

## 诊断结论(已实测验证)

| 维度 | 诊断前 | 诊断后 |
|------|--------|--------|
| 每日自动采集 | 以为要从零建 | ✅ coros-collect systemd timer 已健康运行 |
| training 旧 MCP coros cron | 以为正常 | ❌ 每天报 `Session not found 404`(COROS 升级 MCP 协议) |
| AI 教练数据源 coros_* 表 | 以为空 | ⚠️ 有历史数据但 stale(recovery 最新 06-15) |
| 钉钉通知 | 以为没接 | 🟡 代码已全接好,仅缺 webhook 环境变量 |
| dashboard 公网 | 以为没挂 | ✅ `bigtree.ink/coros/` 已 HTTP 200 |

## 关键架构事实

AI 教练今日建议**不读** `canonical_daily_metrics`(只写审计表),而读 `coros_*` 表实时计算(`features.py:compute_for_date → get_coros_daily_context`)。其中 `coros_recovery_snapshots.recovery_pct` **直接决定 recovery_score**。所以灌入目标是 `coros_*` 表,而非 canonical。

## 实施

### 阶段1 清理与可靠性
- 移除 training 坏 coros cron(每天 05:15 的 MCP 404 噪音)
- 修 coros-collect `run-daily` 孤儿 sync_run bug(health 失败时残留 running,导致 dashboard 卡状态)

### 阶段3 数据打通(核心)
- 新建 `training/coros/collect_bridge.py`:从 coros-collect `daily_metrics` 桥接进 training `coros_*` 表,复用 `coros/storage.py` 幂等 upsert
- 字段映射:
  - `dashboard.summaryInfo.recoveryPct` → `coros_recovery_snapshots.recovery_pct`(驱动 recovery_score)
  - `dashboard.summaryInfo.sleepHrvData.sleepHrvList[]` → `coros_hrv`(近6天 HRV)
  - `dashboard.summaryInfo.fullRecoveryHours` → `coros_recovery_snapshots.estimated_full_recovery_hours`
  - `analyse.dayList.sample[].rhr` → `coros_heart_rate_daily.resting_hr`
  - `analyse.dayList.sample[].t7d/t28d/trainingLoadRatio` → `coros_training_load`
- CLI: `coros-bridge` 子命令(`training/cli.py`)
- 测试: 10 个(解析器单元 + 端到端 + 幂等 + prune + 错误处理)
- 服务器 cron: 每天 04:00 自动桥接(coros-collect 03:33 采集后)

## 验证结果

- 桥接真实数据灌入:`heart_rate:3 / training_load:3 / hrv:6 / recovery:1`
- **AI 教练 `recovery_score: 98`**——用上今日真实恢复%(此前基于 06-15 的 74 或 PMC 估算)
- `readiness_score: 94`(基于真实 recovery)
- 测试:training **170 passed**(1 个预存 `test_science_profile_confidence` 失败,经 stash 验证与本次无关);coros-collect **31 passed**

## 服务器变更清单

| 项 | 变更 |
|----|------|
| crontab | 移除 training `coros-sync`;新增 `coros-bridge`(04:00) |
| /opt/training-system | git pull `f144261`(桥接代码) |
| /opt/coros-collect/src/coros_collect/cli.py | rsync 孤儿 bug 修复 |
| 备份 | 旧 crontab 存 `/tmp/crontab.bak.coros` |

## Git

- training-system: `511900d → f144261` (feat: coros bridge + README 修正)
- 08-AI-training-IOSapp: `e0600e6 → 7017921` (fix: run-daily sync_run abort)

## 已知限制与后续低成本入口

1. **数据维度**:桥接覆盖 recovery%/HRV/心率/训练负荷。**睡眠/压力明细**需修 MCP `coros-sync`(`Session not found 404`,COROS 升级 MCP 协议所致)——本次不做。
2. **analyse.query 心率/负荷是 3 月历史**(该 Training Hub 端点数据特性);今日心率主要靠 dashboard 快照。HRV 是近6天新鲜数据。
3. **启用钉钉通知**(代码已接好,零改动):仅需 `/etc/coros-collect.env` 加一行 `COROS_DINGTALK_WEBHOOK=xxx` + 重启 service。
4. **science_profile_confidence 测试**:预存失败(stash 验证确认与本次无关),建议单独排查。
5. **canonical 今日字段 null**:因 `coros_hrv/heart_rate` 严格按今日 date 查,而 COROS 次日才生成(最新 HRV 是昨日)。recovery 不受影响(快照表取最新)。
