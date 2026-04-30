# DNSServer

## 说明
`pip install -r requirements.txt`安装依赖，如需训练查看模型训练图自行安装matplotlib

**2026/4/7**
这目前还是一个基础版本的DNS服务器，用AI写的，但是已经可以做到向上转发并且查询了
下面是一些使用方法，作为参考：

1) 使用`pip install dnslib` 安装dnslib库
2) 运行`python simpleServer.py`, 可以用`Ctrl ^ C` 打断
3) 开启一个新的Powershell窗口，使用dnslib自带的客户端进行查询，基本格式为`python -m dnslib.client --server <server>:<port> <domain> <type>`, 可以用`python -m dnslib.client --help` 看更详细的用法（这里的服务器和端口用的是`127.0.0.1:5353`, `<type>` 默认为A, e.g. `python -m dnslib.client --server 127.0.0.1:5353 baidu.com AAAA`）

当然也可以用别的，比如dig, nslookup什么的，但dnslib自带的比较方便（其实是因为只有这个跑起来了）

**2026/4/8**
今天完善了一些服务器的功能，现在能够记录查找日志、使用缓存进行查找了，还写了一个用来测试查询速度的.ps1脚本，第一次在Windows上面运行的话需要先用管理员权限打开powershell, 然后更改执行策略`Set-ExecutionPolicy RemoteSigned`, 实验完成之后记得关掉`Set-ExecutionPolicy Restricted`
运行wtest.ps1脚本`./wtest.ps1`；当然Linux的话直接用`bash test.bash`就行

## 一些笔记
为了更好的记录DNS服务器的运行状态，需要在dnslib自带的DNSlogger之外写一个函数，作为DNSlogger的logf参数传进去，比如接受一个字符串，将他写入一个.txt文件，然后打印

**2026/4/30**
将 simpleServer.py 替换为了加入 sqlite3 的版本（由 mjh 完成），然后我修复了一些问题：
- SQL 参数错误：dns.cache.py 中 self.conn.execute("DELETE FROM cache WHERE expire <= ?", now) 改为 self.conn.execute("DELETE FROM cache WHERE expire <= ?", (now,))
- 模块导入错误：dga_runtime 的导入有问题，我把 sys.path 的设置删掉了，因为 dga_runtime.py 在 simpleServer.py 的同级文件夹下，用 from ... import ... 导入就够了（因为现在的 py 不要求有 __init__.py 来识别包了）。后面我们只要保证不更改整个项目的目录结构就不会影响这个模块的导入。
- SQLite 并发安全：引入锁保护，主要是解决 DNSServer 多个线程调用 DNSCache 引发数据库锁错误的问题。由于是 AI 发现和解决的，我不太清楚技术细节
- 缓存策略：之前的 add_records 只会缓存响应中的第一个 A/AAAA 记录。现在可以兼容一问多答了，具体可以通过 wtest.ps1 中 baidu.com d 查询现在会返回 4 条记录来验证。后续我们可以从这里入手实现负载均衡（也就是对于不同的客户端，返回不同的记录，而非 4 条全返回）
- 调用清理：clear_expired() 在之前虽然定义但是没有被调用过；resolver.cache_close() 也新增显式调用
- mylogf 的路径用 os.path.join 替代字符串连接，兼容其他系统的格式
———— by cjq