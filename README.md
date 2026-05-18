# DNSServer 项目说明文档

> 带有 DGA（域名生成算法）恶意域名检测功能的智能 DNS 服务器

---

## 📋 目录

- [项目简介](#项目简介)
- [技术栈](#技术栈)
- [项目结构](#项目结构)
- [核心模块详解](#核心模块详解)
  - [DNS 服务器核心](#1-dns-服务器核心--simpleserverpy)
  - [DNS 缓存层](#2-dns-缓存层--dns_cachepy)
  - [共享配置中心](#3-共享配置中心--configpy)
  - [统一日志模块](#4-统一日志模块--loggerpy)
  - [DGA 检测模块](#5-dga-检测模块--model_training)
  - [GUI 可视化工具](#6-gui-可视化工具--toolsdga_gui)
  - [DNS 命令行客户端](#7-dns-命令行客户端--toolsdns_query)
- [数据流与处理流程](#数据流与处理流程)
- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [模型训练](#模型训练)
- [项目特点](#项目特点)
- [开发历史](#开发历史)

---

## 项目简介

本项目是一个基于 Python 的 DNS 服务器，在基础 DNS 解析功能之上集成了机器学习驱动的 DGA 恶意域名实时检测能力。服务器接收到 DNS 查询后，会先通过 AI 模型判断域名是否为 DGA 生成的恶意域名，若判定为恶意则返回 Sinkhole 响应（`0.0.0.0`），从而阻断恶意域名的解析。

**核心能力：**

- 🌐 标准 DNS 解析（A / AAAA / CNAME / MX / TXT）
- 🛡️ AI 驱动的 DGA 恶意域名实时检测与拦截
- 💾 SQLite 持久化缓存，支持 TTL 过期与后台自动清理
- 🔗 CNAME 链递归解析（最大深度 5）
- 🖥️ GUI 可视化工具与 CLI 查询工具
- ⚙️ 集中化配置管理，白名单机制

---

## 技术栈

| 类别 | 技术 | 用途 |
|------|------|------|
| DNS 服务 | `dnslib` | DNS 服务器框架（解析、转发、响应构建） |
| DNS 查询 | `dnspython` | DNS 客户端查询（UDP/TCP） |
| 机器学习 | `scikit-learn` (RandomForest) | DGA 域名分类模型训练与推理 |
| 模型序列化 | `joblib` | 模型持久化（`.pkl` 格式） |
| 数值计算 | `numpy` | 特征向量构建与推理计算 |
| 缓存存储 | `sqlite3` (Python 内置) | DNS 记录缓存（带 TTL 过期机制） |
| GUI | `tkinter` (Python 内置) | DGA 检测 & DNS 查询可视化工具 |
| 并发控制 | `threading` (Python 内置) | 缓存定期清理后台线程、SQLite 锁保护 |

---

## 项目结构

```
DNSServer/
├── simpleServer.py              # 🟢 核心入口：DNS 服务器 (HybridResolver)
├── dns_cache.py                 # 🟢 缓存层：SQLite DNS 缓存（正向 + 否定缓存）
├── config.py                    # 🟢 配置中心：端口/上游/DGA/白名单
├── logger.py                    # 🟢 统一日志：DNSLogger + 多 Handler 架构
├── prefetcher.py                # 🟢 启发式预加载管理器
├── requirements.txt             # 依赖清单
├── README.md                    # 本文档：项目说明
├── README_OLD.md                # 旧版开发日志（归档）
├── test.bash                    # Linux 测试脚本
├── wtest.ps1                    # Windows 测试脚本
│
├── model_training/              # 🔵 DGA 模型训练与运行时
│   ├── __init__.py
│   ├── train_dga_model.py       #   特征提取 + 模型训练脚本
│   ├── dga_runtime.py           #   推理运行时（单条/批量预测）
│   ├── classifier.py            #   启发式 DGA 检测器（旧版/备用）
│   ├── bench_inference.py       #   推理性能基准测试
│   ├── README.md                #   模型训练说明
│   └── docs/
│       ├── DGA_TRAINING_REPORT.md   # 训练报告
│       └── MODEL_INTEGRATION.md     # 模型集成文档
│
├── tools/
│   ├── demo_api.py              # 🟠 演示 API：DNS 解析步骤可视化 API
│   ├── dga_gui/                 # 🟣 GUI 可视化工具
│   │   ├── __init__.py
│   │   ├── dga_gui.py           #   tkinter 主界面
│   │   ├── dga_utils.py         #   DGA 检测封装（懒加载）
│   │   ├── query.py             #   DNS 查询 + 缓存封装（含否定缓存支持）
│   │   ├── sample_domains.json  #   示例域名数据
│   │   ├── test_gui.py          #   GUI 测试
│   │   └── README.md            #   GUI 使用说明
│   └── dns_query/               # 🟡 CLI 查询工具
│       ├── __init__.py
│       └── dns_client.py        #   dig 风格命令行 DNS 客户端
│       └── train_prefetch.py    #   prefetch测试
│
├── docs/
│   └── demo.html                # 🎬 DNS 解析动画演示（纯静态 HTML）
│
└── artifacts/                   # 📦 模型产物
    └── models/
        └── active/
            └── dga_model_light_markov_100k_v2.pkl  # 当前活跃模型
```

---

## 核心模块详解

### 1. DNS 服务器核心 — `simpleServer.py`

**核心类：`HybridResolver`**

`HybridResolver` 是整个 DNS 服务器的核心解析器，实现了 `dnslib.server.DNSResolver` 接口，负责处理所有传入的 DNS 查询请求。构造函数接受 `upstream` 参数指定上游 DNS 服务器地址（默认 `"8.8.8.8"`）。

**命令行参数：**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--upstream` | `8.8.8.8`（来自 `config.UPSTREAM_DNS`） | 上游 DNS 服务器地址 |

```bash
# 使用默认上游
python simpleServer.py

# 指定上游 DNS
python simpleServer.py --upstream 1.1.1.1
```

**解析流程（`resolve()` 方法）：**

```
请求进入
  │
  ├─ 1. 白名单检查 → 命中则跳过 DGA 检测
  ├─ 2. DGA AI 检测 → 恶意则返回 Sinkhole 响应
  ├─ 3. 否定缓存查询（RFC 2308） → NXDOMAIN 命中则返回含 SOA 的 NXDOMAIN
  ├─ 4. SQLite 正向缓存查询 → 命中则直接返回
  ├─ 5. CNAME 缓存查询 → 命中则递归解析返回
  ├─ 6. 上游 DNS 转发
  │     ├─ NOERROR → 缓存写入 + CNAME 链解析 + 返回
  │     ├─ NXDOMAIN → 提取 SOA 写入否定缓存 + 返回 NXDOMAIN
  │     └─ 其他/失败 → 返回 SERVFAIL
  └─ 7. 统计更新
```

**关键方法：**

| 方法 | 功能 |
|------|------|
| `resolve(request, handler)` | 主解析入口，串联所有处理流程 |
| `_is_whitelisted(qname)` | 白名单检查（委托给 `config.is_whitelisted`） |
| `_check_dga(qname)` | 调用 DGA 模型检测域名 |
| `_build_sinkhole_reply(request, qname, qtype)` | 构建拦截响应（A→0.0.0.0, AAAA→::） |
| `_forward(request)` | 通过 UDP Socket 转发查询到上游 DNS |
| `add_records(reply, qname)` | 将响应记录写入正向缓存 |
| `_resolve_cname_chain(reply, ...)` | 递归解析 CNAME 链（最大深度 5） |
| `_build_reply(request, qname, qtype, rdata, ttl)` | 根据查询类型构建 DNS 响应 |
| `_build_nxdomain_reply(request, qname, soa_rdata, ttl)` | 构建 NXDOMAIN 响应，Authority 段含 SOA（RFC 2308） |
| `_extract_soa(reply)` | 从上游 NXDOMAIN 响应的 Authority 段提取 SOA 记录 |

**日志系统：**

- 使用统一日志模块 [`logger.py`](logger.py) 的 `DNSLogger`，注册 `FileHandler` + `ConsoleHandler`
- 日志格式：`[YYYY-MM-DD HH:MM:SS] [LEVEL] [TAG] message`
- 统一标签体系：`CACHE_HIT`、`CACHE_SET`、`NEG_CACHE_HIT`、`NEG_CACHE_SET`、`NXDOMAIN`、`DGA_BLOCKED`、`DGA_PASS`、`WHITELIST`、`UPSTREAM_ERR`、`FORWARD_ERR`、`CNAME_CHAIN` 等
- 日志级别：`INFO` / `WARN` / `ERROR`

**统计报告：**

服务器关闭时（`Ctrl+C`）输出统计信息：
- 总请求数、总处理时间、平均处理时间
- DGA 检测次数、拦截次数、白名单跳过次数、拦截率

---

### 2. DNS 缓存层 — `dns_cache.py`

**核心类：`DNSCache`**

基于 SQLite 的 DNS 记录持久化缓存，支持 TTL 过期与线程安全操作。

**数据库表结构：**

正向缓存：
```sql
CREATE TABLE cache (
    domain TEXT,
    qtype  INTEGER,
    rdata  TEXT,       -- JSON 编码，兼容多值记录
    ttl    INTEGER,
    expire INTEGER,    -- Unix 时间戳，过期时间
    PRIMARY KEY (domain, qtype)
);
```

否定缓存（RFC 2308）：
```sql
CREATE TABLE neg_cache (
    domain    TEXT,
    qtype     INTEGER,
    soa_rdata TEXT,     -- SOA 记录 JSON（mname, rname, serial, refresh, retry, expire, minimum）
    ttl       INTEGER,
    expire    INTEGER,  -- Unix 时间戳，过期时间
    PRIMARY KEY (domain, qtype)
);
```

**关键特性：**

| 特性 | 实现方式 |
|------|----------|
| **线程安全** | `threading.Lock()` 保护所有数据库操作 |
| **TTL 过期** | 查询时检查 `expire` 字段，过期则删除并返回 `None` |
| **多值支持** | `rdata` 使用 JSON 编码，支持一问多答（如 `baidu.com` 返回 4 条 A 记录） |
| **后台清理** | 服务器启动时创建 daemon 线程，每 60 秒清理过期记录 |
| **优雅退出** | `KeyboardInterrupt` 时通过 `Event.set()` 终止清理线程，显式关闭数据库连接 |

**API 方法：**

| 方法 | 功能 |
|------|------|
| `get(domain, qtype)` | 正向缓存查询，返回 `(rdata, remaining_ttl)` 或 `None` |
| `set(domain, qtype, rdata, ttl)` | 正向缓存写入，自动计算过期时间 |
| `delete(domain, qtype)` | 删除指定正向记录 |
| `get_negative(domain, qtype)` | 否定缓存查询，返回 `(soa_rdata_dict, remaining_ttl)` 或 `None` |
| `set_negative(domain, qtype, soa_rdata, ttl)` | 否定缓存写入（TTL 取 SOA minimum 字段） |
| `delete_negative(domain, qtype)` | 删除指定否定记录 |
| `clear_expired()` | 清理所有过期记录（正向 + 否定缓存） |
| `close()` | 关闭数据库连接 |

---

### 3. 共享配置中心 — `config.py`

集中管理所有配置常量，避免跨模块重复定义，供 `simpleServer.py`、GUI 工具等全局复用。

**配置项一览：**

```python
# DNS 服务器配置
PORT = 5353                    # 监听端口
ADDRESS = "127.0.0.1"          # 监听地址
UPSTREAM_DNS = "8.8.8.8"       # 上游 DNS 服务器

# DGA 检测配置
ENABLE_DGA_DETECTION = True    # 是否启用 DGA 检测
DGA_THRESHOLD = 0.7            # 置信度阈值（70%）
DGA_ACTION = "SINKHOLE"        # 拦截动作：SINKHOLE（返回 0.0.0.0）或 REFUSE

# 白名单
WHITELIST = { ... }            # 精确匹配白名单（含末尾点号）
WHITELIST_SUFFIXES = { ... }   # 后缀匹配白名单
```

**白名单机制：**

- **精确匹配**：域名必须完全匹配（包括末尾的点号），如 `"baidu.com."`
- **后缀匹配**：域名以指定后缀结尾即信任，如 `".cn."` 匹配所有 `.cn` 域名
- **工具函数**：`is_whitelisted(qname)` 封装了两种匹配逻辑，全局复用

---

### 4. 统一日志模块 — `logger.py`

**核心类：`DNSLogger`**

提供跨组件的统一日志基础设施，替代原先 `simpleServer.py` 中的 `mylogf()` 全局函数和 `dga_gui.py` 中的 `_log()` 方法。

**架构设计：**

```
DNSLogger (统一日志器)
  ├── FileHandler      → 写入 log/DNSlog_{时间戳}.txt
  ├── ConsoleHandler   → 控制台 print 输出
  └── WidgetHandler    → tkinter ScrolledText 控件（线程安全 via root.after）
```

**日志格式：**

```
[YYYY-MM-DD HH:MM:SS] [LEVEL] [TAG] message
```

**日志级别：**

| 级别 | 用途 | 示例 |
|------|------|------|
| `INFO` | 常规操作信息 | 缓存命中、DGA 通过、查询完成 |
| `WARN` | 需要注意的情况 | DGA 拦截、上游错误、本地服务器未运行 |
| `ERROR` | 错误与异常 | 转发失败、清理异常、检测失败 |

**统一标签体系：**

| 标签 | 含义 | 使用场景 |
|------|------|----------|
| `CACHE_HIT` | 缓存命中 | 正向缓存查询命中 |
| `CACHE_SET` | 缓存写入 | 写入正向缓存记录 |
| `CACHE_SET_CNAME` | CNAME 缓存写入 | 写入 CNAME 缓存记录 |
| `NEG_CACHE_HIT` | 否定缓存命中 | 否定缓存命中，返回 NXDOMAIN |
| `NEG_CACHE_SET` | 否定缓存写入 | 写入否定缓存（含 SOA TTL） |
| `NXDOMAIN` | 域名不存在 | 上游返回 NXDOMAIN |
| `DGA_BLOCKED` | DGA 拦截 | 检测到恶意域名并拦截 |
| `DGA_PASS` | DGA 通过 | 域名检测为正常 |
| `WHITELIST` | 白名单 | 域名在白名单中跳过检测 |
| `UPSTREAM_ERR` | 上游错误 | 上游 DNS 返回错误响应 |
| `FORWARD_ERR` | 转发错误 | 转发查询到上游失败 |
| `CNAME_CHAIN` | CNAME 链 | CNAME 链递归解析 |
| `CNAME_RESOLVED` | CNAME 解析完成 | CNAME 链解析得到最终 IP |
| `CLEANUP_ERR` | 清理错误 | 缓存清理线程异常 |
| `SERVER` | 服务器 | 服务器启停、状态信息 |
| `QUERY` | 查询 | GUI 发起 DNS 查询 |
| `BATCH` | 批量检测 | GUI 批量检测操作 |
| `DGA` | DGA 检测 | GUI DGA 检测结果 |
| `CACHE` | 缓存管理 | GUI 缓存统计/清理 |
| `DNSLIB` | dnslib 日志 | dnslib 框架内部日志桥接 |

**Handler 详解：**

| Handler | 输出目标 | 线程安全 | 使用者 |
|---------|----------|----------|--------|
| `FileHandler` | 日志文件（每次启动新建） | `threading.Lock` | 服务器 |
| `ConsoleHandler` | 控制台 `print` | 无状态 | 服务器 |
| `WidgetHandler` | tkinter `ScrolledText` | `root.after(0, ...)` | GUI |

**使用示例：**

```python
# 服务器端 (simpleServer.py)
from logger import DNSLogger, FileHandler, ConsoleHandler

logger = DNSLogger("DNSServer")
logger.add_handler(FileHandler("log", "DNSlog"))
logger.add_handler(ConsoleHandler())

logger.info("CACHE_HIT", f"{qname} -> {rdata} (remaining TTL: {ttl}s)")
logger.warn("DGA_BLOCKED", f"{qname} - confidence: {confidence:.2%}")
logger.error("FORWARD_ERR", str(e))

# GUI 端 (dga_gui.py)
from logger import DNSLogger, WidgetHandler

logger = DNSLogger("DGA_GUI")
logger.add_handler(WidgetHandler(self.log_txt, self.root))

logger.info("QUERY", f"查询 {domain} {qtype} @ {server}:{port}...")
```

**GUI 服务器子进程日志捕获：**

GUI 启动本地 DNS 服务器时，通过后台线程实时读取子进程 `stdout` 输出并转发到统一日志器，使服务器日志在 GUI 日志区实时可见：

```python
# stderr 合并到 stdout，后台线程逐行读取
self._dns_server_process = subprocess.Popen(
    [...], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, ...)

def _read_stdout():
    for line in iter(process.stdout.readline, b""):
        text = line.decode("utf-8", errors="replace").rstrip()
        if text:
            logger.info("SERVER", text)
```

---

### 5. DGA 检测模块 — `model_training/`

#### 4.1 特征工程 — `train_dga_model.py`

从域名中提取多维度特征用于机器学习分类：

| 特征类别 | 特征项 | 维度 | 说明 |
|----------|--------|------|------|
| **基础词法** | length | 1 | 域名主体长度 |
| | vowel_ratio | 1 | 元音字母占比 |
| | digit_ratio | 1 | 数字占比 |
| | entropy | 1 | Shannon 信息熵 |
| | consonant_run | 1 | 最长辅音连续长度 |
| **N-gram 哈希桶** | 2-gram buckets | 128 | 2-gram 的 MD5 哈希分桶频率统计 |
| | 3-gram buckets | 128 | 3-gram 的 MD5 哈希分桶频率统计 |
| **Markov 链** | avg_logp | 1 | 字符转移平均对数概率 |
| | min_logp | 1 | 字符转移最小对数概率 |
| | low_prob_ratio | 1 | 低概率转移占比 |
| | perplexity | 1 | 困惑度 |

**域名预处理：** `normalize_domain()` — 小写化、去末尾点号、正则校验、长度限制（4~50）

#### 4.2 推理运行时 — `dga_runtime.py`

提供单条和批量 DGA 检测接口，支持模型懒加载与缓存：

| 函数 | 功能 |
|------|------|
| `predict(domain, threshold)` | 单域名预测，返回 `(is_dga, confidence)` |
| `predict_many(domains, threshold)` | 批量预测，返回 `(is_dga_list, scores_list)` |
| `load_artifact(model_path)` | 加载模型产物（兼容新旧格式） |
| `model_info(model_path)` | 获取模型元信息 |
| `reset()` | 清除缓存模型，下次重新加载 |

**模型兼容性：**

- **新格式**：`dict`，包含 `model` + `feature_config` + `markov_model`
- **旧格式**：直接是 sklearn 模型对象，自动填充默认配置
- **维度对齐**：`_align_feature_dim()` 自动补零或截断，兼容不同版本模型

**当前活跃模型：** `artifacts/models/active/dga_model_light_markov_100k_v2.pkl`

#### 4.3 启发式检测器 — `classifier.py`

基于规则的备用 DGA 检测方案，不依赖 ML 模型：

- 熵 > 3.2 → +0.3
- 元音比 < 0.25 → +0.2
- 数字比 > 0.15 → +0.2
- 辅音连续 > 4 → +0.3
- 长度 > 12 → +0.2
- 随机字符序列 ≥ 10 → +0.2

#### 4.4 推理基准测试 — `bench_inference.py`

测量模型推理性能，支持批量推理和 warmup，输出 QPS 和平均延迟。

---

### 6. GUI 可视化工具 — `tools/dga_gui/`

基于 tkinter 的桌面应用，集成 DNS 查询与 DGA 检测功能。GUI 启动时自动启动本地 DNS 服务器子进程，所有查询均通过本地服务器进行。

**启动方式：**

```bash
python tools/dga_gui/dga_gui.py
# 或
python -m tools.dga_gui.dga_gui
```

**架构设计：**

GUI 以子进程方式启动 `simpleServer.py`，通过 `--upstream` 参数传递上游 DNS 配置。GUI 与服务器之间通过标准 DNS 协议（`127.0.0.1:5353`）通信，服务器端功能（DGA 检测、缓存、负载均衡等）的变更不影响 GUI 代码。

```
┌─────────────────────────────────────────────┐
│  DGAGuiApp (tkinter)                        │
│  ├── 自动启动 simpleServer.py 子进程         │
│  │   └── subprocess.Popen([..., "--upstream",│
│  │       upstream_dns], ...)                │
│  ├── 所有 DNS 查询 → 127.0.0.1:5353         │
│  ├── 子进程 stdout → 日志区实时显示          │
│  └── 关闭时自动终止子进程                    │
└─────────────────────────────────────────────┘
         │ DNS queries (UDP)
         ▼
┌─────────────────────────────────────────────┐
│  simpleServer.py (子进程)                    │
│  ├── HybridResolver(upstream=...)           │
│  ├── DGA 检测 + 缓存 + 转发                 │
│  └── 监听 127.0.0.1:5353                    │
└─────────────────────────────────────────────┘
```

**功能概览：**

| 功能 | 说明 |
|------|------|
| 自动启动服务器 | GUI 启动时自动启动本地 DNS 服务器子进程 |
| 上游 DNS 配置 | 可修改上游 DNS 服务器地址，重启服务器生效 |
| 单域名查询 | 输入域名，选择记录类型（A/AAAA/CNAME），通过本地服务器查询并显示 DGA 结果 |
| JSON 批量检测 | 从 JSON 文件加载域名列表批量检测，Treeview 表格展示结果，支持进度反馈与取消 |
| 否定缓存可视化 | 批量结果中区分显示缓存命中 / NXDOMAIN（否定缓存）/ 上游查询 |
| DGA 阈值调节 | 滑块实时调节检测阈值（0.0~1.0） |
| DNS 缓存开关 | 可选择是否使用本地缓存 |
| 白名单开关 | 可选择是否启用白名单跳过 |
| 批量进度反馈 | 进度条 + 进度标签显示批量检测进度 |
| 任务取消 | 批量检测过程中可随时取消 |
| 缓存管理 | 查看缓存统计、清理过期记录 |
| 结果导出 | 将单域名或批量检测结果导出为 JSON / CSV 文件 |
| 仓库状态 | 查看 Git 仓库状态 |

**关键 UI 组件：**

- **服务器状态栏**：显示运行状态 `● 运行中 (127.0.0.1:5353 → 8.8.8.8)`，包含上游 DNS 输入框和重启按钮
- **单域名输入行**：域名输入框 + 记录类型选择（A / AAAA / CNAME），始终可见
- **批量输入行**：JSON 文件路径 + 浏览按钮 + 记录类型选择，始终可见
- **独立操作按钮**：`🔍 单域名查询` / `📦 批量查询`，互不干扰
- **DNS 查询结果区**：ScrolledText 显示 DNS 查询详细结果 + 缓存命中状态
- **DGA 检测结果区**：单域名标签（域名 / DGA 分数 / 判定）+ Treeview 批量结果表格
- **进度条**：批量检测时显示确定进度，单条检测时显示不确定进度
- **取消按钮**：批量检测过程中可点击取消，通过 `threading.Event` 通知工作线程

**子模块：**

- `dga_utils.py` — DGA 运行时懒加载封装，避免启动时加载模型
- `query.py` — DNS 查询 + 缓存策略封装，与服务器端逻辑一致

---

### 7. DNS 命令行客户端 — `tools/dns_query/dns_client.py`

dig 风格的命令行 DNS 查询工具。

**使用方式：**

```bash
# 查询本地服务器
python tools/dns_query/dns_client.py @127.0.0.1 example.com A

# 查询默认服务器
python tools/dns_query/dns_client.py example.com AAAA
```

**特性：**

- `@server` 语法指定 DNS 服务器
- UDP 优先、TCP 回退策略
- 格式化输出 Question / Answer / Authority / Additional 各段
- 未指定服务器时自动使用系统默认 DNS

---
### 8. 启发式预加载模块 — `prefetcher.py`

**核心类：`PrefetchManager`**

基于滑动窗口与共现矩阵的智能域名预加载模块。通过分析历史查询模式，自动学习高置信度的“伴随域名”对（例如 `www.taobao.com` 后常跟随 `g.alicdn.com`），并在后台提前将目标域名解析结果写入本地缓存，从而大幅降低用户后续访问延迟。

**工作原理：**

1. **记录阶段**：每次 DNS 查询到达时，`resolve()` 方法将域名（`qname`）推入无界队列，后台线程 `_record_worker` 从队列中取出域名，更新滑动窗口历史与共现矩阵。
2. **学习阶段**：周期性分析（默认 30 秒）共现矩阵，计算条件概率 `P(B|A) = count(A,B)/count(A)`。当置信度超过阈值（默认 0.7）且共现次数 ≥ 最小计数（默认 3）时，生成预加载候选对。
3. **预取阶段**：对每个候选对中的目标域名 `B`，调用 `_forward()` 向上游 DNS 发起一次真实查询，并将解析结果通过 `add_records()` 写入 SQLite 缓存。后续用户请求 `B` 时直接缓存命中。

**配置参数（位于 `prefetcher.py` 文件头部）：**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `SLIDING_WINDOW_SIZE` | 200 | 滑动窗口大小 |
| `CORRELATION_BACKTRACK` | 15 | 回溯步长 |
| `MIN_COUNT` | 3 | 阈值 |
| `CONFIDENCE_THRESHOLD` | 0.7 | 预加载置信度阈值 |
| `PREFETCH_INTERVAL_SEC` | 30 | 预加载分析周期（秒） |
| `PREFETCH_QTYPE` | `'A'` | 预加载时查询的记录类型 |

**线程模型：**

- **记录工作线程** (`PrefetchRecordWorker`)：从队列取出域名，更新历史与共现矩阵。
- **预加载定时器线程** (`PrefetchAnalyzer`)：每隔 `PREFETCH_INTERVAL_SEC` 秒分析并执行预加载。
- 两个线程均为 `daemon`，服务器退出时由 `prefetch_mgr.stop()` 安全终止。

**集成方式（`simpleServer.py` 中）：**

```python
from prefetcher import PrefetchManager

class HybridResolver:
    def __init__(self, upstream="8.8.8.8"):
        # ... 原有代码 ...
        self.prefetch_mgr = PrefetchManager(self)
        self.prefetch_mgr.start()

    def resolve(self, request, handler):
        qname = str(request.q.qname)
        self.prefetch_mgr.record_query(qname)   # 记录查询
        # ... 其余解析流程 ...
```
---

## 数据流与处理流程

```
                          客户端 DNS 查询
                                │
                                ▼
                    ┌───────────────────────┐
                    │  HybridResolver       │
                    │    .resolve()         │
                    └───────────┬───────────┘
                                │
                    ┌───────────▼───────────┐
                    │  白名单检查            │
                    │  _is_whitelisted()    │
                    └───┬───────────────┬───┘
                        │ 命中          │ 未命中
                        ▼               ▼
                   跳过 DGA     ┌───────────────┐
                                │ DGA AI 检测    │
                                │ _check_dga()  │
                                └──┬─────────┬──┘
                                   │ 正常    │ 恶意
                                   ▼         ▼
                            ┌──────────┐  Sinkhole
                            │ 缓存查询  │  响应
                            │ cache.get│  (0.0.0.0)
                            └──┬────┬──┘
                               │命中│未命中
                               ▼    ▼
                          直接返回  ┌──────────────┐
                                   │ CNAME 缓存查询 │
                                   └──┬─────────┬──┘
                                      │命中     │未命中
                                      ▼         ▼
                                 递归解析    ┌──────────────┐
                                 返回结果    │ 上游 DNS 转发  │
                                            │ _forward()    │
                                            └──┬─────────┬──┘
                                               │成功      │失败
                                               ▼          ▼
                                         缓存写入     返回 SERVFAIL
                                         返回响应
```

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

如需训练模型或查看训练图表，额外安装：

```bash
pip install matplotlib
```

### 2. 启动 DNS 服务器

```bash
# 使用默认上游 DNS (8.8.8.8)
python simpleServer.py

# 指定上游 DNS 服务器
python simpleServer.py --upstream 1.1.1.1
```

服务器默认监听 `127.0.0.1:5353`，上游 DNS 为 `8.8.8.8`。

### 3. 使用 GUI 工具（推荐）

```bash
python tools/dga_gui/dga_gui.py
```

GUI 启动后自动启动本地 DNS 服务器，可直接进行 DNS 查询和 DGA 检测。可在界面中修改上游 DNS 服务器并重启。

### 4. 测试查询

**方式一：使用 dnslib 自带客户端**

```bash
python -m dnslib.client --server 127.0.0.1:5353 baidu.com A
python -m dnslib.client --server 127.0.0.1:5353 baidu.com AAAA
```

**方式二：使用项目自带客户端**

```bash
python tools/dns_query/dns_client.py @127.0.0.1 baidu.com A
```

**方式三：使用 GUI 工具**

```bash
python tools/dga_gui/dga_gui.py
```

### 5. 运行测试脚本

**Windows (PowerShell)：**

```powershell
# 首次需更改执行策略（管理员权限）
Set-ExecutionPolicy RemoteSigned
./wtest.ps1
# 实验完成后恢复
Set-ExecutionPolicy Restricted
```

**Linux：**

```bash
bash test.bash
```

### 6. 停止服务器

- **独立运行**：按 `Ctrl+C` 停止服务器，将输出统计报告并优雅关闭缓存和清理线程
- **GUI 模式**：关闭 GUI 窗口时自动终止服务器子进程

---

## 配置说明

所有配置集中在 `config.py`，修改后重启服务器生效。部分参数支持通过命令行参数覆盖，无需修改配置文件。

### DNS 服务器配置

| 参数 | 默认值 | 说明 | CLI 覆盖 |
|------|--------|------|----------|
| `PORT` | `5353` | DNS 服务器监听端口 | — |
| `ADDRESS` | `"127.0.0.1"` | 监听地址 | — |
| `UPSTREAM_DNS` | `"8.8.8.8"` | 上游 DNS 服务器地址 | `--upstream` |

### DGA 检测配置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `ENABLE_DGA_DETECTION` | `True` | DGA 检测总开关 |
| `DGA_THRESHOLD` | `0.7` | 置信度阈值（0.6 宽松 / 0.7 平衡 / 0.8 严格） |
| `DGA_ACTION` | `"SINKHOLE"` | 拦截动作：`SINKHOLE` 返回 0.0.0.0，`REFUSE` 拒绝解析 |

### 白名单配置

**精确匹配**（需含末尾点号）：

```python
WHITELIST = {
    "google.com.", "baidu.com.", "github.com.",
    # 添加更多信任域名...
}
```

**后缀匹配**：

```python
WHITELIST_SUFFIXES = {
    ".local.", ".localhost.", ".test.",
    ".cn.", ".edu.cn.", ".gov.cn.",
    # 添加更多信任后缀...
}
```

---

## 模型训练

详见 [`model_training/README.md`](model_training/README.md) 和 [`model_training/docs/DGA_TRAINING_REPORT.md`](model_training/docs/DGA_TRAINING_REPORT.md)。

**训练脚本：**

```bash
python -m model_training.train_dga_model --help
```

**推理基准测试：**

```bash
python -m model_training.bench_inference --model artifacts/models/active/dga_model_light_markov_100k_v2.pkl
```

---

## 项目特点

1. **AI 增强安全**：RandomForest + Markov 链特征模型集成到 DNS 解析流程，实现实时 DGA 检测与拦截
2. **双层缓存体系**：SQLite 正向缓存（A/AAAA/CNAME）+ RFC 2308 否定缓存（NXDOMAIN 含 SOA），TTL 过期自动清理
3. **多工具协同**：CLI 客户端 + GUI 桌面应用 + 纯静态 HTML 演示动画，覆盖不同使用场景
4. **统一配置与日志**：`config.py` 集中管理所有参数 → `logger.py` 多 Handler 架构（文件/控制台/GUI 控件）
5. **GUI 深度集成**：GUI 子进程启动服务器 + 实时日志捕获 + 上游 DNS 可配 + 批量进度反馈 + 取消

---

## 开发历史

| 日期 | 里程碑 |
|------|--------|
| 2026/4/7 | 基础版 DNS 服务器，支持向上转发查询 |
| 2026/4/8 | 新增查询日志、SQLite 缓存、测试脚本 |
| 2026/4/30 | 引入 SQLite 替换内存缓存；修复 SQL 参数、并发安全、缓存策略、日志路径兼容等问题 |
| 2026/5/10 | 修复仅正确响应才缓存的问题；DGA 模块改用相对导入；新增 DNS 客户端工具 |
| 2026/5/10+ | 集成 DGA 检测模块、GUI 可视化工具、集中化配置 |
| 2026/5/13 | 提取统一日志模块 `logger.py`，合并服务器与 GUI 日志系统；GUI 捕获服务器子进程输出 |
| 2026/5/13 | GUI 架构重构：自动启动本地服务器、上游 DNS 可配置、批量进度反馈与任务取消、`--upstream` CLI 参数 |
| 2026/5/14 | RFC 2308 否定缓存：NXDOMAIN 含 SOA 缓存；GUI 双模式去除 + 独立按钮；导出支持单域名；多IP展示修复 |
| 2026/5/14 | DNS 演示动画：3 场景纯静态 HTML（递归解析/DGA拦截/实时查询），AI 特征可视化，步骤时间线 |
| 2026/5/18 | 实现启发式预加载模块 (prefetcher.py)：滑动窗口统计、共现矩阵、置信度判定、后台周期性预加载，有效提升伴随域名解析速度。 |

