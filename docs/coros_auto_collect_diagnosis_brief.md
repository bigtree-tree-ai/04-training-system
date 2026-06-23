# COROS 自动采集链路诊断 + token 健康检查简报 (2026-06-23)

## 背景

用户要求"每天自动化采集最新高驰运动数据 + 身体记录"。上一轮(coros-bridge)已打通**运动数据**(活动/负荷/课表/恢复%/HRV),但 14 天报告暴露 **身体明细(睡眠/压力/完整心率)06-12 起断流**。本轮目标是把断掉的身体数据链路也做成每天自动。

## 诊断结论:链路全貌(已实测验证)

| 数据维度 | 来源 | 状态 | 证据 |
|---------|------|------|------|
| 活动/训练/课表/恢复%/HRV | Training Hub 团队版 | ✅ 每天自动 | coros-collect 03:33 + bridge 04:00,数据新鲜到 06-21 |
| **睡眠分期/压力/完整心率** | **Training Hub 没有** | ❌ 断在 06-11 | 旧 MCP 坏掉前的历史数据 |

**三条路全部实测,得出唯一可行路径:**

### 路1:HTTP 端点逆向 → ❌ 证伪
用浏览器 session 探测 20 个候选端点(`/sleep/query` `/stress/query` `/dailyHealth/query` 等),**全部 500**(固定 `apiCode: 5C4D208` + 空 message)。COROS 网关对未知健康路径统一拒绝,硬猜路径此路不通(要真实路径得抓浏览器流量)。

### 路2:扩展 coros-collect 采 Training Hub → ❌ 证伪
下载 Training Hub 前端主程序 main.js(1.5MB),grep 证实它**根本不调用睡眠/压力端点**:
- `sleep` 出现 **0 次**,`stress` **0 次**,`hrv` **0 次**
- 全部 `/xxx/query` 端点只有 activity/dashboard/training/profile/team
- `/admin/views/sleep` 等路由都返回同一个 SPA(4508 字节)

**结论:Training Hub 团队版是教练/团队视角,不含个人健康明细。** 这是 COROS 平台设计,不是 bug。

### 路3:MCP OAuth → ✅ 唯一可行,但 token 失效
旧 MCP `run 23` 成功过 12 个工具(`querySleepData`/`queryStressLevel`/`queryDailyHealthData` 等),parsers + storage 写入层 100% 完整。但 **refresh_token 失效**:
- `mcpcn.coros.com/mcp` 返回 401(需认证,非 404)→ endpoint 活着
- access_token 5-21 签发已过期,refresh 返回 `{"error":"invalid_grant"}`
- 旧代码在 `CorosMcpClient.__init__` 抛异常 → 每日 cron 静默崩 11 天无人知

## 本次交付:token 健康检查基础设施(commit 101d9ad)

为"修 MCP 恢复 12 维度"铺路,先解决**静默断链**这个根性问题。

| 文件 | 改动 |
|------|------|
| `training/coros/token_health.py`(新) | token 状态检查**不抛异常**,返回结构化状态 `ok/expired/refresh_failed/missing`;失败时尝试 refresh 并给"需重新 coros-login"明确指引 |
| `training/coros/sync.py`(改) | token 失败时记 `sync_run=token_expired` + 优雅返回 `success=False`,不再崩 cron;仅在自动构造 client 时检查(测试传 client 则跳过) |
| `tests/test_token_health.py`(新) | 5 单元:missing/ok/refresh_failed/refresh_success/get_valid_token |
| `tests/test_coros_sync.py`(改) | 降级测试:token 失败优雅返回 + sync_run token_expired;token 有效但 client 坏仍 raise+failed |

**测试**:token_health + sync 相关 **10 passed**;全量 **176 passed**(1 个预存 `science_profile_confidence` 失败,stash 验证与本次无关)。

## 关键认知(COROS 平台限制)

1. **运动数据 vs 身体明细是两条独立链路**:运动走 Training Hub 浏览器 session(稳定,长期有效);身体明细只能走 MCP OAuth(token 会过期)。
2. **不能靠扩 Training Hub 采集器拿睡眠**——团队版压根没这数据。
3. **MCP token 续期是长期维护点**:refresh_token 会过期(本次约 32 天),需周期性重新 coros-login。token_health 让断链可见,但续期本身需人工 OAuth。

## 待办(等用户 coros-login 后接手)

1. **本地 coros-login**(用户操作,~5 分钟):本地 Mac 的 python3.14 因 codefuse 企业代理 CA(`SSL_CERT_FILE=starpoint-root-ca-g2.pem`)导致 SSL 失败,**必须加 `SSL_CERT_FILE=$(python3.14 -m certifi)` 绕过**。已验证 `register_client`(登录第一步)在 certifi 下成功。
2. **部署**:scp 新 `.coros_auth.json` + 本批代码到服务器
3. **验证**:跑 `coros-sync 14`,确认 `querySleepData` 等 12 工具恢复,coros_sleep/coros_stress_daily 灌入今日数据
4. **挂回 cron**:04:05(bridge 之后)跑 coros-sync,端到端验证睡眠/压力每日更新
5. **token 续期预警**:token_health 已就位,后续可接入钉钉/webhook 提前预警

## Git

- `101d9ad` feat(coros): token 健康检查 + coros-sync 优雅降级
- 已 push 到 `origin/main`(`6013265..101d9ad`)

## 本地 coros-login 指引(经验证可跑)

```
cd /Users/hongxing/Desktop/泓兴的外部测试CC/04-training-system/training-system
SSL_CERT_FILE=$(/opt/homebrew/bin/python3.14 -m certifi) /opt/homebrew/bin/python3.14 -m training.cli coros-login
```

浏览器打开 COROS 授权页 → 登录 → 同意授权 → 返回 `Refresh token: yes`。
