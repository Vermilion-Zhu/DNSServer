#!/usr/bin/env python3
import subprocess
import time

PYTHON_CMD = "python"
CLIENT_SCRIPT = "dns_client.py"

#服务器地址和端口
SERVER = "127.0.0.1"
PORT = "5353"

# 域名对（前 -> 后）
PAIRS = [
    ("www.taobao.com", "g.alicdn.com"),
]

ROUNDS = 20 

def query(domain, qtype="A"):
    cmd = [PYTHON_CMD, CLIENT_SCRIPT, f"@{SERVER}", domain, qtype, "-p", PORT]
    print(f"Executing: {' '.join(cmd)}")
    result = subprocess.run(cmd)   # 不捕获输出，直接显示
    if result.returncode != 0:
        print(f"Query failed for {domain}")

print("开始训练预加载模型...")
for round_num in range(1, ROUNDS+1):
    for a, b in PAIRS:
        query(a)
        time.sleep(0.2)
        query(b)
        time.sleep(0.2)
    print(f"第 {round_num}/{ROUNDS} 轮完成")
print("训练结束")