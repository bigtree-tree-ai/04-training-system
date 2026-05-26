# 阶段 A 验收报告：科学知识体系 + 数据补齐

**分支**：`feature/science-viz-stage-a`
**完成时间**：2026-05-26
**测试结果**：138 passed（103 原有 + 35 新增 science 测试）零回归

---

## 交付物

### A.1 science/ 骨架（已完成）

```
training/science/
├── __init__.py                       # SCHEMA_VERSION = 2
├── common/
│   ├── __init__.py
│   ├── schemas.py                    # LoadProfile / PolarizationCheck / ReturnToRunStage / EnergyBalanceReport / SciencePrescription
│   ├── athlete_profile.py            # AthleteProfile + Injury + HRZones（兼容 v1/v2）
│   └── confidence.py                 # DataConfidence 8 维信号加权
├── training/
│   ├── __init__.py
│   ├── load_model.py                 # CTL/ATL/TSB/ACWR_7-28/Monotony/Strain
│   └── pyramid.py                    # 80/20 polarization + Treff PI
├── rehab/
│   ├── __init__.py
│   ├── return_to_run.py              # 5 阶返跑梯度 + R-R1/R-R2 阻断
│   └── load_pain_matrix.py           # 负荷-疼痛 2x2 决策
└── nutrition/
    ├── __init__.py
    ├── energy_balance.py             # TDEE / EA / REDs 三档
    ├── macros.py                     # CHO/PRO/FAT 周期化
    └── fueling.py                    # 长距离补给 + 警示
```

### A.2 schema 增表（已完成）

`training/storage/schema.sql` **末尾追加** 8 张表：
- `session_track_points`（GPS+海拔+HR+速度+步频逐秒）
- `session_gait`（垂直振幅/触地时间/左右平衡/步长汇总）
- `injury_registry`（结构化伤病）
- `pain_log`（VAS 时间序列）
- `rehab_log`（康复处方执行）
- `nutrition_intake`（摄入流水）
- `fueling_log`（补给计划 vs 实际）
- `thresholds_history`（LT/CV/VDOT 学习轨迹）

`training/storage/db.py:_migrate` 新增 5 个 ALTER：
- `sessions.rpe`, `sessions.has_track_points`, `sessions.has_gait`
- `athlete_checkins.session_rpe`, `athlete_checkins.session_id`

### A.3 athlete_config v2（已完成）

迁移脚本：`scripts/migrate_athlete_config_v2.py`（幂等，含 `--dry-run`）

实测从 v1 迁移结果：
- `_schema_version: 2`
- `injuries[]` 反推：`L_knee III post-op`（2025-10-23 onset, 2025-11-10 surgery, stage=4）+ `lower_back I`（VAS=2）
- `zones`：Karvonen 自动生成 Z1<126/Z2<137/Z3<149/Z4<161/Z5<173
- `ffm_kg=57.2`, `pal=1.55`, `sweat_rate_ml_per_h=800`, `gi_tolerance_cho_g_per_h=60`

### A.4 FIT GPS+步态解析（已完成）

`fit_parser.py` 新增 `extract_track_points()` + `aggregate_gait()`：
- 处理 semicircle→degree 坐标转换
- 提取：lat / lon / altitude / hr / speed_mps / cadence / distance / vertical_oscillation / ground_contact_time / stance_time_balance / step_length / vertical_ratio

回填脚本：`scripts/reparse_fit_v2.py`（断点续传，按 `has_track_points` / `has_gait` 标志增量）

实测 3 场样本（2026-04 杭州跑）：
- `track_points`: 9968 / 9983 行 altitude 非空（99.85% 覆盖）
- `track_points`: 9977 / 9983 行 speed 非空（99.94% 覆盖）
- `session_gait` 3 场样本：avg_vertical_oscillation 74.63mm / avg_ground_contact_time 224.25ms / avg_step_length 1007.26mm / avg_vertical_ratio 7.4%

### A.5 RPE 字段（已就位）

DB 已加：`sessions.rpe`、`athlete_checkins.session_rpe`、`athlete_checkins.session_id`。
UI 录入入口留到阶段 C 与可视化重做一并完成（避免与产品端的 `/api/v1/checkins` 冲突）。

### A.6 三学科核心模块（已完成）

| 模块 | 入口函数 | 输出 |
|---|---|---|
| `training/load_model.py` | `compute_load_profile(series)` | LoadProfile |
| `training/pyramid.py` | `polarization_check(z1..z5)` | PolarizationCheck |
| `rehab/return_to_run.py` | `assess_return_to_run(injury, ...)` | ReturnToRunStage |
| `rehab/load_pain_matrix.py` | `classify_load_pain(load, vas_delta)` | "safe / load_only / pain_only / danger / neutral" |
| `nutrition/energy_balance.py` | `energy_balance_report(profile, age, hr_tss, intake)` | EnergyBalanceReport |
| `nutrition/macros.py` | `macros_target(weight, hr_tss, long_session)` | dict |
| `nutrition/fueling.py` | `fueling_plan(duration_min, ...)` | dict |
| `common/confidence.py` | `score_confidence(...)` | DataConfidence |

理论锚点：Daniels VDOT、Friel PMC、Foster monotony/strain、Hulin/Gabbett ACWR、Seiler 80/20、Treff PI、ACSM/APTA RTS、van Melick KNGF（ACL post-op）、Mountjoy IOC RED-S 2023、Burke CHO periodization、Jeukendrup multi-transportable CHO。

