"""
专业数据解读文案系统 — 为所有关键训练指标提供中文专业解读

每个函数接收原始指标值，返回一段包含评级、解读和建议的专业文案字符串。
文案风格：简洁专业，适合在卡片下方以小字展示。
"""


def interpret_ctl(ctl: float) -> str:
    """CTL（慢性训练负荷）体能评级解读"""
    if ctl is None:
        return ""
    if ctl < 15:
        level = "恢复期"
        desc = "体能基础较低，处于训练恢复或起步阶段。建议逐步增加有氧训练量，每周增幅不超过10%。"
    elif ctl < 30:
        level = "入门水平"
        desc = "有氧基础正在建立，适合稳定执行基础有氧计划。保持规律训练，避免突然加量。"
    elif ctl < 50:
        level = "中等水平"
        desc = "有氧基础正在构建中，可以开始引入节奏跑和tempo训练。当前体能支撑半马备赛。"
    elif ctl < 70:
        level = "优秀水平"
        desc = "体能储备充足，可以承受较大训练负荷。适合进入专项强化阶段，加入间歇和长距离。"
    else:
        level = "精英水平"
        desc = "体能处于高水平，具备全马竞赛体能基础。注意监控疲劳累积，防止过度训练。"
    return f"CTL {ctl:.1f} -- {level}。{desc}"


def interpret_tsb(tsb: float) -> str:
    """TSB（训练压力平衡）状态解读"""
    if tsb is None:
        return ""
    if tsb < -30:
        level = "过度训练风险"
        desc = "身体严重疲劳，伤病风险极高。立即降低训练量50%以上，安排2-3天完全休息。"
        color = "danger"
    elif tsb < -10:
        level = "训练刺激区"
        desc = "处于功能性过量训练区间，体能正在积累。保持当前负荷1-2周后安排减量周恢复。"
        color = "warning"
    elif tsb < 5:
        level = "正常训练"
        desc = "训练负荷与恢复基本平衡。可以正常执行训练计划。"
        color = "ok"
    elif tsb < 15:
        level = "最佳竞赛状态"
        desc = "身体恢复充分且保持了训练适应，处于理想的比赛状态窗口。适合安排测试赛或关键训练。"
        color = "success"
    elif tsb < 25:
        level = "恢复充分"
        desc = "身体处于良好恢复状态。如非赛前减量期，可以考虑适当增加训练刺激。"
        color = "ok"
    else:
        level = "失训风险"
        desc = "休息时间过长，体能可能开始下降。建议尽快恢复规律训练，从低强度有氧开始。"
        color = "warning"
    return f"TSB {tsb:.1f} -- {level}。{desc}"


def interpret_acwr(acwr: float) -> str:
    """ACWR（急慢性负荷比）安全区间解读"""
    if acwr is None:
        return ""
    if acwr < 0.8:
        level = "训练不足"
        desc = "近期训练量明显低于长期水平，体能可能下降。逐步增加训练量至安全区间。"
        color = "warning"
    elif acwr <= 1.3:
        level = "安全区间"
        desc = "急慢性负荷比处于理想范围，伤病风险较低。可以正常执行训练计划。"
        color = "ok"
    elif acwr <= 1.5:
        level = "警告区间"
        desc = "近期加量过快，伤病风险上升。建议下周降低训练量10-20%，增加恢复训练。"
        color = "warning"
    else:
        level = "危险区间"
        desc = "急慢性负荷比过高，伤病风险显著增加。立即降低训练强度和量，安排额外休息日。"
        color = "danger"
    return f"ACWR {acwr:.2f} -- {level}。{desc}"


def interpret_vo2max(vo2max: float) -> str:
    """VO2max等级解读（男性30-39岁标准）+ VDOT对应成绩预测"""
    if vo2max is None:
        return ""

    # 等级评定
    if vo2max < 33:
        level = "较差"
    elif vo2max < 36:
        level = "低于平均"
    elif vo2max < 42:
        level = "中等"
    elif vo2max < 46:
        level = "良好"
    elif vo2max < 52:
        level = "优秀"
    else:
        level = "精英"

    # VDOT对应预测成绩（简化查表）
    predictions = _vdot_predictions(vo2max)

    result = f"VO2max {vo2max:.1f} ml/kg/min -- {level}水平(男性30-39岁)。"
    if predictions:
        result += f" VDOT预测: 5K {predictions['5k']}, 10K {predictions['10k']}, 半马 {predictions['hm']}, 全马 {predictions['fm']}。"
    return result


