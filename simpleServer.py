#!/usr/bin/env python3
#A simple DNS server that supports A, AAAA, CNAME requests
#REMEMBER TO DISABLE .ps1 SCRIPTS AFTER THE EXPERIMENT!

from dnslib import DNSRecord, RR, QTYPE, A, AAAA, MX, TXT, RCODE, SOA
from dnslib.server import DNSServer, DNSLogger
import socket, os, time, sys

# 添加model_training目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'model_training'))
try:
    import dga_runtime
    DGA_AVAILABLE = True
except ImportError:
    DGA_AVAILABLE = False
    print("Warning: DGA model not available. Install dependencies: pip install -r model_training/requirements.txt")

#Server configuration for the developing stage
PORT = 5353
ADDRESS = '127.0.0.1'
START_TIME = time.strftime("%m_%d_%H_%M_%S", time.localtime())
LOGNAME = 'DNSlog' + f'{START_TIME}.txt'

# DGA检测配置
ENABLE_DGA_DETECTION = True  # 是否启用DGA检测
DGA_THRESHOLD = 0.7          # DGA检测阈值（0.7表示70%置信度）
DGA_ACTION = "SINKHOLE"      # 拦截动作: "SINKHOLE"(返回0.0.0.0) 或 "REFUSE"(拒绝解析)

# 白名单配置（这些域名不会被DGA检测）
WHITELIST = {
    # 常见可信域名
    "google.com.", "www.google.com.", "youtube.com.", "www.youtube.com.",
    "facebook.com.", "www.facebook.com.", "twitter.com.", "www.twitter.com.",
    "github.com.", "www.github.com.", "stackoverflow.com.", "www.stackoverflow.com.",
    "baidu.com.", "www.baidu.com.", "taobao.com.", "www.taobao.com.",
    "qq.com.", "www.qq.com.", "weibo.com.", "www.weibo.com.",
    "bilibili.com.", "www.bilibili.com.", "zhihu.com.", "www.zhihu.com."
    # 可以在这里添加更多白名单域名
}

# 白名单后缀（以这些后缀结尾的域名也会被信任）
WHITELIST_SUFFIXES = {
    ".local.", ".localhost.", ".test.", ".example.",
    ".cn.", ".edu.cn.", ".gov.cn.",  # 中国教育和政府域名
}

#Keep in track of the requests and replies, and print them out at the console
def mylogf(whattolog:str):
    with open('log\\' + LOGNAME, 'a') as f:
        f.writelines(whattolog + '\n')
    print(whattolog)

