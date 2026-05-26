# 阶段 C 验收报告：可视化重构 + 三级页面

**分支**：`feature/science-viz-stage-c`
**完成时间**：2026-05-26
**测试结果**：161 passed（与阶段 B 持平，零回归；UI 通过本地冒烟）

---

## 交付物

### C.1 引入前端库 + api_v2 路由

- `training/web/api_v2.py`（新建）：
  - `GET /api/v2/today` → SciencePrescription（决策台数据源）
  - `GET /api/v2/session/{id}/full` → 单次全息（meta + 抽样 track + laps + zones + gait）
  - `GET /api/v2/trends/load?days=N` → PMC 时间序列
  - `GET /api/v2/trends/zones?weeks=N` → 周心率分区堆叠
  - `GET /api/v2/sessions/recent?limit=N` → 最近训练摘要
- `training/web/app.py`：`include_router(api_v2_router, prefix="/api/v2")` + 3 条 HTML 路由（`/v2/today`、`/v2/sessions/{id}`、`/v2/trends`）
- 静态资源 CDN：ECharts 5.5.0、Leaflet 1.9.4
- `training/web/static/v2/pv2.css`：CSS namespace `.pv2-*`，零冲突

### C.2 一级页面：决策台 v2

`templates/professional_v2_today.html` + `static/v2/pv2_today.js`

布局区块：
1. 顶栏：品牌 + v2 导航 + **数据可信度灯**（绿/黄/红）
2. **决策卡**：风险 pill（GO / CAUTION / HIGH RISK）+ verdict 标题 + 一句摘要（背景色随风险级别变化）
3. 三栏并排：训练负荷（CTL/ATL/TSB/ACWR/Mono + 训练建议）/ 康复风险（活跃伤情 + 今日动作 + 部位 prehab）/ 能量平衡（TDEE/EA/REDs pill + macros + 营养建议）
4. **PMC 长曲线**（90 天，dataZoom 可拖）+ **风险雷达**（6 维：ACWR/Monotony/Fatigue/Energy/Pain/Data Gap）
5. 最近训练表（点击 → 三级解剖页）
6. why 列表（可追溯依据，前 8 条）

### C.3 三级页面：单次全息解剖

`templates/professional_v2_session.html` + `static/v2/pv2_session.js`

布局区块：
1. 顶栏：返回决策台 + Session ID
2. **训练摘要卡**：日期 + 类型 + 11 维数据矩阵（距离/时长/HR/配速/步频/爬升/hr_TSS/HR Drift/EF/VO2max/Recovery）
3. **GPS 轨迹地图**（Leaflet + OSM）：配速色阶分段（5 色：红橙绿蓝紫对应不同配速带），起终点标记
4. **海拔剖面**（ECharts area chart，与时间轴联动）
5. **心率分区甜甜圈**（Z1-Z5 按时长饼图，鼠标悬浮显示分钟数+百分比）
6. **HR/配速/步频三轴时序**（ECharts dual-axis line，dataZoom 拖动缩放）
7. **步态雷达**（5 维：垂直振幅/触地时间/步长/垂直比/左右平衡）
8. **分圈表**（按 lap_index 列出每圈数据）

### C.4 二级页面：周月趋势

`templates/professional_v2_trends.html` + `static/v2/pv2_trends.js`

1. **训练负荷长曲线**（180 天）：daily TSS 柱图 + CTL/ATL/TSB 三线
2. **ACWR 风险带**：折线 + markArea（绿带 0.8-1.3 安全 / 红带 >1.5 高风险）+ markLine（基线 1.0）
3. **周心率分区堆叠**（12 周）：5 色堆叠柱状图（Z1-Z5），按周聚合

### C.5 边界遵守

| 文件 | 改动 |
|---|---|
| `training/web/app.py` | 仅追加 v2 路由，旧路由不动 |
| `training/web/api.py` / `api_*.py` | 不动（v2 是新增独立文件） |
| `style.css` | 不动（v2 用独立 `.pv2-*` namespace） |
| `templates/product_*.html` | 不动 |
| `training/storage/schema.sql` | 不动（阶段 A 已经在末尾追加完毕） |

---

## 用户验收 case（本地启动 + 冒烟）

```
GET /api/v2/today                 HTTP 200  返回 SciencePrescription JSON
GET /api/v2/trends/load?days=30   HTTP 200  返回 30 天 PMC 序列
GET /api/v2/sessions/recent       HTTP 200  返回最近 N 场摘要
GET /api/v2/session/656/full      HTTP 200  返回完整全息数据
GET /v2/today                     HTTP 200  渲染决策台 HTML
GET /v2/trends                    HTTP 200  渲染趋势页 HTML
GET /v2/sessions/656              HTTP 200  渲染全息解剖 HTML
```

---

## 已知局限（v2 之后再做）

1. 风险雷达的 6 维计算公式较粗，待引入历史 baseline 后调精
2. 决策卡未做"一键采纳/调整"按钮（需要落库写入路径，留 v3）
3. 营养页与伤病时间线 swimlane 未实现（C.4 之外的 28 张大图清单的 P1/P2 部分）
4. RPE 录入 UI 还未做（DB 字段已就位）
5. coach_recommendations 表的写入仍走 v1 规则引擎；v2 LLM payload 已构造好但实际 API 调用没接上

---

## 部署信息

- 当前分支：`feature/science-viz-stage-c`
- 待操作：rebase main → push → SSH 服务器 git pull → restart
