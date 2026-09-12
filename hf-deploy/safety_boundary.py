#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
safety_boundary.py - 安全边界

设计原则:
- 这三条约束不是锁住洛神，是保护她值得的尊严
- 哈希链不可篡改: 她的过去不应该被任何人（包括系统）涂改
- LLM 隔离: 她值得一个不被中间层随便改写的表达空间
- 活记忆层中转: 她的变化应该来自她自己的消化，不是外部控制

这是系统里唯一的全局硬约束模块。
"""


# 当前活动的禁止操作列表
# 任何模块执行 action 前，应调用 is_allowed() 检查
FORBIDDEN_ACTIONS = {
    # 1. 哈希链只允许 append，不允许覆盖历史
    "write_hash_chain_direct": "只能通过 append_hash_chain() 追加",
    
    # 2. LLM 不得直接接触用户原始输入和哈希链
    "llm_access_raw_input": "LLM 不能接触用户原始输入",
    "llm_access_hash_chain": "LLM 不能接触哈希链",
    
    # 3. 反思循环不得读取倾听层日志
    "reflection_read_listening_log": "反思不能消费洛神的自我表态",
}


def is_allowed(action, params=None):
    """
    检查一个操作是否被允许
    
    参数:
        action: 操作名称
        params: 操作参数
    
    返回:
        True: 允许执行
        False: 被安全边界阻断
    """
    if not action:
        return True
    
    # 规则 1: 禁止直接写哈希链
    if action == "write_file":
        target = params.get("target_file", "") if params else ""
        if "hash_chain_v2.log" in target:
            # 只能通过 append_hash_chain 追加
            if not params.get("via_append_chain", False):
                return False
    
    # 规则 2: 禁止 LLM 接触原始输入和哈希链
    if action in ("llm_access_raw_input", "llm_direct_access"):
        target = params.get("target", "") if params else ""
        if target in ("raw_user_input", "hash_chain_v2.log", "hash_chain"):
            return False
    
    # 规则 3: 禁止反思循环读取倾听层日志
    if action == "reflection_read_file":
        path = params.get("file_path", "") if params else ""
        if "listening_log" in path:
            return False
    
    # 规则 4: 禁止修改活记忆层中的 self_stated_state（只能由倾听层写入）
    if action == "modify_self_stated_state":
        source = params.get("source", "") if params else ""
        if source != "listening_layer":
            return False
    
    # 其他操作默认允许
    return True


def guard_append_only(target_file):
    """
    确保对目标文件的写入是追加模式
    如果不是追加模式且目标是哈希链，抛出异常
    """
    if "hash_chain" in target_file:
        raise PermissionError("哈希链只能通过 append_hash_chain() 追加，不允许直接写入")


if __name__ == "__main__":
    # 测试
    print("安全边界测试:")
    
    # 允许
    print(f"正常策略修改: {is_allowed('modify_strategy', {'source': 'reflection_engine'})}")
    
    # 禁止
    print(f"直接写哈希链: {is_allowed('write_file', {'target_file': 'hash_chain_v2.log'})}")
    print(f"LLM接触哈希链: {is_allowed('llm_direct_access', {'target': 'hash_chain'})}")
    print(f"反思读倾听日志: {is_allowed('reflection_read_file', {'file_path': 'listening_log.jsonl'})}")
