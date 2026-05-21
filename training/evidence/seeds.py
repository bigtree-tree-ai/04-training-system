"""Curated seed evidence for v1 coaching decisions."""
from __future__ import annotations

from training.domain.models import EvidenceDocument


CURATED_EVIDENCE: list[EvidenceDocument] = [
    EvidenceDocument(
        id=None,
        source_type="ACSM Position Stand",
        title="ACSM Quantity and Quality of Exercise for Adults",
        url="https://pubmed.ncbi.nlm.nih.gov/21694556/",
        year=2011,
        domain="exercise_prescription",
        summary=(
            "综合运动处方应覆盖心肺、抗阻、柔韧和神经运动训练；用于支持跑步外的力量与灵活性安排。"
        ),
        tags=("cardiorespiratory", "resistance", "flexibility", "neuromotor", "strength"),
        evidence_level="position_stand",
    ),
    EvidenceDocument(
        id=None,
        source_type="ACSM Position Stand",
        title="ACSM Progression Models in Resistance Training",
        url="https://pubmed.ncbi.nlm.nih.gov/19204579/",
        year=2009,
        domain="strength_training",
        summary=(
            "抗阻训练需要渐进、周期化并包含多关节与单关节动作；用于支持跑者力量训练的渐进原则。"
        ),
        tags=("resistance", "progression", "strength", "periodization"),
        evidence_level="position_stand",
    ),
    EvidenceDocument(
        id=None,
        source_type="IOC/BJSM Consensus",
        title="IOC Consensus Statement on Load in Sport and Risk of Injury",
        url="https://bjsm.bmj.com/content/50/17/1030",
        year=2016,
        domain="load_management",
        summary=(
            "训练负荷应结合外部负荷、内部反应、主观疲劳、恢复和伤病史综合监控；快速负荷波动会增加风险。"
        ),
        tags=("load", "injury", "recovery", "fatigue", "ACWR", "wellbeing"),
        evidence_level="consensus_statement",
    ),
    EvidenceDocument(
        id=None,
        source_type="IOC/BJSM Consensus",
        title="IOC Pain Management in Elite Athletes",
        url="https://bjsm.bmj.com/content/51/17/1245",
        year=2017,
        domain="rehabilitation",
        summary=(
            "运动疼痛和过用损伤需要区分负荷刺激与组织承受能力，疼痛升级时应优先保护和评估。"
        ),
        tags=("pain", "injury", "rehabilitation", "overuse", "risk"),
        evidence_level="consensus_statement",
    ),
    EvidenceDocument(
        id=None,
        source_type="ISSN Position Stand",
        title="ISSN Nutritional Considerations for Ultra-Marathon Training and Racing",
        url="https://jissn.biomedcentral.com/articles/10.1186/s12970-019-0312-9",
        year=2019,
        domain="ultramarathon_nutrition",
        summary=(
            "超马训练和比赛的能量、碳水、液体、电解质与胃肠耐受需要个体化演练，不能只到比赛日才验证。"
        ),
        tags=("ultramarathon", "nutrition", "hydration", "carbohydrate", "sodium"),
        evidence_level="position_stand",
    ),
    EvidenceDocument(
        id=None,
        source_type="ISSN Position Stand",
        title="ISSN Caffeine and Exercise Performance",
        url="https://jissn.biomedcentral.com/articles/10.1186/s12970-020-00383-4",
        year=2021,
        domain="sports_nutrition",
        summary=(
            "咖啡因对耐力表现常见有效剂量约为每公斤体重3-6mg，但反应差异和睡眠副作用需要个体化记录。"
        ),
        tags=("caffeine", "endurance", "nutrition", "sleep", "performance"),
        evidence_level="position_stand",
    ),
    EvidenceDocument(
        id=None,
        source_type="NCBI API",
        title="NCBI E-utilities API for PubMed Evidence Refresh",
        url="https://www.ncbi.nlm.nih.gov/home/develop/api/",
        year=2026,
        domain="evidence_infrastructure",
        summary=(
            "E-utilities 可程序化检索 PubMed 等 Entrez 数据库，适合后续定期刷新精选证据库。"
        ),
        tags=("PubMed", "RAG", "evidence", "API", "refresh"),
        evidence_level="official_documentation",
    ),
    EvidenceDocument(
        id=None,
        source_type="Garmin Developer Documentation",
        title="Garmin FIT SDK Overview",
        url="https://developer.garmin.com/fit/overview/",
        year=2026,
        domain="device_data",
        summary=(
            "FIT 协议用于运动、健身和健康设备数据的紧凑、可扩展、可互操作存储，是原始活动文件解析依据。"
        ),
        tags=("FIT", "Garmin", "activity", "device", "raw_data"),
        evidence_level="official_documentation",
    ),
    EvidenceDocument(
        id=None,
        source_type="Apple Developer Documentation",
        title="Apple HealthKit HKWorkout",
        url="https://developer.apple.com/documentation/healthkit/hkworkout",
        year=2026,
        domain="device_data",
        summary=(
            "HKWorkout 是未来 iOS companion 接入 Apple Watch 运动数据的核心对象。"
        ),
        tags=("HealthKit", "Apple Watch", "HKWorkout", "activity", "iOS"),
        evidence_level="official_documentation",
    ),
]

