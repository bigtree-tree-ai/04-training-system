"""运动科学知识体系 — 训练学/康复学/营养学三大学科

每个学科子包结构：
- 输入信号定义（schemas）
- 核心算法（基于公开理论：Daniels/Friel/Magness/Bompa/Seiler/IOC/ACSM）
- 个体化参数读取（athlete_config v2）
- 可执行规则（结构化输出，便于规则引擎与 LLM few-shot 共用）

不依赖任何 product_* / accounts 模块，仅消费 storage 层的查询结果。
"""

__all__ = ["common", "training", "rehab", "nutrition"]
SCHEMA_VERSION = 2
