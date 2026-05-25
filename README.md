# AI 运动康复与训练教练团

个人私有的 AI + 运动训练系统。当前版本以 COROS/FIT 数据、主观晨检、训练课表和精选证据库为输入，输出今日训练建议、恢复/负荷/疼痛风险、专家团意见和可追溯的证据依据。

## 当前状态

- 最新主线：Agentic Coach v1 + Productization v1
- 线上路径：`http://101.37.238.138:8081/training/`
- 部署目录：`/opt/training-system`
- 服务：`training-web.service`
- 默认入口：`/`，显示“今天”工作台
- 小白产品入口：`/product/today`
- 认证：生产环境启用 HTTP Basic auth，凭据来自 `/opt/training-system/.env`

## 快速开始

```bash
cd /Users/hongxing/Desktop/泓兴的外部测试CC/06-运动数据AI化/training-system
/opt/homebrew/bin/python3.14 -m pytest
/opt/homebrew/bin/python3.14 -m training.cli serve --port 8090
```

本地访问：

- `http://127.0.0.1:8090/`：今天
- `http://127.0.0.1:8090/product`：小白用户注册/登录
- `http://127.0.0.1:8090/product/today`：小白版“今天练什么”
- `http://127.0.0.1:8090/dashboard`：传统训练仪表板
- `http://127.0.0.1:8090/coros`：COROS 全景
- `http://127.0.0.1:8090/api/v1/today`：今日 AI 建议 JSON

## 核心能力索引

### 数据输入

- FIT 原始文件：`training/data_import/`
- COROS MCP 同步：`training/coros/`
- 主观晨检：`/api/v1/checkins`
- 运动员配置：`athlete_config.json`

### 数据层

- Raw layer：`raw_ingest_events`
- Canonical layer：`canonical_daily_metrics`
- Feature layer：`daily_features`
- SQLite schema：`training/storage/schema.sql`

### AI 教练团

- 领域模型和端口：`training/domain/`
- 特征管线：`training/application/features.py`
- 多专家教练决策：`training/application/coach.py`
- 自主心跳：`training/application/heartbeat.py`
- 今日聚合服务：`training/application/today.py`
- SQLite 适配器：`training/adapters/sqlite_repositories.py`

### 证据库

- 精选证据种子：`training/evidence/seeds.py`
- 本地检索器：`training/evidence/retriever.py`
- API：`/api/v1/evidence/search`

### Web/PWA

- FastAPI app：`training/web/app.py`
- API routes：`training/web/api.py`
- Product API routes：`training/web/product_api.py`
- 今天页：`training/web/templates/today.html`
- 小白产品页：`training/web/templates/product_*.html`
- 样式：`training/web/static/style.css`
- PWA：`/manifest.webmanifest`、`/service-worker.js`

### Productization v1

- 账号和会话：`training/product/accounts.py`
- 用户隔离、导出删除、后台查询：`training/product/repository.py`
- FIT 上传首报：`training/product/uploads.py`、`training/product/reports.py`
- 产品测试：`tests/test_productization.py`

## 主要 API

- `GET /api/v1/today`
- `POST /api/v1/checkins`
- `GET /api/v1/checkins`
- `POST /api/v1/sync/run`
- `GET /api/v1/coach/recommendations`
- `POST /api/v1/coach/recommendations`
- `POST /api/v1/plan/confirm`
- `GET /api/v1/evidence/search`

### 产品 API

- `POST /api/product/auth/register`
- `POST /api/product/auth/login`
- `POST /api/product/onboarding`
- `POST /api/product/fit/upload`
- `GET /api/product/today/simple`
- `GET /api/product/privacy/export`
- `DELETE /api/product/privacy/account`
- `POST /api/product/notifications/subscribe`
- `GET /api/product/admin/users`

## 常用命令

```bash
# 全量测试
/opt/homebrew/bin/python3.14 -m pytest

# 启动本地服务
/opt/homebrew/bin/python3.14 -m training.cli serve --port 8090

# 查看今日建议
/opt/homebrew/bin/python3.14 -m training.cli today

# 手动运行心跳
/opt/homebrew/bin/python3.14 -m training.cli heartbeat morning

# COROS 授权和同步
/opt/homebrew/bin/python3.14 -m training.cli coros-login
/opt/homebrew/bin/python3.14 -m training.cli coros-sync 14
/opt/homebrew/bin/python3.14 -m training.cli coros-overview
```

## 部署

```bash
bash scripts/deploy_aliyun.sh
```

部署脚本会同步 `origin/main` 到 `/opt/training-system`，安装依赖，重启 `training-web.service`，并保留每日 COROS sync cron。

生产环境需要 `/opt/training-system/.env`：

```bash
TRAIN_AUTH_USER=...
TRAIN_AUTH_PASSWORD=...
```

不要把 `.env`、`.coros_auth.json`、API key、服务器密码或私钥提交到 Git。

## 交付验收标准

每次开发交付前必须完成：

- 单元测试、集成测试、回归测试通过
- 空数据、异常输入、认证、重复提交、缺失配置等边界验证
- 完整用户链路走通
- 本地页面/API 验收
- 涉及部署时完成服务器服务状态和 `/training/` 路由验收
- 最终说明 Git 状态、提交、测试结果和线上验证结果

详细简报见 [docs/agentic_coach_v1_brief.md](docs/agentic_coach_v1_brief.md) 和 [docs/productization_v1_brief.md](docs/productization_v1_brief.md)，索引见 [docs/INDEX.md](docs/INDEX.md)。
