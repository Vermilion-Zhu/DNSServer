# DGA Detector & DNS Query GUI

基于 tkinter 的 DNS 查询与 DGA（域名生成算法）检测图形界面工具。

## 功能特性

### 🔍 DNS 查询
- **缓存优先策略**：与 `simpleServer.py` 一致，先查 SQLite 缓存，命中则直接返回
- 支持自定义 DNS 服务器和记录类型（A/AAAA/MX/TXT/CNAME/NS）
- 缓存命中时显示剩余 TTL

### 🛡️ DGA 检测
- 基于 AI 模型（Markov 链）实时检测 DGA 恶意域名
- 可调节检测阈值（0.0~1.0）
- **白名单机制**：与 `simpleServer.py` 共享白名单配置（通过 `config.py`）

### 📦 批量检测
- 支持 JSON 文件批量导入域名
- 批量 DGA 检测结果以表格形式展示
- 导出为 JSON 或 CSV 格式

### 🖥️ DNS 服务器管理
- 一键启动/停止本地 DNS 服务器（`simpleServer.py`，端口 5353）
- 启动后自动将查询指向本地服务器

### 💾 缓存管理
- 查看缓存统计（总记录数、有效/过期）
- 浏览最近 20 条缓存记录
- 一键清理过期缓存

### 🔄 Git 集成
- 拉取远程仓库更新并自动重载 DGA 模型
- 查看仓库状态

## 项目架构

```
DNSServer/
├── config.py              ← 共享配置（白名单、阈值、端口等）
├── dns_cache.py           ← SQLite DNS 缓存
├── simpleServer.py        ← DNS 服务器（使用 config.py）
├── model_training/
│   └── dga_runtime.py     ← DGA 检测模型
├── tools/
│   ├── dga_gui/
│   │   ├── dga_gui.py     ← GUI 主程序（使用 config.py + dns_cache.py）
│   │   └── sample_domains.json
│   └── dns_query/
│       └── dns_client.py  ← DNS 查询客户端
```

**关键设计**：GUI 通过 `config.py` 与 `simpleServer.py` 共享配置，避免代码重复。

## 使用方法

```bash
# 从项目根目录运行
python tools/dga_gui/dga_gui.py

# 或作为模块运行
python -m tools.dga_gui.dga_gui
```

## 依赖

```bash
pip install -r requirements.txt
```

核心依赖：
- `tkinter`（Python 内置）
- `dnspython` — DNS 查询
- `dnslib` — DNS 服务器与缓存
- `scikit-learn` / `joblib` — DGA 模型推理