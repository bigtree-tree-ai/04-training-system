# COROS MCP 12 维度恢复 + 全维度每日采集链路完成 (2026-06-24)

## 背景

身体明细(睡眠/压力/心率)断链诊断(见 `coros_auto_collect_diagnosis_brief.md`)后确认:Training Hub 团队版不含个人健康明细,**只能走 MCP OAuth**。但 MCP 因 refresh_token 失效 + 工具改名完全断开,睡眠/压力数据停在 06-11 静默 11 天。本次修复并恢复全维度每日自动采集。

## 修复过程(四步)

| 步骤 | 内容 | commit |
|------|------|--------|
| 1. token 健康基础设施 | token 失败不抛异常,优雅降级记 `token_expired`,根治静默断链 | `101d9ad` |
| 2. 用户重新授权 | 本地 `coros-login`(需 `SSL_CERT_FILE=certifi` 绕过企业代理 CA) | — |
| 3. 发现工具改名 | `queryHrvAssessment` → `querySleepHrv`(tools/list 实测 22 工具) | `37f7dd2` |
| 4. 验证 12 维度 | coros-sync 14 全通,数据新鲜到 06-24 | — |

## 全维度每日采集链路(已上线)

```
03:33  coros-collect   运动/活动/恢复%/HRV(浏览器 session,稳定)
         ↓
04:00  coros-bridge    桥接运动数据 → coros_* 表
         ↓
04:05  coros-sync 14   MCP 身体明细(睡眠分期/压力/心率)→ coros_* 表
         ↓
      AI 教练 today(读 coros_* 表 → ReadinessFeatures → 决策)
```

## 验证证据(全实跑)

**coros-sync 14 输出**:
```
recovery:1  fitness:1  training_load:28  daily_health:14
sleep:14  hrv:7  resting_hr:14  avg_hr:14  stress:14  schedule:7  devices:5  profile:1
```

**数据新鲜度**(此前身体明细停在 06-11):
| 表 | 修复前 max | 现在 max |
|----|-----------|---------|
| coros_sleep | 06-11 | **06-24** |
| coros_stress_daily | 06-11 | **06-24** |
| coros_daily_health | 06-11 | **06-24** |
| coros_heart_rate_daily | 06-11 | **06-24** |

**AI 教练 today 用上身体数据**:
```
readiness 86 / recovery 97
sleep_hours 8.07 · sleep_score 76 · stress_avg 17 · resting_hr 54 · hrv_ms 51
```

## 关键技术发现

1. **COROS MCP 工具改名**(2026 升级):`queryHrvAssessment` → `querySleepHrv`。返回格式与 `parse_hrv` 兼容,仅改工具名即可。
2. **本地 Mac SSL 陷阱**:python3.14 的 `SSL_CERT_FILE` 被 codefuse 企业代理 CA(`starpoint-root-ca-g2.pem`)占用,导致 coros-login SSL 失败。必须 `SSL_CERT_FILE=$(/opt/homebrew/bin/python3.14 -m certifi)` 绕过。
3. **MCP endpoint 活着**:`mcpcn.coros.com/mcp` 返回 401(需认证)非 404,协议没坏,是 token + 工具名问题。

## 长期维护点

- **MCP refresh_token 约 30 天过期**,到期前 token_health 会记 `sync_run=token_expired` 预警
- **续期命令**(本地 Mac):
  ```
  SSL_CERT_FILE=$(/opt/homebrew/bin/python3.14 -m certifi) /opt/homebrew/bin/python3.14 -m training.cli coros-login
  ```
  然后 `scp .coros_auth.json root@server:/opt/training-system/`
- 这是 COROS 平台限制:个人健康数据必须本人 OAuth 授权,团队浏览器 session 拿不到

## 新发现可用 MCP 工具(未来可接,本次未用)

- `querySportRecords` — 运动记录(当前 `coros_sport_records` 表为空,可填)
- `downloadActivityFitFiles` / `queryActivityFitFileDownloadUrls` — FIT 文件下载(解"服务器无 FIT 原文件"遗留)
- `queryStressTimeSeries` / `queryHealthCheckTimeSeries` — 压力/健康时序

## Commits

- `101d9ad` feat(coros): token 健康检查 + coros-sync 优雅降级
- `ffe8df7` docs: 自动采集链路诊断简报
- `37f7dd2` fix(coros): queryHrvAssessment→querySleepHrv

## 测试

token_health + sync 相关 10 passed;全量 176 passed(1 个预存 `test_science_profile_confidence` 失败,stash 验证与本次无关)。
