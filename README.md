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
- SQL 参数：dns.cache.py 中 self.conn.execute("DELETE FROM cache WHERE expire <= ?", now) 改为 self.conn.execute("DELETE FROM cache WHERE expire <= ?", (now,))
- ~~模块导入：dga_runtime 的导入，把 sys.path 的设置删掉。因为 dga_runtime.py 在 simpleServer.py 的同级文件夹下，换用 from ... import ... 导入即可。~~
- SQLite 并发安全：引入锁保护。因为新增了一个定期清理缓存的线程，需要避免两个函数对数据库的资源竞争。具体的线程创建和释放在这些地方：
  - class HybridResolver 构造函数中的 self._stop_cleaner 和 t。线程 t 开始进入 等待-清理缓存的循环中。
  - if __name__ == '__main__' 下 except KeyboardInterrupt 的  resolver._stop_cleaner.set()。会使得 _periodic_cleanup 中 while 循环终止，进而函数结束，释放线程 t 的资源。
- 缓存策略：之前的 add_records 只会缓存响应中的第一个 A/AAAA 记录。现在可以兼容一问多答了。（可通过 wtest.ps1 中 baidu.com d 查询现在会返回 4 条记录来验证）
- 调用清理：clear_expired() 在之前虽然定义但是没有被调用过；resolver.cache_close() 也新增显式调用
- 日志路径兼容：mylogf 的路径用 os.path.join 替代字符串连接，兼容其他系统的格式
———— by cjq

**2026/5/10**
修复问题：
- 上一版本中无论向上转发的请求是否收到正确的响应都会进行缓存，现在仅仅在符合预期的情况下才会缓存：
    ```
    if getattr(reply, 'header', None) and reply.header.rcode == RCODE.NOERROR and not reply.tc and reply.rr:
        self.add_records(reply, qname)
    else:
        mylogf(f'[UPSTREAM ERROR] {qname} - RCODE: {reply.header.rcode if getattr(reply, "header", None) else "N/A"}, TC: {getattr(reply, "tc", "N/A")}, RR count: {len(getattr(reply, "rr", []))}')
    ```
- 上一次的 DGA 模块导入还有问题。把 model_training/dga_runtime.py 中导入包内模块改成相对导入了（加上 "from ."），如果需要把模块作为脚本测试，需要在 python 命令后加 "-m" 参数
———— by cjq