class HybridResolver:
    def __init__(self, upstream="8.8.8.8"):
        self.upstream = upstream
        self.records = {
            "local.test.": ("A", "192.168.1.100"),
            "ipv6.test.": ("AAAA", "2001:db8::1"),
            "mail.test.": ("MX", (10, "mail.local.test.")),
            "info.test.": ("TXT", "This is a test record"),
            # format: <site> : (<type>, <address>)      not good enough :(
        }
        #A temporary cache, waiting for an alternative...(TODO: Maybe use the sqlite3 library?)
        self.newrecord = {
            QTYPE.A:{'local.test.':'0.0.0.0'},
            QTYPE.AAAA:{'local.test.':'2001:db8::1'},
            QTYPE.CNAME:{},
            QTYPE.SOA:{},
        }

        #Calculate the processing time and total amount of requests
        self.processing_time = 0.
        self.count = 0
        
        # DGA检测统计
        self.dga_blocked_count = 0
        self.dga_check_count = 0
        self.whitelist_bypass_count = 0

        if 'log' not in os.listdir():
            os.mkdir('log')
        with open('log\\' + LOGNAME, 'w') as f:
            f.write(f'DNSServer start logging at {START_TIME}\n')
            if ENABLE_DGA_DETECTION and DGA_AVAILABLE:
                f.write(f'DGA Detection: ENABLED (threshold={DGA_THRESHOLD}, action={DGA_ACTION})\n')
                f.write(f'Whitelist: {len(WHITELIST)} domains, {len(WHITELIST_SUFFIXES)} suffixes\n')
            else:
                f.write(f'DGA Detection: DISABLED\n')
    
    #The main function of the resolver, which would be called by the DNSServer object.
    def resolve(self, request, handler):
        start = time.time()
        q = request.q
        qname = str(q.qname)
        qtype = q.qtype
        #print(f'Processing {qname}, with type {qtype}')
        
        try:
            # ===== DGA检测 =====
            if ENABLE_DGA_DETECTION and DGA_AVAILABLE:
                # 检查是否在白名单中
                if self._is_whitelisted(qname):
                    self.whitelist_bypass_count += 1
                    mylogf(f'[WHITELIST] {qname} - bypassed DGA check')
                else:
                    # 执行DGA检测
                    is_dga, confidence = self._check_dga(qname)
                    self.dga_check_count += 1
                    
                    if is_dga:
                        self.dga_blocked_count += 1
                        mylogf(f'[DGA BLOCKED] {qname} - confidence: {confidence:.2%}')
                        
                        # 根据配置返回拦截响应
                        if DGA_ACTION == "SINKHOLE":
                            return self._build_sinkhole_reply(request, qname, qtype)
                        '''else:  # REFUSE
                            return self._build_refuse_reply(request)'''
                    else:
                        mylogf(f'[DGA PASS] {qname} - confidence: {confidence:.2%}')
            
            # ===== 正常解析流程 =====
            #Check local records
            if qname in self.newrecord[qtype]:
                rdata = self.newrecord[qtype][qname]
                return self._build_reply(request, qname, qtype, rdata)
            #If the authority server does not find the CNAME record, it will return a SOA record as reply in the Authority Section
            elif qname in self.newrecord[QTYPE.SOA]:
                rname, rdata = self.newrecord[QTYPE.SOA][qname]
                return self._build_reply(request, rname, QTYPE.SOA, rdata)

            '''if qname in self.records:
                rtype, rdata = self.records[qname]
                if self._match_type(qtype, rtype):
                    return self._build_reply(request, qname, qtype, rdata)'''
            
            #Foward to upstream
            reply = self._forward(request)
            self.add_records(reply, qname)
            return reply
        finally:
            self.processing_time += time.time() - start
            self.count += 1
    
    #QTYPE.xxx is a enumarate type, which will be evaluated into integers
    def _match_type(self, qtype, rtype_str):
        type_map = {"A": QTYPE.A, "AAAA": QTYPE.AAAA, "MX": QTYPE.MX, "TXT": QTYPE.TXT}
        return qtype == type_map.get(rtype_str)
    
    #Build replies according to the query type
    def _build_reply(self, request, qname, qtype, rdata):
        reply = request.reply()
        
        if qtype == QTYPE.A:
            reply.add_answer(RR(qname, QTYPE.A, rdata=A(rdata), ttl=60))
        elif qtype == QTYPE.AAAA:
            reply.add_answer(RR(qname, QTYPE.AAAA, rdata=AAAA(rdata), ttl=60))
        elif qtype == QTYPE.MX:
            pref, mx = rdata
            reply.add_answer(RR(qname, QTYPE.MX, rdata=MX(pref, mx), ttl=60))
        elif qtype == QTYPE.TXT:
            reply.add_answer(RR(qname, QTYPE.TXT, rdata=TXT(rdata), ttl=60))
        elif qtype == QTYPE.SOA:
            reply.add_auth(RR(qname, QTYPE.SOA, rdata=rdata, ttl=60)) 
        
        return reply
    
    #Use sockets to perform a query to higher-level DNS servers
    def _forward(self, request):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(3)
        try:
            sock.sendto(request.pack(), (self.upstream, 53))
            data, _ = sock.recvfrom(512)
            return DNSRecord.parse(data)
        except:
            reply = request.reply()
            reply.header.rcode = RCODE.SERVFAIL
            return reply
        finally:
            sock.close()

    #Once a new record appears, add it to the cache
    def add_records(self, reply, qname:str):
        for rr in reply.rr:
            mylogf(f'Adding new record : {rr.rtype} {rr.rname} {rr.rdata}')
            self.newrecord[rr.rtype][qname] = str(rr.rdata)
        if reply.auth:
            for rr in reply.auth:
                mylogf(f'Adding new record : {rr.rtype} {rr.rname} {rr.rdata} from SOA')
                self.newrecord[rr.rtype][qname] = (rr.rname, rr.rdata)
    
    # ===== DGA检测相关方法 =====
    
    def _is_whitelisted(self, qname):
        """检查域名是否在白名单中"""
        # 精确匹配
        if qname in WHITELIST:
            return True
        
        # 后缀匹配
        for suffix in WHITELIST_SUFFIXES:
            if qname.endswith(suffix):
                return True
        
        return False
    
    def _check_dga(self, qname):
        """使用AI模型检测域名是否为DGA恶意域名"""
        try:
            # 移除末尾的点号（DNS格式）
            domain = qname.rstrip('.')
            
            # 调用DGA检测模型
            is_dga, confidence = dga_runtime.predict(
                domain, 
                threshold=DGA_THRESHOLD
            )
            return is_dga, confidence
        except Exception as e:
            mylogf(f'[DGA ERROR] Failed to check {qname}: {e}')
            return False, 0.0  # 出错时默认放行
    
    def _build_sinkhole_reply(self, request, qname, qtype):
        """构建Sinkhole响应（返回0.0.0.0或::）"""
        reply = request.reply()
        
        if qtype == QTYPE.A:
            reply.add_answer(RR(qname, QTYPE.A, rdata=A("0.0.0.0"), ttl=60))
        elif qtype == QTYPE.AAAA:
            reply.add_answer(RR(qname, QTYPE.AAAA, rdata=AAAA("::"), ttl=60))
        else:
            # 其他类型返回空响应
            pass
        
        return reply
    
    '''def _build_refuse_reply(self, request):
        """构建拒绝响应"""
        reply = request.reply()
        reply.header.rcode = RCODE.REFUSED
        return reply
    '''

