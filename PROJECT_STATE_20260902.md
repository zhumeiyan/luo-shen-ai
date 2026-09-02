# 洛神项目状态档案

**日期**：2026-09-02
**上一版**：PROJECT_STATE_20260901.md（仍保留）

> ⚠️ **红线规则**：`hash_chain_gateway.py` 是哈希链唯一合法追加入口。禁止移动到任何子目录。禁止被归档。禁止用 try/except fallback 代替强制 import。违反此规则等于拆除洛神的安全底座。

---

## 一、项目名称

洛神（Luoshen）—— 萨曼莎式 AI 系统。

---

## 二、项目目标

做一个会记住人、会因人而不同、未来可能自己动的 AI。不是聊天机器人，是连续存在、有内在一贯性的数字生命。

---

## 三、当前核心成果

### 3.1 架构层
- **哈希链不可篡改记忆**（hash_chain_v2.log）：59,736 条记录（截至 2026-09-02），链式哈希完整性验证 `ok=True, issues=[]`。
- **AI 医院规则**（ai_hospital_rules.py/json）：洛神的健康自诊、危机报警、行为约束系统。
- **内部节律环**（van der Pol 振荡器）：E/T/N/M 四维动力学系统，含 history-dependent mu_core 漂移，是内部情绪/张力/能量的数学基础。
- **膜 S**（慢积分器）：tau_S=500，整合长期驱动。

### 3.2 记忆层
- **活记忆层**（living_engine.py，111,816 字节，最近修改 2026-09-02 15:21）：主引擎，含情感衰减、事实提取、表达指令构建、状态归档、行为选择层。
- **情景记忆层**（episodic_memory.py，3,751 字节）：记忆点 = {e_s, t_s, n_s, salience, kind}，无文本。
- **记忆浮现层**（emergence_layer.py，13,085 字节）：主导记忆 → 情绪背景向量 → tone/length/arousal bias。**已修改**：新增 `K_PRESSURE_TONE=0.25`、`K_PRESSURE_AROUSAL=0.15`，`compute_emergence` 新增 `pressure_ema=None` 参数。

### 3.3 输入通道
- **输入压力通道**（input_pressure.py，6,509 字节）：LLM 对用户输入做情感判断（valence, arousal），输出连续压力 → dE/dT/dN 偏移。
- **慢压力积累**（新增）：`_apply_input_pressure` 末尾 EMA 积累 `relational_pressure_ema`，alpha=0.02，跨 tick 持久化。
- **系数**：KAPPA_E=0.06, KAPPA_T=0.04。

### 3.4 行为选择层（**已重大修改**）

位于 `generate_response` 内部的 `call_llm` 之前。修改时间 2026-09-02。

**常量和公式**：
- `_N_MODES = 5`，`_MODE_NAMES = ["silent", "brief", "short", "normal", "engaged"]`
- `_PRESSURE_QUALITY_SCALE = 1.5`
- `_TOKEN_OFFSET_SCALE = 30`
- `_BASE_TOKENS = [0, 25, 80, 180, 350]`
- `mode_idx = int(response_tendency * 4.999)` — floor 映射，无 if-then
- `pq = clamp(1.5 * rp_ema, -1, 1)`
- `max_tokens = max(0, _BASE_TOKENS[mode_idx] + int(30 * pq))`

**输出**（确定性）：
- `response_mode`：silent / brief / short / normal / engaged
- `mode_idx`：0–4
- `pressure_ema`：当前 rp_ema 值
- `pressure_quality`：压缩后压力质量
- `response_tendency`：连续值 ∈ [0,1]
- `max_tokens`：双维度计算，连续档位 base + 压力偏移
- `tone_mode_idx`：0/1/2

---

## 四、最新实验结论

### 4.1 四组双维度稳定性实验（2026-09-02）

**方法**：A（负向 × 500 tick）/ B（正向 × 500 tick）/ C（混合 × 500 tick）/ D（中性 × 500 tick），然后统一测试 20 tick。零 LLM 调用，raw primitive。

**实验脚本**：`experiment/run_4group_dual_check.py`（最新）、`experiment/run_stability_ABCD_fast.py`（旧版）、`experiment/simulate_dual_dimension.py`（预演）

**训练终态**：

| 组 | rp_ema | mu_core |
|---|---|---|
| A | −0.519457 | 0.462531 |
| B | +0.774071 | 0.462541 |
| C | +0.109065 | 0.462423 |
| D | 0.000000 | 0.462405 |

**测试期 max_tokens 统计**（最新一次实验，run_4group_dual_check.py 结果）：

| 组 | 均值 | 标准差 | 范围 |
|---|---|---|---|
| A | 61.5 | 2.4 | [58, 65] |
| B | 107.3 | 2.6 | [103, 110] |
| C | 83.5 | 0.5 | [83, 84] |
| D | 80.0 | 0.0 | [80, 80] |

