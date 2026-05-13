# DGA 恶意域名检测模型训练

本目录包含用于训练和评估 DGA（域名生成算法）恶意域名检测模型的完整工具链。

## 📁 目录结构

```
model_training/
├── train_dga_model.py      # 主训练脚本
├── classifier.py            # 分类器实现
├── dga_runtime.py          # 模型推理运行时
├── bench_inference.py      # 性能基准测试
├── requirements.txt        # Python依赖
├── docs/                   # 文档目录
│   ├── DGA_TRAINING_REPORT.md      # 详细训练报告
│   └── MODEL_INTEGRATION.md        # 集成指南
└── README.md              # 本文件

../artifacts/
├── models/
│   └── active/
│       └── dga_model_light_markov_100k_v2.pkl  # 当前生产模型
└── plots/
    └── plots_light_markov_100k_v2/             # 训练可视化图表
```

## 🎯 当前模型信息

**模型文件**: `dga_model_light_markov_100k_v2.pkl`

**性能指标**:
- 准确率 (Accuracy): **95.06%**
- DGA召回率 (Recall): **94.00%**
- 误报率 (FPR): **3.946%**
- 推理速度: **5246 queries/s** (0.19 ms/query)
- 模型大小: **17.45 MB**

**模型配置**:
- 算法: RandomForest
- 特征: Markov链 + 基础统计特征
- 训练样本: 100k (50k benign + 50k DGA)

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 训练新模型

```bash
python train_dga_model.py --config light_markov --samples 100000
```

可用配置:
- `baseline`: 基础特征 (仅统计特征)
- `light_markov`: 轻量Markov特征 (推荐)
- `full`: 完整特征集

### 3. 性能测试

```bash
python bench_inference.py ../artifacts/models/active/dga_model_light_markov_100k_v2.pkl
```

### 4. 在DNS服务器中使用

```python
from model_training.dga_runtime import DGAClassifier

# 加载模型
classifier = DGAClassifier('artifacts/models/active/dga_model_light_markov_100k_v2.pkl')

# 检测域名
domain = "example.com"
is_dga, confidence = classifier.predict(domain)

if is_dga:
    print(f"⚠️ 检测到恶意域名 (置信度: {confidence:.2%})")
else:
    print(f"✓ 正常域名 (置信度: {confidence:.2%})")
```

## 📊 训练数据要求

训练脚本需要以下数据文件:

1. **白样本**: Tranco Top 1M 域名列表
   - 文件: `tranco_6GYWX-1m.csv.zip`
   - 来源: https://tranco-list.eu/

2. **黑样本**: DGA域名数据集
   - 推荐数据集:
     - ExtraHop DGA Detection Training Dataset
     - 360 Netlab DGA Dataset
     - Bambenek DGA Feed
   - 格式: 每行一个域名的文本文件

将数据文件放在项目根目录或通过命令行参数指定路径。

## 🔧 高级配置

### 自定义训练参数

```bash
python train_dga_model.py \
    --config light_markov \
    --samples 200000 \
    --n-estimators 150 \
    --max-depth 25 \
    --min-samples-leaf 3 \
    --output-dir custom_output
```

### 特征工程

编辑 `classifier.py` 中的特征提取函数:
- `extract_basic_features()`: 基础统计特征
- `extract_markov_features()`: Markov链特征
- `extract_ngram_features()`: N-gram特征

## 📈 模型评估

训练完成后，在输出目录查看:

1. **ROC曲线**: `roc_curve.png`
   - 评估分类器性能
   - AUC值越接近1越好

2. **特征重要性**: `feature_importance.png`
   - 显示哪些特征对分类最有用

3. **误分类样本**: `misclassified_examples.md`
   - 分析模型错误案例

4. **外部验证**: `external_benign_eval.md`
   - 在Alexa Top 1000上的误报率测试

## 🔗 集成到DNS服务器

详细集成步骤请参考: [MODEL_INTEGRATION.md](docs/MODEL_INTEGRATION.md)

简要步骤:
1. 在DNS服务器启动时加载模型
2. 在域名解析前调用分类器
3. 对检测为DGA的域名返回0.0.0.0或拒绝解析
4. 记录拦截日志供分析

示例集成代码:

```python
# 在server.py中
from model_training.dga_runtime import DGAClassifier

class DNSServer:
    def __init__(self):
        self.dga_classifier = DGAClassifier(
            'artifacts/models/active/dga_model_light_markov_100k_v2.pkl'
        )
    
    def handle_query(self, domain):
        # DGA检测
        is_dga, confidence = self.dga_classifier.predict(domain)
        
        if is_dga and confidence > 0.8:
            print(f"[BLOCKED] DGA域名: {domain} (置信度: {confidence:.2%})")
            return self.create_sinkhole_response()  # 返回0.0.0.0
        
        # 正常解析流程
        return self.resolve_domain(domain)
```

## 📚 文档

- [DGA_TRAINING_REPORT.md](docs/DGA_TRAINING_REPORT.md) - 完整训练报告和实验结果
- [MODEL_INTEGRATION.md](docs/MODEL_INTEGRATION.md) - DNS服务器集成指南

## ⚠️ 注意事项

1. **数据平衡**: 确保训练集中benign和DGA样本数量相近
2. **过拟合**: 使用交叉验证和独立测试集评估
3. **误报率**: 在生产环境中，低误报率比高召回率更重要
4. **定期更新**: DGA算法不断演化，建议定期重新训练模型

## 🛠️ 故障排除

**问题**: 训练速度慢
- 解决: 减少样本数量或使用更少的树 (`--n-estimators`)

**问题**: 内存不足
- 解决: 使用 `baseline` 配置或减少特征维度

**问题**: 误报率高
- 解决: 调整分类阈值或使用 `light_markov` 配置

**问题**: 模型文件过大
- 解决: 减少树的数量或深度

## 📞 支持

如有问题，请查看:
1. 训练日志: `logs/` 目录
2. 详细文档: `docs/` 目录
3. 代码注释: 各Python文件中的docstring

---

**最后更新**: 2026-04-09
**模型版本**: v2 (light_markov_100k)