def _vdot_predictions(vo2max: float) -> dict:
    """根据VO2max简化预测各距离成绩"""
    # 简化的VDOT查表（关键节点线性插值）
    table = [
        (30, "30:40", "63:46", "2:21:04", "4:49:17"),
        (35, "27:00", "56:03", "2:04:13", "4:16:03"),
        (40, "24:08", "50:03", "1:50:59", "3:49:45"),
        (45, "21:50", "45:16", "1:40:20", "3:28:26"),
        (50, "19:57", "41:21", "1:31:35", "3:10:49"),
        (55, "18:23", "38:06", "1:24:18", "2:56:01"),
        (60, "17:03", "35:22", "1:18:09", "2:43:25"),
    ]
    # 找最近的区间
    for i, (v, t5k, t10k, thm, tfm) in enumerate(table):
        if vo2max < v:
            if i == 0:
                return {"5k": t5k, "10k": t10k, "hm": thm, "fm": tfm}
            # 返回较近的
            prev = table[i - 1]
            return {"5k": prev[1], "10k": prev[2], "hm": prev[3], "fm": prev[4]}
    last = table[-1]
    return {"5k": last[1], "10k": last[2], "hm": last[3], "fm": last[4]}


def interpret_training_status(status: str) -> str:
    """训练状态的中文解读和建议"""
    if not status:
        return ""

    status_map = {
        "Peaking": {
            "cn": "巅峰状态",
            "desc": "身体状态处于最佳，适合参加比赛或进行测试训练。",
            "advice": "抓住这个窗口期安排重要训练或比赛。"
        },
        "Productive": {
            "cn": "高效训练",
            "desc": "训练负荷适当，体能在稳步提升中。",
            "advice": "继续当前训练节奏，保持训练一致性。"
        },
        "Maintaining": {
            "cn": "维持状态",
            "desc": "训练量足够维持当前体能水平，但提升空间有限。",
            "advice": "考虑增加训练变化性或适度提高强度。"
        },
        "Recovery": {
            "cn": "恢复期",
            "desc": "身体正在从高负荷训练中恢复。",
            "advice": "以低强度有氧和拉伸为主，确保充分恢复。"
        },
        "Unproductive": {
            "cn": "低效训练",
            "desc": "训练负荷未能有效刺激体能提升，可能是强度不够或恢复不足。",
            "advice": "检查训练计划结构，确保有足够的强度变化和恢复时间。"
        },
        "Detraining": {
            "cn": "体能下降",
            "desc": "训练频率或量不足，体能开始流失。",
            "advice": "尽快恢复规律训练，从当前体能60%的强度开始。"
        },
        "Overreaching": {
            "cn": "过量训练",
            "desc": "训练负荷超出恢复能力，短期可能有提升但需警惕。",
            "advice": "计划一个减量周(负荷降低40-60%)，增加睡眠和营养摄入。"
        },
        "Strained": {
            "cn": "过度疲劳",
            "desc": "持续高负荷导致身体严重疲劳，伤病风险极高。",
            "advice": "立即安排3-5天完全休息或仅做轻松散步，必要时咨询运动医学专家。"
        },
    }

    info = status_map.get(status)
    if info:
        return f"{info['cn']}({status}) -- {info['desc']}{info['advice']}"
    return f"训练状态: {status}"


def interpret_hr_drift(drift_pct: float) -> str:
    """心率漂移率解读 -- 反映有氧耐力水平"""
    if drift_pct is None:
        return ""
    if drift_pct < 3:
        level = "优秀"
        desc = "有氧耐力扎实，心血管系统高效。当前有氧基础足以支撑长距离训练。"
    elif drift_pct < 5:
        level = "正常"
        desc = "有氧耐力处于正常水平。继续积累有氧跑量，心率漂移会进一步改善。"
    elif drift_pct < 10:
        level = "有氧不足"
        desc = "心率漂移偏高，有氧基础需要加强。建议增加Z2心率区间的长距离慢跑。"
    else:
        level = "需要关注"
        desc = "心率漂移过大，可能是脱水、睡眠不足、有氧基础薄弱等原因。检查恢复状况并增加基础有氧训练。"
    return f"心率漂移 {drift_pct:.1f}% -- {level}。{desc}"


def interpret_marathon_shape(score: float) -> str:
    """马拉松专项准备度评分解读 (0-100)"""
    if score is None:
        return ""
    if score < 20:
        level = "起步阶段"
        desc = "马拉松准备刚刚开始，需要全面提升有氧基础、长距离能力和跑量。"
    elif score < 40:
        level = "基础构建"
        desc = "正在打基础，重点积累周跑量和长距离。建议每周至少3-4次有氧跑。"
    elif score < 60:
        level = "稳步提升"
        desc = "基础逐步巩固，可以开始引入马拉松配速跑和节奏跑训练。"
    elif score < 80:
        level = "备赛良好"
        desc = "马拉松专项能力较强，继续保持长距离训练并注意赛前减量。"
    else:
        level = "竞赛就绪"
        desc = "马拉松准备充分，身体状态适合参赛。进入赛前减量期，保持信心。"
    return f"马拉松准备度 {score:.0f}/100 -- {level}。{desc}"


