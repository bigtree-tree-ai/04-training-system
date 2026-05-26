# 科学知识体系 + 三级页面 + 可视化重构 — 接续简报

**最后更新**：2026-05-26
**当前分支**：`feature/science-viz-stage-a`
**Plan 文件**：`~/.codefuse/engine/cc/plans/ai-cr-keen-sparrow.md`（执行手册，含三阶段细节）

> 这份简报是"双 AI 并行开发"的 onboarding 文档。任何 AI（包括 Claude/Codex/Gemini 等）下次接手都先读这里。

---

## 一句话项目状态

`training-system` 已上线（agentic coach v1 + productization v1），用户反馈"AI 解读不专业、可视化不足、信赖感低"，启动 3 阶段重构：**科学知识体系 → 分析升级 → 可视化重构**。本侧负责重构，另一 AI 负责产品端维护。

---

## 双 AI 协作纪律（最重要）

| 区域 | 本侧（feature/science-viz-*） | 另一 AI |
|------|------------------------------|---------|
| `training/science/`（新建） | 独占 | 不动 |
| `training/data_import/`、`training/analysis/`、`training/ai_coach/` | 独占（向后兼容） | 不动 |
| `training/web/templates/professional_v2_*.html` + `static/v2/*` | 独占 | 不动 |
| `training/web/templates/product_*.html` + `training/product/` + `accounts.py` | 不动 | 独占 |
| `training/storage/schema.sql` | **末尾追加** | **顶部追加** |
| `training/web/static/style.css` | 仅加 `.pv2-*` 前缀类名 | 不动现有 |
| `requirements.txt` | 末尾注释段追加 | 顶部追加 |
| `scripts/deploy_aliyun.sh`、systemd unit、`.env` | 不动 | 独占 |

每次 push 前：`git fetch origin && git pull --rebase origin main`，冲突手解。

---

## 用户已确认的关键决策

1. **聚焦数据 + 分析 + 可视化重构**，不动产品端 / 账号 / 部署链路
2. **优先级**：先建科学知识体系 → 再升分析 → 再做可视化
3. **目标用户**：作者本人，**专业版优先**（懂 PMC/VDOT/ACWR/HRV，信息密度高）
4. **去赛事化叙事**——不以戈21为主线（旧的"戈21A队备赛"语境已废弃）
5. Git：双方走 feature 分支
6. **每阶段收官**：rebase main → PR → `bash scripts/deploy_aliyun.sh` → 线上验收

---

## 三阶段路线图

### 阶段 A：科学知识体系 + 数据补齐（约 1.5–2 周）→ 当前阶段

- A.1 建 `training/science/` 三学科目录（training / rehab / nutrition）+ `common/` 公共层
- A.2 `schema.sql` 末尾追加 8 张表：`session_track_points`、`session_gait`、`injury_registry`、`pain_log`、`rehab_log`、`nutrition_intake`、`fueling_log`、`thresholds_history`
- A.3 `athlete_config.json` 升级到 v2（结构化 `injuries[]` / `zones` / `vdot` / `sweat_rate` 等）+ 迁移脚本
- A.4 `fit_parser.py` 升级提取 GPS lat/lon/altitude + 步态参数（`vertical_oscillation` / `ground_contact_time` / `stance_time_balance`）+ 回填脚本 `scripts/reparse_fit_v2.py`
- A.5 RPE 录入闭环（专业页面横幅 + `/checkin/rpe`）
- A.6 三学科核心模块首版：
  - `science/training/load_model.py` — monotony/strain + 7d:28d ACWR
  - `science/rehab/return_to_run.py` — 5 阶返跑梯度
  - `science/nutrition/energy_balance.py` — TDEE + EA + REDs 三档评分
- A.7 验收：pytest 全绿 + 单测覆盖 ≥80% + 任选 2 场 FIT reparse 验证 GPS/步态行数
- A.8 部署：rebase main → PR → `bash scripts/deploy_aliyun.sh` → 线上验收

### 阶段 B：分析升级 + 个体化建议（约 1.5–2 周）

- 迁移 `interpretations.py` 解读逻辑到 `science/*/prescriptions.py`
- LT/CV 动态学习管线（每月跑一次）
- 80/20 polarization index 计算与触发
- LLM 升级为按学科组装 + few-shot + 结构化 schema
- 康复个体化（伤病结构化、负荷-疼痛矩阵、返跑阻断规则）
- 营养完整管线（TDEE/EA/CHO 周期化/补给/电解质/咖啡因）
- 分支：`feature/science-viz-stage-b`

### 阶段 C：可视化重构（约 2 周）

- 引入 ECharts 5 / Leaflet / Alpine.js / HTMX（CDN）
- 一级页：决策台 / 体能态势 / 风险雷达 / 学习中心
- 二级页：周月趋势 / 心率分区演化 / 负荷历史 / 伤病时间线 / 营养复盘
- 三级页：单次训练全息解剖（GPS+海拔联动 + HR/Pace/Cadence 三轴时序 + Lap 热力 + 步态雷达）
- 28 张图表（P0/P1/P2 见 plan 文件）
- 信赖感顶栏：数据新鲜度 + 公式悬浮 + 模型卡 + 导出
- 分支：`feature/science-viz-stage-c`