---

## 用户验收 case（基于真实数据）

执行：`python -m scripts.science_demo`

### Case 1：Athlete Profile v2 加载
```
姓名: 泓兴, 体重: 65.0kg, FFM: 57.2kg
MaxHR: 173, RHR: 56, LTHR: 159
Zones: Z1<126, Z2<137, Z3<149, Z4<161, Z5<173
伤病数: 2
  - L_knee | grade=III post-op | stage=4 | VAS=1.0 | 术后 197 天
  - lower_back | grade=I | VAS=2.0
```
✓ v1 字符串伤病自动反推为结构化条目，术后天数动态计算。

### Case 2：训练负荷剖面（基于 daily_load 407 天数据）
```
{
  "ctl": 15.23,  "atl": 0.19,  "tsb": 15.04,
  "acwr_7_28": null,  "monotony": null,  "strain": null,
  "verdict": "peak"
}
```
✓ ATL=0.19 准确反映"近期没训练"；CTL=15 低水平体能基线。
**已知 issue**：低 CTL+正 TSB 应该叫 detrain 而非 peak（阶段 B 修）。

### Case 3：返跑阶段评估
输入：左膝术后 197 天 + today_vas=1 + recent_vas=[1,1,2] + weekly_hard_min=10
```
{ "stage": 5, "today_action": "advance",
  "do": ["今日按阶段 5 执行", "记录晨痛 VAS"],
  "avoid": ["跨阶段尝试比赛配速"] }
```
✓ 术后 >180 天解除 R-R1 阻断；近 3 课 VAS≤2 → advance；逻辑正确。

### Case 4：能量平衡（hr_tss=60，摄入 2400 kcal）
```
{
  "tdee_kcal": 3048,  "exercise_kcal": 624,
  "ea_kcal_per_kg_ffm": 31.0,  "reds_flag": "yellow",
  "macros_target": { "cho_g": 455, "pro_g": 117, "fat_g": 65 },
  "notes": [
    "能量可用性偏低（30-45）— 黄灯，关注连续 3-7 天趋势",
    "当前有伤情且能量不足，骨骼/软组织修复将受影响"
  ]
}
```
✓ 60 hr_tss × 65 kg × 0.16 = 624 kcal 与生理预期一致；REDs 黄灯触发；伤情×能量不足联合警告。

### Case 5：FIT 解析（杭州市跑步 20260406）
```
sample track: lat=30.3008755 lon=120.23208 hr=84
sample 1000s: lat=30.3029112 hr=147 altitude_m=25.0 speed_mps=3.214 cadence=95
gait: vertical_oscillation=74.63mm, ground_contact_time=224.25ms,
      step_length=1007.26mm, vertical_ratio=7.4%
```
✓ GPS 坐标杭州市区准确，海拔 22-26m 起伏合理，步态参数齐全。

### Case 6：数据可信度评估（当前状态）
```
score=0.15  level=low
missing=['training_load', 'morning_checkin']
stale=['hrv', 'rhr', 'sleep', 'session']
```
✓ 准确暴露当前数据陈旧（最后训练 2026-04-06，距今 ~7 周），所有同步信号均 stale。
这恰恰说明系统已能识别"建议不可信赖"的状态——未来 LLM 输出会带 confidence=0.15 + 缺口清单。

---

## 测试覆盖

| 文件 | 用例数 | 覆盖 |
|---|---|---|
| `test_science_load_model.py` | 10 | ACWR/Monotony/Strain/EWMA/verdict |
| `test_science_pyramid.py` | 5 | 4 种极化判定 + PI |
| `test_science_return_to_run.py` | 6 | 进阶/退阶/术后阻断/VAS 阻断 |
| `test_science_nutrition.py` | 9 | TDEE/EA/REDs/macros/fueling |
| `test_science_profile_confidence.py` | 5 | v1/v2 加载 + 置信度高/低/陈旧 |
| **合计** | **35** | 全部 PASSED |
| 全套件 | **138** | 含原有 103，零回归 |

---

## 已知遗留（阶段 B/C 处理）

1. LoadProfile verdict 在低 CTL+正 TSB 误判为 peak（应叫 detrain）
2. RPE 录入 UI 入口未实现
3. `interpretations.py` 解读逻辑还未迁入 `science/*/prescriptions.py`
4. 课表生成器 `planning/generator.py` 还未引用 science 输出
5. coach_recommendations 还在用旧的规则引擎（阶段 B 升级 LLM few-shot）
6. 戈21相关常量保留在 `config.py`（GOBI_RACE_DATE）便于产品端兼容，新功能不引用

---

## 部署信息（待执行）

- 当前分支：`feature/science-viz-stage-a`
- 远端：`origin/feature/science-viz-stage-a`
- 待操作：rebase main → 合并 → `bash scripts/deploy_aliyun.sh`

部署后线上验证：
1. `curl http://101.37.238.138:8081/training/api/v1/today` 仍返回 200
2. SSH 到服务器：`sqlite3 /opt/training-system/training.db ".tables"` 含新增 8 表
3. 服务器跑 `python -m scripts.migrate_athlete_config_v2` 升级线上 athlete_config（如有）
4. 服务器跑 `python -m scripts.reparse_fit_v2 --since 2025-04-01` 全量回填 GPS / 步态
