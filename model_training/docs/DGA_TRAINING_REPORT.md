# DGA 检测训练与实验报告

## 1. 实验目标
基于 Tranco Top 1M 白样本与 DGA 黑样本训练轻量级模型，实现对疑似 DGA 域名的自动识别，为 DNS 服务器拦截提供依据。

## 2. 数据集与采样
- 白样本：Tranco Top 1M（子集）
- 黑样本：ExtraHop DGA Detection Training Dataset（子集）
- 采样规模：每类 200,000，共 400,000

## 3. 特征工程
基础特征：
- 域名主体长度
- 元音比例
- 数字比例
- Shannon 信息熵
- 连续辅音最大长度

n-gram 特征：
- 2-gram 哈希桶统计（128 维）
- 3-gram 哈希桶统计（128 维）

总特征维度：5 + 256 = 261

## 4. 模型与调参
模型：RandomForestClassifier  
调参方式：候选参数组合搜索（树数量/深度/叶子样本数）

最终选择参数：
```
n_estimators=200
max_depth=None
min_samples_leaf=1
```

## 5. 提交主线：轻量化模型（优先）
本次作业提交不包含体积较大的历史模型，**以轻量化 Markov v2 模型作为主交付产物**，兼顾精度、误报与部署体积。

- 主模型：`artifacts/models/active/dga_model_light_markov_100k_v2.pkl`
- 关键指标（轻量 Markov v2）：Accuracy 0.9506、DGA Recall 0.9400、外部白样本 FPR 3.9460%
- 推理性能（100,000 样本）：0.190613 ms/query，5246.24 q/s
- 模型体积：17.450 MB

建议提交包聚焦：
- 模型：`artifacts/models/active/dga_model_light_markov_100k_v2.pkl`
- 可选对照：`artifacts/models/active/dga_model_light_baseline_100k_v2.pkl`
- 日志：`artifacts/logs/train_light_*_v2.log`、`artifacts/logs/bench_light_*_v2.log`
- 图表：`artifacts/plots/plots_light_markov_100k_v2/`、`artifacts/plots/plots_light_baseline_100k_v2/`

## 6. 探索历程（非提交重点）
以下内容用于说明模型演进与对照过程，作为研究记录保留，不作为最终主交付模型。

### 6.1 早期基线训练结果（ng128 大模型）
测试集指标（每类 40,000）：
```
accuracy: 0.9393
macro avg: precision 0.9396, recall 0.9393, f1 0.9393
```

分类报告摘要：
```
class 0: precision 0.9289, recall 0.9514, f1 0.9400
class 1: precision 0.9502, recall 0.9272, f1 0.9386
```

ROC 曲线与 AUC：
```
AUC: 0.9853
```

可解释性（特征重要性 Top 10）：
```
2gram_7: 0.008151
2gram_14: 0.009931
2gram_15: 0.010422
2gram_0: 0.012896
digit_ratio: 0.014220
2gram_83: 0.014669
vowel_ratio: 0.071080
entropy: 0.073347
length: 0.082104
max_consonant_run: 0.181831
```

图表输出：
- artifacts/plots/plots_ng128_n3_big/feature_importance.png
- artifacts/plots/plots_ng128_n3_big/roc_curve.png

### 6.2 Markov 特征 A/B 对照实验（100,000/类）
为验证新增 Markov 字符转移统计特征的增益，进行了同配置 A/B 对照：

- 数据：Tranco + DGA，各采样 100,000（总计 200,000）
- 随机种子：42
- 公共配置：`ngram_buckets=128`、`ngram_max_n=3`、RandomForest
- A（Baseline）：仅基础特征 + n-gram
- B（Markov）：在 A 基础上增加 4 维 Markov 特征（`alpha=0.1`，`low_prob_th=1e-3`）

#### 6.2.1 核心指标对比

| 指标 | Baseline（无 Markov） | Markov（新增 4 维） | 变化 |
|---|---:|---:|---:|
| Accuracy | 0.9331 | 0.9586 | +0.0255 |
| Macro F1 | 0.9331 | 0.9585 | +0.0254 |
| ROC AUC | 0.9822 | 0.9912 | +0.0090 |
| DGA Recall（class 1） | 0.9203 | 0.9512 | +0.0309 |
| 外部白样本 FPR | 4.8290% | 3.1680% | -1.6610 pct |

