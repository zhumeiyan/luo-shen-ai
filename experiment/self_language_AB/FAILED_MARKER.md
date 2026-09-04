# 失败实验归档

本目录包含 self_language_AB 实验数据。

该实验于 2026-09-04 初判为 PASS，经复审确认失败：
- NEG/POS 两组内部状态在 50 tick 内未变化
- 句子差异来自 LLM temperature=0.85 随机采样，非洛神内部状态驱动
- 违反项目原则："禁止用随机数制造假活"

revert commits: d468106 + 83b156f
hash chain correction: record_hash ccd4afc8026e57887c117e10275d0e85
