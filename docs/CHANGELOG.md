# Changelog — 科学知识体系重构

## 2026-05-26 阶段 C：可视化重构 + 三级页面

### Added
- `training/web/api_v2.py` — v2 数据 API（5 条路由，只读）
- `training/web/static/v2/pv2.css` — `.pv2-*` namespace CSS（零冲突）
- `templates/professional_v2_today.html` + `pv2_today.js` — 决策台（PMC + 风险雷达 + 三栏卡 + 信赖感顶栏）
- `templates/professional_v2_session.html` + `pv2_session.js` — 单次全息解剖（Leaflet GPS 配速色阶 + 海拔剖面 + HR/Pace/Cadence 三轴 + 心率分区 + 步态雷达 + 分圈表）
- `templates/professional_v2_trends.html` + `pv2_trends.js` — 周月趋势（180d PMC + ACWR 风险带 + 12w 心率分区堆叠）
- ECharts 5.5.0 + Leaflet 1.9.4 通过 CDN 引入

### Changed
- `app.py` 追加 4 条 v2 路由（`/v2`、`/v2/today`、`/v2/sessions/{id}`、`/v2/trends`），旧路由全部保留

### Deploy
- 三级页面本地冒烟全部 HTTP 200
- main HEAD 已部署阿里云

---

## 2026-05-26 阶段 B：分析升级 + 个体化建议

### Added
- `training/science/training/thresholds.py` — LT_HR / Critical Speed 动态学习
- `training/science/training/prescriptions.py` — 训练学解读（个体化 actions）
- `training/science/rehab/prescriptions.py` — 康复学解读 + 部位 prehab 库
- `training/science/nutrition/prescriptions.py` — 营养学解读
- `training/science/nutrition/caffeine.py` — 咖啡因剂量+睡眠安全
- `training/science/nutrition/hydration.py` — 补液 + 失水警示
- `training/science/nutrition/electrolytes.py` — 电解质（钠钾镁）
- `training/science/llm_prompts.py` — Few-shot + 结构化 JSON schema（4 examples）
- `training/application/science_today.py` — SciencePrescription 聚合服务
- 23 个新单测，161 全套件 PASSED

### Changed
- `LoadProfile._verdict` 修复：低 CTL+低 ATL → detrain（替代误判 peak）
- electrolytes notes 触发条件简化（cramp_history 任何情况都加提示）

### Deploy
- main HEAD 已部署阿里云 `:8081/training/`
- 服务 active，API HTTP 200

---

## 2026-05-26 阶段 A：科学知识体系骨架 + 数据补齐

### Added
- `training/science/` 三学科目录（training/rehab/nutrition + common 9 模块）
- 8 张新表（GPS、步态、伤病、疼痛、康复、营养摄入、补给、阈值历史）
- athlete_config v2 + 幂等迁移脚本（自动反推结构化 injuries[]）
- FIT GPS+步态解析升级（每秒 lat/lon/altitude/hr/speed/cadence + 步态汇总）
- `scripts/reparse_fit_v2.py` 增量回填脚本
- 三学科首版算法（Daniels/Friel/Foster/Hulin/Seiler/IOC RED-S）
- 35 个 science 单测，138 全套件 PASSED

### Migration
- DB 自动 ALTER：`sessions.rpe / has_track_points / has_gait`
- DB 自动 ALTER：`athlete_checkins.session_rpe / session_id`

### Deploy
- main HEAD `e14f8d4` 已部署阿里云
- 8 张新表已在线，公网 200，内网 API 200