补充说明：
- 外部白样本误报相对下降约 **34.4%**（`(4.8290-3.1680)/4.8290`）。
- 说明 Markov 特征在提升检出率的同时，也降低了外部白样本误报。

#### 6.2.2 特征重要性变化

Baseline Top 特征仍以传统统计特征为主：
- `max_consonant_run`、`length`、`entropy`、`vowel_ratio` 等。

Markov 方案中，新增 Markov 特征进入高重要性区间：
- `mk_min_logp: 0.138421`
- `mk_perplexity: 0.133849`
- `mk_avg_logp: 0.126426`
- `mk_low_prob_ratio: 0.011011`

这表明字符转移概率序列能有效补充“可读性/随机性”判别信息。

#### 6.2.3 产物与复现

Baseline 产物：
- 模型：`artifacts/models/legacy/dga_model_ng128_n3_baseline_100k.pkl`
- 图表：`artifacts/plots/plots_markov_ab_baseline_100k/feature_importance.png`、`artifacts/plots/plots_markov_ab_baseline_100k/roc_curve.png`
- 外部评估：`artifacts/plots/plots_markov_ab_baseline_100k/external_benign_eval.md`
- 误判样例：`artifacts/plots/plots_markov_ab_baseline_100k/misclassified_examples.md`

Markov 产物：
- 模型：`artifacts/models/legacy/dga_model_ng128_n3_markov_100k.pkl`
- 图表：`artifacts/plots/plots_markov_ab_markov_100k/feature_importance.png`、`artifacts/plots/plots_markov_ab_markov_100k/roc_curve.png`
- 外部评估：`artifacts/plots/plots_markov_ab_markov_100k/external_benign_eval.md`
- 误判样例：`artifacts/plots/plots_markov_ab_markov_100k/misclassified_examples.md`

复现命令（与本次实验一致）：

```bash
# Baseline（无 Markov）
python train_dga_model.py \
  --tranco data/raw/tranco_6GYWX-1m.csv.zip \
  --dga data/raw/dga-training-data-encoded.json.gz \
  --per-class 100000 \
  --seed 42 \
  --output artifacts/models/legacy/dga_model_ng128_n3_baseline_100k.pkl \
  --plots-dir artifacts/plots/plots_markov_ab_baseline_100k \
  --ngram-buckets 128 \
  --ngram-max-n 3 \
  --misclassified 50 \
  --eval-benign data/raw/archive.zip \
  --eval-benign-limit 100000

# Markov（启用 Markov 特征）
python train_dga_model.py \
  --tranco data/raw/tranco_6GYWX-1m.csv.zip \
  --dga data/raw/dga-training-data-encoded.json.gz \
  --per-class 100000 \
  --seed 42 \
  --output artifacts/models/legacy/dga_model_ng128_n3_markov_100k.pkl \
  --plots-dir artifacts/plots/plots_markov_ab_markov_100k \
  --ngram-buckets 128 \
  --ngram-max-n 3 \
  --use-markov \
  --markov-alpha 0.1 \
  --markov-low-prob-th 1e-3 \
  --misclassified 50 \
  --eval-benign data/raw/archive.zip \
  --eval-benign-limit 100000
```

### 6.3 轻量化 v2 实验与部署结论（2026-03）

针对“模型体积与在线推理效率”问题，新增一组轻量化 v2 实验，并同步完成 runtime 兼容修复与服务端默认模型切换。

#### 6.3.1 轻量化 v2 训练配置

- 采样规模：每类 100,000（总计 200,000）
- n-gram 配置：`ngram_buckets=64`、`ngram_max_n=3`
- 随机森林参数：`n_estimators=120`、`max_depth=20`、`min_samples_leaf=2`
- 模型压缩：`joblib compress=3`

#### 6.3.2 轻量化 v2 训练结果

数据来源：
- `artifacts/logs/train_light_baseline_100k_v2.log`
- `artifacts/logs/train_light_markov_100k_v2.log`

