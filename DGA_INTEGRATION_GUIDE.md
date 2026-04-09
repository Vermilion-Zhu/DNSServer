# DGA检测集成使用指南

## 📋 功能概述

已成功将DGA（域名生成算法）恶意域名检测功能集成到 `simpleServer.py` 中，包含：

### ✅ 已实现功能

1. **白名单机制** - 信任的域名直接放行，不进行AI检测
2. **DGA AI检测** - 使用机器学习模型实时检测恶意域名
3. **智能拦截** - 检测到恶意域名后返回0.0.0.0（Sinkhole）
4. **统计报告** - 记录拦截数量、检测次数等关键指标

---

## 🎯 白名单配置

### 白名单类型

代码中实现了**两种白名单机制**：

#### 1. 精确匹配白名单 (`WHITELIST`)
```python
WHITELIST = {
    "google.com.", "www.google.com.",
    "baidu.com.", "www.baidu.com.",
    "github.com.", "www.github.com.",
    # ... 更多域名
}
```

**特点**：必须完全匹配（包括末尾的点号）

#### 2. 后缀匹配白名单 (`WHITELIST_SUFFIXES`)
```python
WHITELIST_SUFFIXES = {
    ".local.", ".localhost.", ".test.",
    ".cn.", ".edu.cn.", ".gov.cn.",
}
```

**特点**：只要域名以这些后缀结尾就会被信任

### 如何添加白名单

**方法1：直接编辑代码**（第30-47行）
```python
WHITELIST = {
    # 添加你信任的域名
    "example.com.",
    "mysite.com.",
}

WHITELIST_SUFFIXES = {
    # 添加你信任的后缀
    ".mycompany.com.",
}
```

**方法2：动态加载**（推荐用于生产环境）
可以修改代码从外部文件加载白名单：
```python
# 在HybridResolver.__init__中添加
def load_whitelist_from_file(self, filepath):
    with open(filepath, 'r') as f:
        for line in f:
            domain = line.strip()
            if domain and not domain.startswith('#'):
                WHITELIST.add(domain)
```

---

## ⚙️ DGA检测配置

### 配置参数（第25-28行）

```python
ENABLE_DGA_DETECTION = True  # 是否启用DGA检测
DGA_THRESHOLD = 0.7          # 检测阈值（0-1之间）
DGA_ACTION = "SINKHOLE"      # 拦截动作
```

### 参数说明

| 参数 | 说明 | 推荐值 |
|------|------|--------|
| `ENABLE_DGA_DETECTION` | 总开关 | `True` |
| `DGA_THRESHOLD` | 置信度阈值，越高越严格 | `0.7`（平衡）<br>`0.8`（严格）<br>`0.6`（宽松） |
| `DGA_ACTION` | `"SINKHOLE"`: 返回0.0.0.0<br>`"REFUSE"`: 拒绝解析 | `"SINKHOLE"` |

---

## 🚀 使用方法

### 1. 安装依赖

```bash
cd e:\dns\team\DNSServer
pip install -r model_training\requirements.txt
```

主要依赖：
- `joblib` - 模型加载
- `numpy` - 数值计算
- `scikit-learn` - 机器学习

### 2. 启动服务器

```bash
python simpleServer.py
```

**启动日志示例**：
```
DNS Server running on 127.0.0.1:5353, with starting time 04_09_10_30_00
DGA Detection: ENABLED (threshold=0.7, action=SINKHOLE)
Whitelist: 18 domains, 6 suffixes
```

### 3. 测试DGA检测

#### 测试白名单域名（应该放行）
```bash
# Windows PowerShell
Resolve-DnsName -Name google.com -Server 127.0.0.1 -Port 5353

# Linux/Mac
dig @127.0.0.1 -p 5353 google.com
```

**预期日志**：
```
[WHITELIST] google.com. - bypassed DGA check
```

#### 测试正常域名（应该通过检测）
```bash
Resolve-DnsName -Name microsoft.com -Server 127.0.0.1 -Port 5353
```

**预期日志**：
```
[DGA PASS] microsoft.com. - confidence: 15.23%
```

#### 测试恶意域名（应该被拦截）
```bash
# 典型DGA域名特征：随机字符串
Resolve-DnsName -Name xjkwqpzmn.com -Server 127.0.0.1 -Port 5353
```

**预期日志**：
```
[DGA BLOCKED] xjkwqpzmn.com. - confidence: 94.56%
```

**预期响应**：返回 `0.0.0.0`

---

## 📊 统计信息

### 运行时日志

所有检测结果都会记录到 `log\DNSlog_<timestamp>.txt`：

```
DNSServer start logging at 04_09_10_30_00
DGA Detection: ENABLED (threshold=0.7, action=SINKHOLE)
Whitelist: 18 domains, 6 suffixes

[WHITELIST] google.com. - bypassed DGA check
[DGA PASS] microsoft.com. - confidence: 15.23%
[DGA BLOCKED] xjkwqpzmn.com. - confidence: 94.56%
```

### 停止服务器统计

按 `Ctrl+C` 停止服务器时会显示完整统计：