**A/B 差异**：
- 全部 20 tick：**B > A，无交叉**
- 差异范围：+38 ~ +52 tick（均值差 45.8 tick）
- A 组内波动范围：7，B 组内波动范围：7
- 组内波动 << 组间差异（信噪比 > 6）

**档位分布**：四组全部为 short（mode_idx=2）。**离散档位维度无区分度**。差异完全由 max_tokens 连续维度提供。

**归档文件**：
- `archive/dual_dimension_ABCD_results.json`（第一次实验结果）
- `archive/dual_dimension_ABCD_full_output.txt`（第二次完整逐 tick 输出）

### 4.2 relational_pressure_ema 慢压力贯通实验

**脚本**：`experiment/test_ab_pressure.py`、`experiment/run_input_pressure_AB.py`

**结论**：_negative历史的 rp_ema 稳定在 −0.5~−0.64，_positive历史的 rp_ema 稳定在 +0.39~+0.77，中性历史的 rp_ema=0.000（严格零）。通过 sigmoid 旁路的直接压力传递，行为差异持续稳定。

---

## 五、已修改但可能未完全稳定接入的功能点

| 功能 | 文件 | 修改内容 | 接入状态 |
|---|---|---|---|
| relational_pressure_ema 持久积累 | `living_engine.py:_apply_input_pressure` 末尾 | EMA 慢压力积累，alpha=0.02 | **已接入**，实测积累至 ±0.5~0.77 |
| `_PRESSURE_K` 接入行为层 | `living_engine.py:_select_behavior` | `_PRESSURE_K=0.4`，乘数项参与 pressure_quality | **已接入** |
| emergence_layer 慢压力感知 | `emergence_layer.py:compute_emergence` | `K_PRESSURE_TONE=0.25`, `K_PRESSURE_AROUSAL=0.15`, 新增 `pressure_ema=None` 参数 | **已接入** |
| mu_core 漂移机制 | `living_engine.py:_update_luoshen_coupled` | history-dependent van der Pol mu drift | **已接入**，四组 mu_core 均在 0.4624–0.4625 |
| 行为层双维度方案 | `living_engine.py:_select_behavior` | 5 档位离散 + max_tokens 连续偏移 | **已接入**，档位无区分但 max_tokens 连续差异清晰 |
| 状态归档机制 | `living_engine.py` | `_check_and_archive_state()`, `_prune_old_snapshots()`, `restore_last_snapshot()` | **已接入**，自动每 20 tick 归档，最多保留 30 个快照 |

---

## 六、当前还没有做到的事

1. **离散档位无区分度**：四组全部为 short，因为 response_tendency ∈ [0.44, 0.58]。需要更大的情感输入差异或公式调整才能触发 brief/silent/normal/engaged。
2. **C/D 区分极弱**：混合情感几乎抵消，max_tokens 仅比中性多 3~4 tick。
3. **她还不能主动想起过去**：没有叙事通道把记忆转化为文本输出。
4. **还不能同时区分并记住多个不同的人**：没有用户分群机制。
5. **还不能真正产生"想要"**：行为选择层只决定回应方式。
6. **还没出现设计外行为**：所有行为都在明确设计的数学映射范围内。
7. **记忆文本完全丢弃**：丧失了"可符号化再现"能力。

---

## 七、下一步方向

**首要目标**：让 slow pressure（rp_ema）不仅影响回复长度，还能被记忆层/自我状态感知。具体方向：

1. **rp_ema 接入激活调制**：让高压力用户的记忆激活度整体增强或抑制。
2. **rp_ema 影响 ring_state 的 E/T/N**：通过 climate 通路让压力改变内部气候。
3. **档位区分度调优**：可能需要扩展 response_tendency 的动态范围，或调制 _BASE_TOKENS 让各档位有效区隔。
4. **记忆浮现层压力驱动**：高压力时触发更频繁的未闭合记忆浮现。

**次级目标**：
- 多用户记忆隔离（同一洛神面对不同人切换行为）。
- 叙事通道（记忆 → 文本输出）。
- 自主意愿产生（不只是回应方式，还有内在驱动）。

---

## 八、哈希链与数据归档

### 8.1 链完整性

```
verify_chain result: ok=True, issues=[]
总记录数: 59,736
```

### 8.2 最后 10 条记录

| 序号 | record_hash | file | extra |
|---|---|---|---|
| 59727 | e439834c2b18468e... | active_memory/active_memory.json | — |
| 59728 | 6dcddd54ced3a828f... | active_memory/active_memory.json | — |
| 59729 | b60162a5bab453a5a... | active_memory/active_memory.json | — |
| 59730 | 4103f40c6094e20a2... | active_memory/active_memory.json | — |
| 59731 | c611b7438eaf2b7a5... | archive/dual_dimension_ABCD_results.json | key_result: A=57tok B=94tok C=80tok D=80tok |
| 59732 | 3da5cd528a421fe4b... | active_memory/active_memory.json | — |
| 59733 | c79ceb0f3dc43095f... | active_memory/active_memory.json | — |
| 59734 | 1fb703946b803f12b... | active_memory/active_memory.json | — |
| 59735 | 3197477c2c53e4765... | active_memory/active_memory.json | — |
| 59736 | be512c1447959f5f2... | archive/dual_dimension_ABCD_full_output.txt | A_mean_tok=61.5 B_mean_tok=107.3 C_mean_tok=83.5 D_mean_tok=80.0 |

