# DNSServer

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