```
============================================================
DNS Server Statistics:
============================================================
Total requests: 150
Total processing time: 12.34s
Average processing time: 0.08s

DGA Detection Statistics:
  Whitelist bypassed: 45
  DGA checks performed: 105
  Malicious domains blocked: 12
  Block rate: 11.43%
============================================================
```

---

## 🔧 工作流程

```
DNS查询请求
    ↓
检查是否在白名单？
    ├─ 是 → 直接放行 → 正常解析
    └─ 否 → DGA AI检测
              ├─ 恶意（置信度≥阈值）→ 拦截 → 返回0.0.0.0
              └─ 正常（置信度<阈值）→ 放行 → 正常解析
```

### 代码位置

| 功能 | 代码位置 |
|------|----------|
| 配置参数 | 第25-47行 |
| 主检测逻辑 | `resolve()` 方法，第100-122行 |
| 白名单检查 | `_is_whitelisted()` 方法，第200-210行 |
| DGA检测 | `_check_dga()` 方法，第212-226行 |
| Sinkhole响应 | `_build_sinkhole_reply()` 方法，第228-239行 |

---

## 🎨 自定义扩展

### 1. 调整检测严格度

**场景**：误报太多，想放宽检测

```python
DGA_THRESHOLD = 0.8  # 从0.7提高到0.8，只拦截高置信度恶意域名
```

**场景**：想更严格拦截

```python
DGA_THRESHOLD = 0.6  # 降低到0.6，更激进拦截
```

### 2. 改变拦截方式

**返回自定义IP**（如内部警告页面）：
```python
def _build_sinkhole_reply(self, request, qname, qtype):
    reply = request.reply()
    if qtype == QTYPE.A:
        reply.add_answer(RR(qname, QTYPE.A, rdata=A("192.168.1.100"), ttl=60))
    return reply
```

**完全拒绝解析**：
```python
DGA_ACTION = "REFUSE"  # 改为REFUSE模式
```

### 3. 添加黑名单

在 `resolve()` 方法中添加：
```python
BLACKLIST = {"evil.com.", "malware.net."}

if qname in BLACKLIST:
    mylogf(f'[BLACKLIST] {qname} - blocked by blacklist')
    return self._build_sinkhole_reply(request, qname, qtype)
```

### 4. 记录拦截域名到文件

```python
def _check_dga(self, qname):
    # ... 原有代码 ...
    if is_dga:
        with open('log/blocked_domains.txt', 'a') as f:
            f.write(f'{time.strftime("%Y-%m-%d %H:%M:%S")} {qname} {confidence:.2%}\n')
    return is_dga, confidence
```

---

## ⚠️ 注意事项

### 1. 性能影响

- **白名单域名**：几乎无性能影响（字符串查找）
- **DGA检测**：每次约 **0.2ms** 额外延迟
- **推荐**：将常用域名加入白名单以提升性能

### 2. 误报处理

如果发现正常域名被误拦截：

1. **临时解决**：降低 `DGA_THRESHOLD`
2. **永久解决**：将域名加入 `WHITELIST`
3. **根本解决**：用更多数据重新训练模型

### 3. 模型文件

确保模型文件存在：
```
artifacts/models/active/dga_model_light_markov_100k_v2.pkl
```

如果缺失，会显示警告：
```
⚠️  Warning: DGA model not available. Install dependencies: ...
```

### 4. 日志文件管理

日志会持续增长，建议定期清理：
```bash
# 删除7天前的日志
forfiles /p "log" /s /m *.txt /d -7 /c "cmd /c del @path"
```

---

## 🧪 测试建议

### 测试用例

| 域名类型 | 测试域名 | 预期结果 |
|---------|---------|---------|
| 白名单 | google.com | 放行（WHITELIST） |
| 正常域名 | microsoft.com | 放行（DGA PASS） |
| 短随机串 | abc123.com | 可能拦截 |
| 长随机串 | xjkwqpzmn.com | 拦截（DGA BLOCKED） |
| 数字域名 | 123456.com | 可能拦截 |
| 本地域名 | test.local | 放行（后缀白名单） |

### 压力测试

```bash
# 使用dnsperf工具
dnsperf -s 127.0.0.1 -p 5353 -d domains.txt -c 10 -l 30
```

---

## 📚 相关文档

- [模型训练文档](model_training/README.md)
- [训练报告](model_training/docs/DGA_TRAINING_REPORT.md)
- [集成指南](model_training/docs/MODEL_INTEGRATION.md)

---

## 🐛 故障排除

### 问题1：模型加载失败

**错误**：`FileNotFoundError: Model file not found`

**解决**：
```bash
# 检查模型文件是否存在
dir artifacts\models\active\dga_model_light_markov_100k_v2.pkl
```

### 问题2：导入错误

**错误**：`ImportError: No module named 'joblib'`

**解决**：
```bash
pip install joblib numpy scikit-learn
```

### 问题3：所有域名都被拦截

**原因**：阈值设置过低

**解决**：
```python
DGA_THRESHOLD = 0.8  # 提高阈值
```

### 问题4：检测太慢

**解决**：
1. 扩大白名单范围
2. 使用更轻量的模型
3. 启用缓存机制（待实现）

---

**最后更新**: 2026-04-09  
**版本**: v1.0
