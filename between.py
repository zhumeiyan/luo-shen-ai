#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
between.py —— 差异原语（Difference Primitive）C 坐标

主体: (σ, g, h)
  σ = (a + b) / 2       （中心）
  g = b - a             （差）
  h = b.bias - a.bias   （偏差差）

投影（恒等）:
  a = σ - g/2
  b = σ + g/2

g 由 a、b 决定。不是独立状态。投影公式必须恒等成立。

每步:
  1. 投影: a = σ - g/2, b = σ + g/2
  2. 规则作用 + bias: a_new = rule_a(a) + a.bias, b_new = rule_b(b) + b.bias
  3. 重新读出: g = b_new - a_new,  σ = (a_new + b_new) / 2
  4. bias 带 leak: a.bias = leak * a.bias + gain * g,  b.bias = leak * b.bias - gain * g
  5. h = b.bias - a.bias
"""


class Stateful:
    """
    有状态的东西。但在此 C 坐标版本中，trajectory 由 Between 统一写入，
    不调用 step()。仅保留 bias 属性作为状态容器。
    """
    def __init__(self, initial):
        self.trajectory = [float(initial)]
        self.bias = 0.0


class Difference:
    """在 C 坐标版本中，Difference 不维护独立状态，仅作为接口兼容保留。"""
    def __init__(self):
        self.trajectory = []

    def read(self, a, b):
        g = b.trajectory[-1] - a.trajectory[-1]
        self.trajectory.append(float(g))
        return g


class Between:
    """
    C 坐标: 主体为 (σ, g, h)。a、b 为投影。
    """
    def __init__(self, a, b, leak=0.9, gain=0.1):
        self.a = a
        self.b = b
        self.leak = leak
        self.gain = gain
        # C 坐标主状态
        self.sigma = (a.trajectory[-1] + b.trajectory[-1]) / 2.0
        self.g = b.trajectory[-1] - a.trajectory[-1]
        self.h = b.bias - a.bias
        # 记录
        self.sigma_trajectory = [self.sigma]
        self.g_trajectory = []
        self.h_trajectory = []

    def step(self, rule_a, rule_b):
        # 1. 投影
        a_val = self.sigma - self.g / 2.0
        b_val = self.sigma + self.g / 2.0

        # 2. 规则作用 + bias
        a_raw = rule_a([a_val])
        b_raw = rule_b([b_val])
        a_new = a_raw + self.a.bias
        b_new = b_raw + self.b.bias

        # 3. 重新读出 C 坐标
        self.sigma = (a_new + b_new) / 2.0
        self.g = b_new - a_new

        # 4. bias 带 leak
        self.a.bias = self.leak * self.a.bias + self.gain * self.g
        self.b.bias = self.leak * self.b.bias - self.gain * self.g
        self.h = self.b.bias - self.a.bias

        # 5. 写入轨迹
        self.a.trajectory.append(float(a_new))
        self.b.trajectory.append(float(b_new))
        self.sigma_trajectory.append(float(self.sigma))
        self.g_trajectory.append(float(self.g))
        self.h_trajectory.append(float(self.h))


# ── 跑 20000 步 C 坐标 flat×flat ───────────────────────────────────────────

if __name__ == "__main__":
    flat = lambda t: t[-1]

    a = Stateful(0.0)
    b = Stateful(1.0)
    bet = Between(a, b, leak=0.9, gain=0.1)

    for _ in range(20000):
        bet.step(flat, flat)

    print("=== C 坐标 flat×flat 20000 步 ===")
    print()
    print('a.trajectory[-1]:', repr(a.trajectory[-1]))
    print('b.trajectory[-1]:', repr(b.trajectory[-1]))
    print('σ.trajectory[-1]:', repr(bet.sigma_trajectory[-1]))
    print('g.trajectory[-1]:', repr(bet.g_trajectory[-1]))
    print()

    # 投影恒等验证
    sigma_last = bet.sigma_trajectory[-1]
    g_last = bet.g_trajectory[-1]
    a_last = a.trajectory[-1]
    b_last = b.trajectory[-1]

    proj_a = sigma_last - g_last / 2.0
    proj_b = sigma_last + g_last / 2.0
    g_from_pos = b_last - a_last

    # 用最新一步的 σ 和 g（轨迹的最后一个元素）验证
    print('投影恒等验证:')
    print('  a - (σ - g/2):', repr(a_last - proj_a))
    print('  b - (σ + g/2):', repr(b_last - proj_b))
    print('  g - (b - a):  ', repr(g_last - g_from_pos))
    print()

    # L1: det = leak = 0.9 (规则积=1, det=1*0.9)
    print('L1: det = 规则积 × leak = 1 × 0.9 =', 1 * bet.leak)
    print()

    # L2: a.bias + b.bias
    print('L2: a.bias + b.bias =', repr(a.bias + b.bias))
    print()

    # L3: 投影恒等三项全 == 0.0
    l3a = a_last - proj_a
    l3b = b_last - proj_b
    l3c = g_last - g_from_pos
    print('L3 投影恒等:')
    print('  a - (σ - g/2):', repr(l3a), '== 0.0 ?', l3a == 0.0)
    print('  b - (σ + g/2):', repr(l3b), '== 0.0 ?', l3b == 0.0)
    print('  g - (b - a):  ', repr(l3c), '== 0.0 ?', l3c == 0.0)
    print()

    # L4: g 唯一值集合大小
    g_last2k = bet.g_trajectory[-2000:]
    g_unique = sorted(set(g_last2k), key=lambda x: (round(x, 15), x))
    print('L4: g 唯一值集合（大小=' + str(len(g_unique)) + '）:')
    for v in g_unique:
        print('  ', repr(v))
    print()

    # L5: g 零交叉次数
    g_zero_cross = sum(1 for i in range(1, len(bet.g_trajectory))
                       if bet.g_trajectory[i-1] * bet.g_trajectory[i] < 0)
    print('L5: g 零交叉次数:', g_zero_cross)
    print()

    # 末 20 步 g 值
    print('g.trajectory[-20:]:')
    for v in bet.g_trajectory[-20:]:
        print('  ', repr(v))
    print()

    # σ 末 20 步
    print('σ.trajectory[-20:]:')
    for v in bet.sigma_trajectory[-20:]:
        print('  ', repr(v))
    print()

    # h 末 20 步
    print('h.trajectory[-20:]:')
    for v in bet.h_trajectory[-20:]:
        print('  ', repr(v))
    print()

    print('σ.trajectory length:', len(bet.sigma_trajectory))
    print('g.trajectory length:', len(bet.g_trajectory))
    print('h.trajectory length:', len(bet.h_trajectory))
    print('a.trajectory length:', len(a.trajectory))
    print('b.trajectory length:', len(b.trajectory))
    print()
    print('=== 完毕 ===')