def interpret_recovery_score(score: int) -> str:
    """恢复指数解读 (0-100)"""
    if score is None:
        return ""
    if score < 20:
        level = "严重疲劳"
        desc = "身体恢复严重不足，伤病和过度训练风险极高。建议完全休息1-2天，关注睡眠和营养。"
        color = "danger"
    elif score < 40:
        level = "疲劳"
        desc = "恢复不充分，只适合低强度恢复跑或交叉训练。避免任何高强度训练。"
        color = "warning"
    elif score < 60:
        level = "一般"
        desc = "恢复中等，可以进行中等强度训练，但不建议安排关键训练或比赛。"
        color = "ok"
    elif score < 80:
        level = "良好"
        desc = "恢复状况良好，可以正常执行训练计划，包括较高强度训练。"
        color = "ok"
    else:
        level = "充分恢复"
        desc = "身体状态极佳，适合安排关键训练、测试跑或比赛。"
        color = "success"
    return f"恢复指数 {score}/100 -- {level}。{desc}"


def interpret_zone_distribution(easy_pct: float) -> str:
    """心率区间分布解读 -- 80/20极化训练原则"""
    if easy_pct is None:
        return ""
    if easy_pct >= 80:
        level = "极化达标"
        desc = f"轻松跑(Z1+Z2)占比{easy_pct:.0f}%，符合80/20极化训练原则。训练结构合理，有利于有氧基础建设和伤病预防。"
    elif easy_pct >= 70:
        level = "接近达标"
        desc = f"轻松跑占比{easy_pct:.0f}%，略低于80%目标。建议减少中等强度(Z3)训练，将部分训练替换为纯Z2有氧跑。"
    elif easy_pct >= 60:
        level = "强度偏高"
        desc = f"轻松跑仅占{easy_pct:.0f}%，中高强度训练过多。长期如此会导致疲劳累积和有氧基础不稳。大幅增加轻松跑比例。"
    else:
        level = "严重失衡"
        desc = f"轻松跑仅占{easy_pct:.0f}%，训练强度分布严重失衡。几乎所有训练都太快了，这会限制进步并增加伤病风险。"
    return f"极化训练 -- {level}。{desc}"


def interpret_comparison_metric(name: str, diff_pct: float, trend: str) -> str:
    """环比指标变化的专业解读"""
    if diff_pct is None:
        return ""

    # 根据指标名称给出不同解读
    metric_context = {
        "跑量": {
            "up_good": True,
            "up_desc": "跑量增长有助于有氧基础积累，但注意单周增幅不超过10%。",
            "down_desc": "跑量减少可能是休息调整，也需检查是否因伤病或动力不足。",
        },
        "TSS负荷": {
            "up_good": None,  # 中性
            "up_desc": "训练负荷增加说明训练刺激加大，注意配合足够恢复。",
            "down_desc": "负荷降低可能是减量周的正常安排，或需要检查训练执行率。",
        },
        "平均心率": {
            "up_good": False,
            "up_desc": "同等配速下心率上升可能暗示疲劳累积、脱水或有氧退步。",
            "down_desc": "心率下降通常是有氧能力提升的信号，同等配速更轻松。",
        },
        "轻松配速": {
            "up_good": False,  # 配速秒数上升=变慢
            "up_desc": "轻松跑配速变慢，可能是天气炎热、疲劳或需要检查训练负荷。",
            "down_desc": "轻松跑配速提升，表明有氧能力在进步。",
        },
        "平均步频": {
            "up_good": True,
            "up_desc": "步频提升通常意味着跑姿经济性改善，有利于减少冲击力。",
            "down_desc": "步频下降可能是疲劳或步幅加大的信号，关注跑姿变化。",
        },
        "心率漂移": {
            "up_good": False,
            "up_desc": "心率漂移增大说明有氧耐力可能退步，需要更多Z2长距离训练。",
            "down_desc": "心率漂移减小是有氧耐力提升的直接证据，继续保持。",
        },
    }

    ctx = metric_context.get(name)
    if ctx:
        if diff_pct > 0:
            desc = ctx["up_desc"]
        else:
            desc = ctx["down_desc"]
    else:
        if diff_pct > 0:
            desc = f"{name}较上期上升。"
        else:
            desc = f"{name}较上期下降。"

    abs_pct = abs(diff_pct)
    if abs_pct < 3:
        magnitude = "变化不大，基本持平"
    elif abs_pct < 10:
        magnitude = "小幅变化"
    elif abs_pct < 20:
        magnitude = "明显变化"
    else:
        magnitude = "大幅变化"

    arrow = "^" if trend == "up" else ("v" if trend == "down" else "-")
    return f"{name} {arrow} {diff_pct:+.1f}% ({magnitude})。{desc}"
