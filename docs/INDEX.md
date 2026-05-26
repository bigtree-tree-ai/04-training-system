# 项目索引

这个目录只保留当前有效文档。旧的阶段性进展文档已删除，避免下次启动时读取过期资料。

## 当前文档

- [项目 README](../README.md)：快速开始、架构索引、命令、API、部署和验收标准。
- [Productization v1 开发简报](productization_v1_brief.md)：多用户、小白 onboarding、FIT 上传首报、隐私、后台和 PWA 底座。
- [Agentic Coach v1 开发简报](agentic_coach_v1_brief.md)：教练团决策与心跳机制。
- [科学知识体系重构接续简报](science_viz_refactor_brief.md)：双 AI 协作、三阶段路线、协作纪律。
- [阶段 A 验收报告](stage_a_acceptance.md)：科学骨架 + 数据补齐 + 35 单测。
- [阶段 B 验收报告](stage_b_acceptance.md)：分析升级 + 个体化 + 23 单测。
- [阶段 C 验收报告](stage_c_acceptance.md)：可视化重构 + 三级页面 + Playwright 验证。
- [Changelog](CHANGELOG.md)：科学重构三阶段时间线。

## 快速定位

- **v2 决策台**：`training/web/templates/professional_v2_today.html` + `static/v2/pv2_today.js`
- **v2 全息解剖**：`training/web/templates/professional_v2_session.html` + `static/v2/pv2_session.js`
- **v2 趋势页**：`training/web/templates/professional_v2_trends.html` + `static/v2/pv2_trends.js`
- **科学知识体系**：`training/science/{common,training,rehab,nutrition}/`
- **SciencePrescription 聚合**：`training/application/science_today.py`
- **v2 API**：`training/web/api_v2.py`
- 今天页（v1）：`training/web/templates/today.html`
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
