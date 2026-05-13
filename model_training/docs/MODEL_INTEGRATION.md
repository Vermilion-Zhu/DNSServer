# DGA 模型对接与使用说明

## 1. 这份文档解决什么问题

本项目在 DNS 代理服务器中集成 DGA（Domain Generation Algorithm）恶意域名检测能力。\
你只需要把域名字符串交给模型推理模块，得到 `p(dga)`（0\~1 概率），再按阈值决定是否拦截。

## 2. 文件与产物

- 模型文件（当前默认/推荐）：`artifacts/models/active/dga_model_light_markov_100k_v2.pkl`
- 历史模型（可对比，不推荐默认部署）：`artifacts/models/legacy/dga_model_ng128_n3_baseline_100k.pkl`、`artifacts/models/legacy/dga_model_ng128_n3_markov_100k.pkl`
- 推理模块（供服务器调用）：`../dga_runtime.py`
- 训练脚本（特征提取与训练）：`../train_dga_model.py`
- 训练报告（含指标/误判/性能）：`./DGA_TRAINING_REPORT.md`

服务端当前默认配置（`server.py`）：

```python
DGA_MODEL_PATH = "artifacts/models/active/dga_model_light_markov_100k_v2.pkl"
DGA_THRESHOLD = 0.7
```

## 3. 特征配置与兼容原则

优先原则：**由模型产物自带配置驱动推理**（artifact bundle 中的 `feature_config`），尽量不要手动覆写。

当前默认模型（`artifacts/models/active/dga_model_light_markov_100k_v2.pkl`）配置：

- `ngram-buckets=64`
- `ngram-max-n=3`（2-gram 与 3-gram）
- `use_markov=True`（额外 4 维 Markov 特征）

兼容说明：

- `dga_runtime.py` 已内置维度对齐兜底（不足补零、超出截断），用于历史模型兼容，避免线上崩溃。
- 但兜底不代表语义完全等价：如果历史模型缺失 `markov_model`，Markov 维度会被零填充，分数可能偏移。

## 4. 输出含义与拦截策略

推理输出：

- `score = p(dga)`：域名为 DGA 的概率（越大越可疑）
- `is_dga = (score >= threshold)`：是否判定为 DGA

阈值建议：

- **演示拦截更明显**：`threshold = 0.5`
- **减少误杀更稳**：`threshold = 0.7`（推荐默认）

拦截动作建议（协议侧实现）：

- 对 A 查询：返回 Sinkhole `0.0.0.0`
- 对其他类型：返回空 Answer 或 NXDOMAIN（团队统一一种即可）

## 5. 服务器侧怎么接入

在 DNS 服务器处理每次查询时（拿到 `qname` 后，进入缓存/递归之前），加入：

```python
from dga_runtime import predict

is_dga, score = predict(qname, threshold=0.7)
if is_dga:
    # 这里执行拦截：返回 0.0.0.0 或 NXDOMAIN
    ...
else:
    # 继续走缓存/递归流程
    ...
```

日志建议（便于统计/展示）：

- `domain, qtype, score(p(dga)), blocked(True/False), threshold`

## 6. 本地快速自测

在项目目录运行：

```powershell
python -c "import dga_runtime as r; print(r.predict('asdf789asdf789asdf.com', threshold=0.7))"
python -c "import dga_runtime as r; print(r.predict('google.com', threshold=0.7))"
python -c "import dga_runtime as r; print(r.model_info('artifacts/models/active/dga_model_light_markov_100k_v2.pkl'))"
```

## 7. 常见问题排查

### 7.1 报错或告警：X has N features, but model is expecting M features

原因：训练与推理特征配置不一致，或历史模型缺少配置元数据。\
处理：

- 优先使用 bundle 格式新模型（推荐：`artifacts/models/active/dga_model_light_markov_100k_v2.pkl`）
- 推理侧不要手改特征参数，交给 `dga_runtime` 从模型读取配置
- 兼容兜底虽可避免崩溃，但应尽快替换异常历史产物

### 7.2 旧 Markov 100k 模型为什么不建议上线

`artifacts/models/legacy/dga_model_ng128_n3_markov_100k.pkl` 为旧格式，缺少 `markov_model`。即使 runtime 可运行，也会出现“推理时 Markov 维度被零填充”的语义偏差。

建议：

- 仅用于兼容测试，不作为默认线上模型
- 统一迁移到 `artifacts/models/active/dga_model_light_markov_100k_v2.pkl`

### 7.3 误报偏高怎么办

优先从策略而不是模型入手：

- 阈值上调（例如 0.7 → 0.8）
- 加灰区策略：`0.5~0.7` 只记录不拦截
- 对 punycode/连字符等类型加额外特征或规则（降低误杀）

## 8. 交接清单

- 协议同学：
  - 使用 `dga_runtime.predict(qname)` 获取 `(is_dga, score)` 并执行拦截
  - ~~保证~~ ~~`qname`~~ ~~进入模型前是小写且去掉末尾点号~~。（已解决）可直接传入原始 qname，模块内部会自动 normalize；建议避免带空格与非法字符
  - 记录日志字段（domain/qtype/score/blocked）
- 测试同学：
  - 用一组正常域名 + 一组 DGA 域名做演示
  - 统计拦截率、缓存命中率，并截图 ROC/特征重要性图