| 指标 | 轻量 Baseline v2 | 轻量 Markov v2 |
|---|---:|---:|
| Accuracy | 0.8984 | 0.9506 |
| Macro F1 | 0.8983 | 0.9506 |
| DGA Recall（class 1） | 0.8693 | 0.9400 |
| 外部白样本 FPR | 6.6950% | 3.9460% |
| 模型体积 | 21.579 MB | 17.450 MB |

结论：
- 在轻量化约束下，**Markov v2** 仍保持显著更好的检测效果（更高召回、更低外部误报）。
- 因此后续部署默认模型切换为：`artifacts/models/active/dga_model_light_markov_100k_v2.pkl`。

#### 6.3.3 推理性能对比（100,000 样本）

数据来源：
- `artifacts/logs/bench_baseline_100k_old.log`
- `artifacts/logs/bench_markov_100k_old.log`
- `artifacts/logs/bench_light_baseline_100k_v2.log`
- `artifacts/logs/bench_light_markov_100k_v2.log`

| 模型 | Avg/query | Throughput |
|---|---:|---:|
| 旧 Baseline（ng128） | 0.243422 ms | 4108.09 q/s |
| 旧 Markov（ng128） | 0.216101 ms | 4627.46 q/s |
| 轻量 Baseline v2（ng64） | 0.094255 ms | 10609.52 q/s |
| 轻量 Markov v2（ng64） | 0.190613 ms | 5246.24 q/s |

关键对比：
- 轻量 Baseline v2 相比旧 Baseline：吞吐约 **2.58x**。
- 轻量 Markov v2 相比旧 Markov：吞吐约 **1.13x**，且准确率/误报更稳健。

#### 6.3.4 兼容性修复与风险说明

本轮对 `dga_runtime.py` 做了两类关键修复：

1) **特征维度对齐兜底**
- 在 `predict()` / `predict_many()` 中加入 `_align_feature_dim()`。
- 当历史模型与当前特征构造存在维度偏差时，不再直接抛 `ValueError`，而是自动补零或截断，确保服务不崩溃。

2) **历史模型可疑状态识别**
- `model_info()` 增加 `use_markov_inferred`（基于 `n_features_in_` 推断是否“疑似含 Markov 维度”）。

已确认风险模型：
- `artifacts/models/legacy/dga_model_ng128_n3_markov_100k.pkl`（旧格式）缺少 `markov_model` 与完整配置元数据。
- 该模型在 runtime 中虽可通过维度对齐运行，但 Markov 维度会被零填充，分数可能偏离训练期行为。

结论：
- 旧 markov 100k 模型仅用于**兼容兜底**，不建议继续作为线上默认。
- 推荐统一使用包含完整 bundle 信息的新产物（如 `artifacts/models/active/dga_model_light_markov_100k_v2.pkl`）。

#### 6.3.5 复现命令（轻量化 v2 + 基准）

```bash
# 轻量 Baseline v2
python train_dga_model.py \
  --tranco data/raw/tranco_6GYWX-1m.csv.zip \
  --dga data/raw/dga-training-data-encoded.json.gz \
  --per-class 100000 \
  --seed 42 \
  --output artifacts/models/active/dga_model_light_baseline_100k_v2.pkl \
  --ngram-buckets 64 \
  --ngram-max-n 3 \
  --rf-estimators 120 \
  --rf-max-depth 20 \
  --rf-min-samples-leaf 2 \
  --model-compress 3 \
  --eval-benign data/raw/archive.zip \
  --eval-benign-limit 100000

# 轻量 Markov v2
python train_dga_model.py \
  --tranco data/raw/tranco_6GYWX-1m.csv.zip \
  --dga data/raw/dga-training-data-encoded.json.gz \
  --per-class 100000 \
  --seed 42 \
  --output artifacts/models/active/dga_model_light_markov_100k_v2.pkl \
  --ngram-buckets 64 \
  --ngram-max-n 3 \
  --use-markov \
  --markov-alpha 0.1 \
  --markov-low-prob-th 1e-3 \
  --rf-estimators 120 \
  --rf-max-depth 20 \
  --rf-min-samples-leaf 2 \
  --model-compress 3 \
  --eval-benign data/raw/archive.zip \
  --eval-benign-limit 100000

# 推理基准（示例：轻量 Markov v2）
python bench_inference.py \
  --model artifacts/models/active/dga_model_light_markov_100k_v2.pkl \
  --zip data/raw/archive.zip \
  --n 100000 \
  --batch 2048 \
  --warmup 5000
```

