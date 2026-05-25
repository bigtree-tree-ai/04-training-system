# Productization v1 开发简报

## 目标

把个人私教优先的 Agentic Coach 扩展成可给小白用户试用的封闭 Beta：账号、数据隔离、onboarding、FIT 上传首报、小白版“今天练什么”、隐私/免责声明/导出删除、管理后台和 PWA 提醒底座。

## 已实现

- 多用户账号：`product_users`、`product_auth_sessions`，首个注册用户自动为 admin。
- 数据隔离：产品侧 FIT 上传写入 `sessions.owner_user_id`，产品 API 只按当前登录用户查询。
- Onboarding：目标赛事、跑步基础、可训练时间、心率、身高体重、伤病史、当前不适、免责声明确认。
- FIT 上传：`POST /api/product/fit/upload` 支持 raw octet-stream，处理中文文件名，解析后生成首份报告。
- 小白 Today：`/product/today` 输出今日建议、readiness、风险理由、下一步、最近训练和最近首报。
- 隐私能力：`/product/privacy` 和 API 支持数据导出、账号数据删除、免责声明展示。
- 管理后台：`/product/admin` 和 `/api/product/admin/users` 展示用户、上传、训练计数。
- PWA 底座：`manifest.webmanifest`、`service-worker.js`、通知订阅记录和测试通知 API。

## 新增核心文件

- `training/product/accounts.py`：密码哈希、会话 cookie、用户权限。
- `training/product/repository.py`：产品用户 profile、上传记录、Today、导出删除、通知、后台查询。
- `training/product/uploads.py`：FIT 上传保存、解析、owner 写入、首报生成。
- `training/product/reports.py`：面向小白的首份报告生成。
- `training/web/product_api.py`：产品化 API。
- `training/web/templates/product_*.html`：产品页面。
- `tests/test_productization.py`：端到端产品化测试。

## API 索引

- `POST /api/product/auth/register`
- `POST /api/product/auth/login`
- `POST /api/product/auth/logout`
- `GET /api/product/me`
- `GET /api/product/onboarding`
- `POST /api/product/onboarding`
- `POST /api/product/fit/upload`
- `GET /api/product/today/simple`
- `GET /api/product/privacy/export`
- `DELETE /api/product/privacy/account`
- `POST /api/product/notifications/subscribe`
- `POST /api/product/notifications/test`
- `GET /api/product/admin/users`

## 验收记录

- `/opt/homebrew/bin/python3.14 -m pytest`：100 passed。
- 浏览器链路：注册 -> onboarding -> 中文 FIT 上传 -> 首份报告 -> Today 刷新 -> 隐私导出 -> 通知订阅 -> 管理后台。
- 移动端验收：390x844 截图检查 Today 页面内容无明显重叠。

## 仍需产品化增强

- 远程 Web Push 需要补 VAPID key 和发送器；当前 v1 已有 PWA manifest、service worker、订阅记录、测试通知和通知审计。
- 生产开放前需要补邮箱验证、密码重置、rate limit、审计保留策略和正式隐私协议文本。
- 个人旧 dashboard 仍是私有系统；小白用户默认入口应使用 `/product/today`。