---

## 当前进度（2026-05-26 凌晨）

- [x] Phase 1-3 完成（探索 + 用户对齐 + 设计）
- [x] Plan 文件落盘（`~/.codefuse/engine/cc/plans/ai-cr-keen-sparrow.md`）
- [x] 分支 `feature/science-viz-stage-a` 已建（基于 main，main 当前 HEAD: `6461daf`）
- [ ] **下一步**：A.1 science/ 骨架（建目录 + `__init__.py` + `common/{schemas,athlete_profile,confidence}.py`）

---

## 项目关键事实速查

### 数据状态（已实现）
- COROS OAuth + MCP：14 日滚动同步，断点续传
- FIT 解析：331 sessions（2025-04 ~ 2026-04），3027 圈数据
- DB：SQLite WAL，4 层 schema（raw / canonical / feature / 分析）
- 个人参数：身高 173.5cm，体重 65kg，MaxHR 173，RHR 56，LTHR 159，半马 PB 1:32:45
- 关键伤病：2025-10-23 左膝韧带断裂 → 2025-11-10 手术 → 2026-01 恢复跑步；当前膝盖受力微痛 + 后背酸疼

### 数据状态（缺口）
- ❌ FIT GPS 轨迹未持久化
- ❌ FIT 步态字段（垂直振幅/触地时间/左右平衡）未提取
- ❌ Session RPE 0% 填充
- ⚠️ COROS 长期数据滞后（最新 2026-05-11，靠手动 FIT 导入补）
- ❌ 营养摄入数据完全没有

### 关键文件路径
- `training/storage/schema.sql:1-567` — 末尾追加新表
- `training/data_import/fit_parser.py` — 升级 GPS + 步态
- `training/analysis/pro_metrics.py` — 加 monotony/strain，ACWR 改 7d:28d
- `training/ai_coach/prompt_builder.py` — few-shot + 结构化输出
- `athlete_config.json` — 升级 v2 schema
- `training/web/app.py` — 接入 `api_v2.router`，不直接写路由

### 部署
- 服务器：`101.37.238.138`，systemd `training-web.service`
- 部署目录：`/opt/training-system`
- 部署脚本：`bash scripts/deploy_aliyun.sh`
- 线上：`http://101.37.238.138:8081/training/`
- HTTP Basic：`/opt/training-system/.env`（`TRAIN_AUTH_USER` / `TRAIN_AUTH_PASSWORD`）

---

## 下次会话快速接续清单

```bash
# 1. 进项目并对齐分支
cd /Users/hongxing/Desktop/泓兴的外部测试CC/06-运动数据AI化/training-system
git status
git branch
git fetch origin
git pull --rebase origin main   # 处理另一 AI 的提交

# 2. 跑现有测试确认基线没坏
/opt/homebrew/bin/python3.14 -m pytest

# 3. 读这份简报 + plan 文件 + 另一 AI 的最新 brief
cat docs/science_viz_refactor_brief.md
cat ~/.codefuse/engine/cc/plans/ai-cr-keen-sparrow.md
ls docs/                         # 看另一 AI 最近交付了什么 brief

# 4. 从 plan 的 A.1 开始：science/ 骨架
mkdir -p training/science/{common,training,rehab,nutrition}
touch training/science/__init__.py training/science/common/__init__.py ...
```

---

## 风险登记

| 风险 | 缓解 |
|------|------|
| 双 AI 同时改 schema.sql / 同时改 athlete_config.json | schema 末尾追加；athlete_config 加 `_schema_version` 后原子读改写 |
| GPS 全量回填 800MB-1.2GB | 部署前 `df -h` 检查阿里云磁盘；不足只回填近 6 个月 |
| 营养数据冷启动 | 从今天起按日填，前 4 周营养页显示"开始记录第 N 天"占位 |
| 旧 FIT 文件丢失 | 仅近 6 个月（COROS 仍能拉的窗口）可补 GPS，更早场次 GPS 留 NULL |
| 部署冲突 | 部署前先 SSH 看 `git status`，冲突先在服务器 stash 或 reset |

---

## 参考文献（科学知识体系来源）

- Daniels《Running Formula 4e》— VDOT、E/M/T/I/R 配速
- Friel《The Triathlete's Training Bible》— PMC、ATL/CTL = 7d/42d EWMA
- Magness《Science of Running》— LT2/CV 动态学习
- Bompa《Periodization》— Macro/Meso/Microcycle
- Seiler 80/20 极化论文（2009/2014）
- IOC Consensus Statement on Sports Nutrition 2018
- Mountjoy et al. RED-S IOC 2018/2023
- Blanch & Gabbett (2016) ACWR injury risk
- Soligard et al. IOC Consensus 2016
- van Melick KNGF 2016（ACL 术后康复）
