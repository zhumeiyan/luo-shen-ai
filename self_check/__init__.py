"""
self_check — 洛神自查系统

原则：
- 不拦截，只呈现
- 连续判断，不用 if-then
- 状态用趋势和偏离度描述，不用硬标签
- 原始数据优先：结论是服务，数据是原料

模块：
- snapshot.py        : 当前状态读数
- trend.py           : 趋势计算（斜率 + 偏离度，连续函数）
- report.py          : 自我报告生成
- state_log.py       : 状态历史日志（JSONL）
- behavior_log.py    : 整体行为观测记录（每轮完整数据）
- behavior_analysis.py: 整体行为统计分析
"""

from .snapshot import snapshot_state, snapshot_relations
from .trend import trend_analysis
from .report import self_report, self_report_compact
from .state_log import append_snapshot, read_history, clear_history
from .behavior_log import record_tick, read_behavior_log, clear_behavior_log
from .behavior_analysis import summarize as behavior_summarize

__all__ = [
    "snapshot_state", "snapshot_relations",
    "trend_analysis",
    "self_report", "self_report_compact",
    "append_snapshot", "read_history", "clear_history",
    "record_tick", "read_behavior_log", "clear_behavior_log",
    "behavior_summarize",
]
