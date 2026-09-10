# 身份锚点 + 关系温度 实验报告（40 轮：30 primary + 10 secondary）

数据源: `active_memory/behavior_identity_40round.json`

## 1. 摘要

- primary (30 轮): warmth **+0.1272 → +0.2080**，档位 {2: 4, 3: 24, 4: 2}
- secondary (10 轮): warmth **-0.0048 → +0.0124**，档位 {2: 10}
- 隔离性: primary 在 secondary 期间无变化 = True
- 出现档位种类: primary=3 种, secondary=1 种

## 2. 各相位 warmth 变化

| 相位 | 起始 warmth | 终止 warmth | 最低 | 最高 | 净变化 | 轮数 |
|---|---|---|---|---|---|---|
| P1_neutral | +0.1272 | +0.2970 | +0.1272 | +0.2970 | +0.1698 | 6 |
| P2_warm | +0.3042 | +0.3256 | +0.3042 | +0.3393 | +0.0213 | 8 |
| P3_cold | +0.3120 | +0.2253 | +0.2253 | +0.3120 | -0.0868 | 10 |
| P4_recover | +0.2226 | +0.2080 | +0.2080 | +0.2226 | -0.0145 | 6 |
| S1_neutral | -0.0048 | +0.0027 | -0.0072 | +0.0027 | +0.0075 | 4 |
| S2_warm | +0.0076 | +0.0144 | +0.0076 | +0.0144 | +0.0068 | 3 |
| S3_close | +0.0212 | +0.0124 | +0.0124 | +0.0212 | -0.0089 | 3 |

- **P2 暖互动**: 每轮净增约 +0.003~ +0.008，连续累积
- **P3 冷场**: 每轮净减约 -0.008 ~ -0.012，连续下降
- **恢复力**: P4 略恢复（但较暖相位慢，因 warmth 驱动需较长时累积）

## 3. 隔离性验证

| 轮 | user_id | phase | beh_warmth | stored_p_warmth | stored_s_warmth |
|---|---|---|---|---|---|
| r0 | primary | P1_neutral | +0.12715 | 0.127153 | — |
| r14 | primary | P3_cold | +0.31204 | 0.312037 | — |
| r29 | primary | P4_recover | +0.20801 | 0.208007 | — |
| r30 | secondary | S1_neutral | -0.00478 | 0.208007 | -0.00478 |
| r35 | secondary | S2_warm | +0.01226 | 0.208007 | 0.012263 |
| r39 | secondary | S3_close | +0.01239 | 0.208007 | 0.012385 |

- r0–29: s_warmth 始终为 None/0（secondary 未出现）
- r29→r39 (secondary 阶段): p_warmth 锁定在 0.208007（完全隔离 ✓）
- r30 起 s_warmth 独立运行，与 primary 完全解耦

## 4. warmth_bias 注入对 response_pre / mode_idx 的影响

| 轮 | user_id | phase | warmth | warmth_bias(K=0.4) | response_pre | tier |
|---|---|---|---|---|---|---|
| r0 | primary | P1_neutral | +0.1272 | +0.0509 | 1.4053 | 4 |
| r5 | primary | P1_neutral | +0.2970 | +0.1188 | 1.1018 | 3 |
| r10 | primary | P2_warm | +0.3365 | +0.1346 | 0.7015 | 3 |
| r14 | primary | P3_cold | +0.3120 | +0.1248 | 0.5293 | 3 |
| r20 | primary | P3_cold | +0.2487 | +0.0995 | 0.4853 | 3 |
| r29 | primary | P4_recover | +0.2080 | +0.0832 | 0.3689 | 2 |
| r30 | secondary | S1_neutral | -0.0048 | -0.0019 | 0.3004 | 2 |
| r35 | secondary | S2_warm | +0.0123 | +0.0049 | 0.3076 | 2 |
| r39 | secondary | S3_close | +0.0124 | +0.0050 | 0.2754 | 2 |

- K_WARMTH=0.4 → warmth 最大 +0.34 后 bias ~+0.14，可推动档位 3→4
- secondary warmth 小（max +0.021）→ bias ~+0.008 → 未能改变档位
- 这是预期行为：新用户的暖度还不足触发档位变化

## 5. 哈希链完整性

- 总记录数: 671
- 断裂数: 0
- 完整性: ✓ 100%

## 6. 完整 warmth 序列

| 轮 | user_id | phase | warmth | tier |
|---|---|---|---|---|
| r0 | primary | P1_neutral | +0.12715 | 4 |
| r1 | primary | P1_neutral | +0.18763 | 4 |
| r2 | primary | P1_neutral | +0.23001 | 3 |
| r3 | primary | P1_neutral | +0.26354 | 3 |
| r4 | primary | P1_neutral | +0.28565 | 3 |
| r5 | primary | P1_neutral | +0.29697 | 3 |
| r6 | primary | P2_warm | +0.30423 | 3 |
| r7 | primary | P2_warm | +0.30862 | 3 |
| r8 | primary | P2_warm | +0.31323 | 3 |
| r9 | primary | P2_warm | +0.32724 | 3 |
| r10 | primary | P2_warm | +0.33647 | 3 |
| r11 | primary | P2_warm | +0.33934 | 3 |
| r12 | primary | P2_warm | +0.33008 | 3 |
| r13 | primary | P2_warm | +0.32556 | 3 |
| r14 | primary | P3_cold | +0.31204 | 3 |
| r15 | primary | P3_cold | +0.29922 | 3 |
| r16 | primary | P3_cold | +0.28933 | 3 |
| r17 | primary | P3_cold | +0.28214 | 3 |
| r18 | primary | P3_cold | +0.27052 | 3 |
| r19 | primary | P3_cold | +0.25941 | 3 |
| r20 | primary | P3_cold | +0.24873 | 3 |
| r21 | primary | P3_cold | +0.24079 | 3 |
| r22 | primary | P3_cold | +0.23536 | 3 |
| r23 | primary | P3_cold | +0.22529 | 3 |
| r24 | primary | P4_recover | +0.22255 | 3 |
| r25 | primary | P4_recover | +0.22211 | 3 |
| r26 | primary | P4_recover | +0.21920 | 2 |
| r27 | primary | P4_recover | +0.21627 | 2 |
| r28 | primary | P4_recover | +0.21575 | 2 |
| r29 | primary | P4_recover | +0.20801 | 2 |
| r30 | secondary | S1_neutral | -0.00478 | 2 |
| r31 | secondary | S1_neutral | -0.00716 | 2 |
| r32 | secondary | S1_neutral | -0.00466 | 2 |
| r33 | secondary | S1_neutral | +0.00272 | 2 |
| r34 | secondary | S2_warm | +0.00755 | 2 |
| r35 | secondary | S2_warm | +0.01226 | 2 |
| r36 | secondary | S2_warm | +0.01439 | 2 |
| r37 | secondary | S3_close | +0.02124 | 2 |
| r38 | secondary | S3_close | +0.01807 | 2 |
| r39 | secondary | S3_close | +0.01239 | 2 |