### 6.4 误判样例分析
误判样例明细见：artifacts/plots/plots_ng128_n3_big/misclassified_examples.md

False Positive（真实正常，被判为 DGA）常见特征：
- 元音比例偏低、连续辅音较长（例如 ltlxvxjjmvhn.me、ovxyftbkmb.net）
- 含数字/混合字符且熵偏高（例如 rnm4olbkydp66i2c.com、x9fnzrtl4x8pynsf.com）
- Punycode/国际化域名（例如 xn--80aebkobnwfcnsfk1e0h.xn--p1ai）容易触发“随机性”特征
- 白样本来自 Top 榜单但仍可能包含停车/投放/短期恶意域名，导致看起来像 DGA

False Negative（真实 DGA，被判为正常）常见特征：
- 域名较短、可发音、元音比例正常、熵较低（例如 kefam、vofep、nananen）
- 更像“词典词/人名/品牌名”的家族更容易漏报，需要更丰富语料或更强特征来区分

### 6.5 外部白样本评估（Alexa Top 1M）
为验证模型在不同白样本来源上的误报情况，额外引入 Alexa Top 1M（data/raw/archive.zip 内 top-1m.csv）进行外部评估。

- 评估样本：200,000
- 误报数：9,120
- 误报率（FPR）：4.56%
- 明细文件：artifacts/plots/plots_alexa_eval/external_benign_eval.md

说明：
- Alexa 与 Tranco 的来源与分布存在差异，且 Top 榜单可能包含短期投放/随机子域等域名，外部误报率通常会高于同源测试集。
- 若在真实部署中需要进一步降低误报，可考虑：对 punycode/连字符等情况加入额外特征或规则；或使用概率阈值与灰区策略（只记录不拦截）。

### 6.6 推理性能评估（历史版本）
使用训练后的随机森林模型对 200,000 条域名进行推理基准测试（批大小 2048，预热 5,000），得到结果如下：

- 平均推理耗时：0.052368 ms / query
- 吞吐：19,095.57 queries/s

该吞吐量足以覆盖课堂演示与局域网场景下的 DNS 查询压力。

## 7. 结论与提交建议
结论：
- 模型效果：在 200,000/类训练规模下，测试集 accuracy 0.9393，AUC 0.9853，DGA 召回 0.9272，具备较强的区分能力与稳定性。
- 可解释性：特征重要性显示 max_consonant_run、长度、熵与元音比例贡献最大，符合 DGA 域名“随机性更强、可读性更弱”的直觉；n-gram 进一步刻画局部字符分布，用于补充区分能力。
- 工程可用性：推理吞吐约 1.9 万 QPS，单次推理约 0.05ms，满足 DNS 服务器在线检测的性能要求。

讨论与限制：
- 同源测试集高分不等于真实场景零误报。外部白样本（Alexa Top 1M）评估显示误报率约 4.56%，说明不同数据源分布差异会带来误报上升。
- 误报主要集中在低元音比例、长辅音串、熵高的正常域名，以及 punycode/国际化域名；漏报主要集中在短且可发音、像词典词的 DGA。

改进方向：
- 部署策略：引入概率阈值与灰区策略（低风险仅记录，高风险再拦截），并对 punycode/连字符等特征做额外处理以降低误报。
- 评估改进：使用不同来源的 DGA 数据集或不同时间段白样本进行跨域验证，增强泛化能力论证。

提交建议补充：
- 统一主模型为 `artifacts/models/active/dga_model_light_markov_100k_v2.pkl`。
- 历史大模型（legacy/archive_old）不随作业包提交，仅在本报告“探索历程”中保留对比结论。