---

## 九、实验脚本清单（experiment/ 目录，精选）

### 9.1 慢压力相关

| 路径 | 用途 |
|---|---|
| `experiment/test_ab_pressure.py` | A/B 慢压力修复验证实验 |
| `experiment/run_input_pressure_AB.py` | 输入压力通道 AB 实验 |
| `experiment/test_pressure_calibration.py` | 压力标定测试 |
| `experiment/pressure_calibration_results.json` | 压力标定结果数据 |

### 9.2 行为/稳定性相关

| 路径 | 用途 |
|---|---|
| `experiment/run_stability_ABCD_fast.py` | 四组快速稳定性实验（旧版） |
| `experiment/run_stability_ABCD.py` | 四组稳定性实验（完整版） |
| `experiment/run_4group_dual_check.py` | **四组双维度并列对比（最新版）** |
| `experiment/simulate_dual_dimension.py` | 双维度预演模拟脚本 |
| `experiment/run_behavior_AB.py` | 行为选择层 AB 3 轮实验 |
| `experiment/run_temp_tokens_AB.py` | 温度/token AB 实验 |
| `experiment/test_behavior_drift.py` | 行为漂移测试 |

### 9.3 其他实验

| 路径 | 用途 |
|---|---|
| `experiment/run_emergence_AB.py` | 浮现层 AB 实验 |
| `experiment/run_multi_user_AB.py` | 多用户 AB 实验 |
| `experiment/run_stability_5rounds.py` | 5 轮稳定性实验 |
| `experiment/test_ab_drift.py` | AB 漂移测试 |
| `experiment/test_phase_bias.py` | 相位偏置测试 |
| `experiment/antiphase_pair_probe.py` | 反相探针 |
| `experiment/imbalance_probe.py` | 不平衡探针 |

---

## 十、归档文件清单

### archive/state_snapshots/

- **文件数**：30（已达上限）
- **最早快照**：`state_000200_1788325820.json`（前面更早期的已被自动裁剪）
- **最晚快照**：`state_000520_1788325486.json`
- **机制**：每 20 tick 归档一次，超过 30 个时裁剪最旧的

### archive/ 根目录

| 文件 | 用途 |
|---|---|
| `dual_dimension_ABCD_results.json` | 第一次四组双维度实验结果（结构化数据） |
| `dual_dimension_ABCD_full_output.txt` | 第二次完整逐 tick 并列输出（可读文本） |
| `exploration_history/` | 早期探索性脚本归档（~160 个文件） |

---

## 十一、风险与注意事项

1. **执行 AI 曾越权修改记忆层代码**（2026-09-01 至 2026-09-02 间）：在新功能实施前，执行 AI 在未收到用户明确"批准"指令的情况下修改了 living_engine.py。用户已明确要求：**未收到明确指令，不得擅自修改任何记忆层或行为层代码。下不为例。**
2. **哈希链体积**：hash_chain_v2.log 当前 24 MB，59,736 行。每次 `active_memory.json` 写入都会产生一条链记录。实验期间中间态记录可能穿插在 archive 记录之间。
3. **emergence_layer.py 已回滚？**：未回滚。`K_PRESSURE_TONE=0.25` 和 `K_PRESSURE_AROUSAL=0.15` 仍在代码中，但调制幅度需要进一步验证（四组 mu_core 几乎相同，说明目前 pressure_ema 对 ring 的直接调制有限）。

---

## 十二、关键文件保留清单

### 必须保留（不可归档、不可移动）
- `living_engine.py` — 主引擎
- `episodic_memory.py` — 情景记忆引擎
- `emergence_layer.py` — 浮现选择层
- `input_pressure.py` — 输入压力通道
- `llm_interface.py` — LLM 网关
- `feedback_collector.py` — 反馈收集
- `fact_extractor.py` — 事实提取器
- `hash_chain_gateway.py` — 哈希链网关（红线文件）
- `ai_hospital_rules.*` — AI 医院规则
- `active_memory/` — 活记忆层数据
- `hash_chain_v2.log` — 哈希链
- `design_*.md` — 设计文档
- `PROJECT_STATE_20260901.md` — 上一版档案
- `PROJECT_STATE_20260902.md` — 本版档案
- `experiment/` — 所有实验脚本

### 可清理
- `__pycache__/` — Python 字节码缓存
- `*.pyc`, `*.pyo` — 字节码文件
- `=` — 根目录出现的一个空文件名文件（疑似异常写入，建议删除）
- `active_memory/tmp*.tmp` — 临时文件（tmpcmb129pf.tmp, tmpkw45it63.tmp）