if __name__ == "__main__":

    #Initiating resolver and the DNSServer object
    resolver = HybridResolver()
    server = DNSServer(resolver, port=PORT, address=ADDRESS, logger=DNSLogger(logf=mylogf))
    print(f"DNS Server running on {ADDRESS}:{PORT}, with starting time {START_TIME}")

    #Start the server until being terminated by the keyboard
    try:      
        server.start()
    except KeyboardInterrupt:
        #The average processing time for a request is about 0.2 sec. 
        #With cache in hand, we can accelerate it to lesser than 0.01 sec!
        #How to manage it is another problem, though...
        print(f'\n{"="*60}')
        print(f'DNS Server Statistics:')
        print(f'{"="*60}')
        print(f'Total requests: {resolver.count}')
        print(f'Total processing time: {resolver.processing_time:.2f}s')
        print(f'Average processing time: {resolver.processing_time/resolver.count:.2f}s')
        
        if ENABLE_DGA_DETECTION and DGA_AVAILABLE:
            print(f'\nDGA Detection Statistics:')
            print(f'  Whitelist bypassed: {resolver.whitelist_bypass_count}')
            print(f'  DGA checks performed: {resolver.dga_check_count}')
            print(f'  Malicious domains blocked: {resolver.dga_blocked_count}')
            if resolver.dga_check_count > 0:
                block_rate = resolver.dga_blocked_count / resolver.dga_check_count * 100
                print(f'  Block rate: {block_rate:.2f}%')
        print(f'{"="*60}')
        #print(f'Final record list: {resolver.newrecord}')
        