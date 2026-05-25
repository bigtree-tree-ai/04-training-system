# 项目索引

这个目录只保留当前有效文档。旧的阶段性进展文档已删除，避免下次启动时读取过期资料。

## 当前文档

- [项目 README](../README.md)：快速开始、架构索引、命令、API、部署和验收标准。
- [Productization v1 开发简报](productization_v1_brief.md)：多用户、小白 onboarding、FIT 上传首报、隐私、后台和 PWA 底座。
- [Agentic Coach v1 开发简报](agentic_coach_v1_brief.md)：本次重构内容、链路、测试、部署和后续入口。

## 快速定位

- 今天页：`training/web/templates/today.html`
- 小白产品入口：`training/web/templates/product_today.html`
- 产品 API：`training/web/product_api.py`
- 产品账号/隔离：`training/product/`
- v1 API：`training/web/api.py`
- 教练团逻辑：`training/application/coach.py`
- 心跳机制：`training/application/heartbeat.py`
- 特征管线：`training/application/features.py`
- 领域端口：`training/domain/ports.py`
- 证据库：`training/evidence/seeds.py`
- SQLite schema：`training/storage/schema.sql`
- 验收测试：`tests/test_agentic_coach.py`、`tests/test_productization.py`

## 下次开发建议入口

1. 先读 `README.md` 和本文件。
2. 跑 `/opt/homebrew/bin/python3.14 -m pytest`。
3. 查看 `GET /api/v1/today` 当前输出。
4. 修改前确认是否影响 `/training/` 线上路径和 `training-web.service`。
