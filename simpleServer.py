#!/usr/bin/env python3
#A simple DNS server that supports A, AAAA, CNAME requests
#REMEMBER TO DISABLE .ps1 SCRIPTS AFTER THE EXPERIMENT!

from dns_cache import DNSCache
from dnslib import DNSRecord, RR, QTYPE, A, AAAA, MX, TXT, CNAME, RCODE
from dnslib.server import DNSServer, DNSLogger as DnslibLogger
import socket, os, time, threading, traceback

# 共享配置（从 config.py 导入）
from config import (
    PORT, ADDRESS,
    ENABLE_DGA_DETECTION, DGA_THRESHOLD, DGA_ACTION,
    WHITELIST, WHITELIST_SUFFIXES, is_whitelisted,
)

# 统一日志器
from logger import DNSLogger, FileHandler, ConsoleHandler

logger = DNSLogger("DNSServer")
logger.add_handler(FileHandler("log", "DNSlog"))
logger.add_handler(ConsoleHandler())

# dnslib DNSLogger 桥接函数：将 dnslib 的日志输出转发到统一日志器
def _dnslib_logf(msg: str):
    logger.info("DNSLIB", msg)

try:
    from model_training import dga_runtime
    DGA_AVAILABLE = True
except ImportError:
    DGA_AVAILABLE = False
    logger.warn("SERVER", "DGA model not available. Install dependencies: pip install -r model_training/requirements.txt")

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
        # A temporary cache placeholder (legacy local-record support removed)
        self.cache = DNSCache("dns_cache.db")

        #Calculate the processing time and total amount of requests
        self.processing_time = 0.
        self.count = 0
        
        # DGA检测统计
        self.dga_blocked_count = 0
        self.dga_check_count = 0
        self.whitelist_bypass_count = 0

        logger.info("SERVER", "DNSServer start logging")
        if ENABLE_DGA_DETECTION and DGA_AVAILABLE:
            logger.info("SERVER", f"DGA Detection: ENABLED (threshold={DGA_THRESHOLD}, action={DGA_ACTION})")
            logger.info("SERVER", f"Whitelist: {len(WHITELIST)} domains, {len(WHITELIST_SUFFIXES)} suffixes")
        else:
            logger.info("SERVER", "DGA Detection: DISABLED")

        # start periodic cache cleanup thread
        self._stop_cleaner = threading.Event()
        def _periodic_cleanup():
            while not self._stop_cleaner.wait(60):
                try:
                    self.cache.clear_expired()
                except Exception as e:
                    logger.error("CLEANUP_ERR", f"{e}\n{traceback.format_exc()}")
        t = threading.Thread(target=_periodic_cleanup, daemon=True)
        t.start()
        self._cleaner_thread = t
    
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
                    logger.info("WHITELIST", f"{qname} - bypassed DGA check")
                else:
                    # 执行DGA检测
                    is_dga, confidence = self._check_dga(qname)
                    self.dga_check_count += 1
                    
                    if is_dga:
                        self.dga_blocked_count += 1
                        logger.warn("DGA_BLOCKED", f"{qname} - confidence: {confidence:.2%}")
                        
                        # 根据配置返回拦截响应
                        if DGA_ACTION == "SINKHOLE":
                            return self._build_sinkhole_reply(request, qname, qtype)
                        # (REFUSE behavior removed)
                    else:
                        logger.info("DGA_PASS", f"{qname} - confidence: {confidence:.2%}")
            
            # ===== 正常解析流程 =====
            # (legacy local-record handling removed)
            cached = self.cache.get(qname, qtype)
            if cached:
                rdata, remaining_ttl = cached
                logger.info("CACHE_HIT", f"{qname} -> {rdata} (remaining TTL: {remaining_ttl}s)")
                return self._build_reply(request, qname, qtype, rdata, remaining_ttl)
            # continue to upstream lookup
            # CNAME cache lookup for A/AAAA queries
            if qtype in (QTYPE.A, QTYPE.AAAA):
                cached_cname = self.cache.get(qname, QTYPE.CNAME)
                if cached_cname:
                    cname_target, cname_ttl = cached_cname
                    logger.info("CACHE_HIT", f"[CNAME] {qname} -> {cname_target}")
                    cached_ip = self.cache.get(cname_target, qtype)
                    if cached_ip:
                        ip_data, ip_ttl = cached_ip
                        reply = request.reply()
                        reply.add_answer(RR(qname, QTYPE.CNAME, rdata=CNAME(cname_target), ttl=cname_ttl))
                        rdata_cls = A if qtype == QTYPE.A else AAAA
                        if isinstance(ip_data, list):
                            for rd in ip_data:
                                reply.add_answer(RR(cname_target, qtype, rdata=rdata_cls(rd), ttl=ip_ttl))
                        else:
                            reply.add_answer(RR(cname_target, qtype, rdata=rdata_cls(ip_data), ttl=ip_ttl))
                        logger.info("CNAME_RESOLVED", f"{qname} -> {cname_target} -> {ip_data}")
                        return reply

            #Forward to upstream
            reply = self._forward(request)
            if getattr(reply, 'header', None) and reply.header.rcode == RCODE.NOERROR and not getattr(reply.header, 'tc', False) and getattr(reply, 'rr', None):
                self.add_records(reply, qname)
                # CNAME chain resolution
                reply = self._resolve_cname_chain(reply, request, qname, qtype)
            else:
                logger.warn("UPSTREAM_ERR", f"{qname} - RCODE: {reply.header.rcode if getattr(reply, 'header', None) else 'N/A'}, TC: {getattr(reply, 'tc', 'N/A')}, RR count: {len(getattr(reply, 'rr', []))}")
            return reply
        finally:
            self.processing_time += time.time() - start
            self.count += 1
    
    #QTYPE.xxx is a enumarate type, which will be evaluated into integers
    def _match_type(self, qtype, rtype_str):
        type_map = {"A": QTYPE.A, "AAAA": QTYPE.AAAA, "MX": QTYPE.MX, "TXT": QTYPE.TXT, "CNAME": QTYPE.CNAME}
        return qtype == type_map.get(rtype_str)
    
    # Build replies according to the query type
    def _build_reply(self, request, qname, qtype, rdata, ttl=60):
        reply = request.reply()
        if qtype == QTYPE.A:
            if isinstance(rdata, list):
                for rd in rdata:
                    reply.add_answer(RR(qname, QTYPE.A, rdata=A(rd), ttl=ttl))
            else:
                reply.add_answer(RR(qname, QTYPE.A, rdata=A(rdata), ttl=ttl))
        elif qtype == QTYPE.AAAA:
            if isinstance(rdata, list):
                for rd in rdata:
                    reply.add_answer(RR(qname, QTYPE.AAAA, rdata=AAAA(rd), ttl=ttl))
            else:
                reply.add_answer(RR(qname, QTYPE.AAAA, rdata=AAAA(rdata), ttl=ttl))
        elif qtype == QTYPE.CNAME:
            reply.add_answer(RR(qname, QTYPE.CNAME, rdata=CNAME(rdata), ttl=ttl))
        elif qtype == QTYPE.MX:
            pref, mx = rdata if isinstance(rdata, tuple) else (10, rdata)
            reply.add_answer(RR(qname, QTYPE.MX, rdata=MX(pref, mx), ttl=ttl))
        elif qtype == QTYPE.TXT:
            reply.add_answer(RR(qname, QTYPE.TXT, rdata=TXT(rdata), ttl=ttl))
        return reply
    
    #Use sockets to perform a query to higher-level DNS servers
    def _forward(self, request):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(3)
        try:
            sock.sendto(request.pack(), (self.upstream, 53))
            data, _ = sock.recvfrom(4096)
            return DNSRecord.parse(data)
        except Exception as e:
            logger.error("FORWARD_ERR", f"{e}\n{traceback.format_exc()}")
            reply = request.reply()
            reply.header.rcode = RCODE.SERVFAIL
            return reply
        finally:
            sock.close()

    # Once a new record appears, add it to the cache
    def add_records(self, reply, qname:str):
        # collect A and AAAA records and cache all values per type
        a_list = []
        a_ttl = None
        aaaa_list = []
        aaaa_ttl = None
        for rr in reply.rr:
            if rr.rtype == QTYPE.A:
                a_list.append(str(rr.rdata))
                a_ttl = rr.ttl if a_ttl is None else min(a_ttl, rr.ttl)
            elif rr.rtype == QTYPE.AAAA:
                aaaa_list.append(str(rr.rdata))
                aaaa_ttl = rr.ttl if aaaa_ttl is None else min(aaaa_ttl, rr.ttl)

        if a_list:
            self.cache.set(qname, QTYPE.A, a_list, a_ttl or 60)
            logger.info("CACHE_SET", f"{qname} -> {a_list} (TTL={a_ttl or 60}s)")
        if aaaa_list:
            self.cache.set(qname, QTYPE.AAAA, aaaa_list, aaaa_ttl or 60)
            logger.info("CACHE_SET", f"{qname} -> {aaaa_list} (TTL={aaaa_ttl or 60}s)")

        # cache CNAME if present and matches qname
        cname_target = None
        cname_ttl = None
        for rr in reply.rr:
            if rr.rtype == QTYPE.CNAME and str(rr.rname) == qname:
                cname_target = str(rr.rdata)
                cname_ttl = rr.ttl
                break
        if cname_target:
            if not cname_target.endswith('.'):
                cname_target += '.'
            self.cache.set(qname, QTYPE.CNAME, cname_target, cname_ttl or 60)
            logger.info("CACHE_SET_CNAME", f"{qname} -> {cname_target} (TTL={cname_ttl or 60}s)")
            for rr in reply.rr:
                if rr.rtype == QTYPE.A and str(rr.rname) == cname_target:
                    self.cache.set(cname_target, QTYPE.A, [str(rr.rdata)], rr.ttl)
                    logger.info("CACHE_SET", f"{cname_target} -> {rr.rdata} (TTL={rr.ttl}s)")
                elif rr.rtype == QTYPE.AAAA and str(rr.rname) == cname_target:
                    self.cache.set(cname_target, QTYPE.AAAA, [str(rr.rdata)], rr.ttl)
                    logger.info("CACHE_SET", f"{cname_target} -> {rr.rdata} (TTL={rr.ttl}s)")

    def _resolve_cname_chain(self, reply, request, qname, qtype, depth=0):
        """CNAME chain resolution for A/AAAA queries."""
        if depth >= 5:
            logger.warn("CNAME_CHAIN", f"Max depth reached for {qname}")
            return reply
        if qtype not in (QTYPE.A, QTYPE.AAAA):
            return reply
        has_target = any(rr.rtype == qtype and str(rr.rname) == qname for rr in reply.rr)
        if has_target:
            return reply
        cname_target = None
        for rr in reply.rr:
            if rr.rtype == QTYPE.CNAME and str(rr.rname) == qname:
                cname_target = str(rr.rdata)
                break
        if not cname_target:
            return reply
        logger.info("CNAME_CHAIN", f"{qname} -> {cname_target}, resolving (depth={depth})")
        cached = self.cache.get(cname_target, qtype)
        if cached:
            rdata, remaining_ttl = cached
            logger.info("CACHE_HIT", f"[CNAME_CHAIN] {cname_target} -> {rdata}")
            rdata_list = rdata if isinstance(rdata, list) else [rdata]
            rdata_cls = A if qtype == QTYPE.A else AAAA
            for rd in rdata_list:
                reply.add_answer(RR(cname_target, qtype, rdata=rdata_cls(rd), ttl=remaining_ttl))
            return reply
        try:
            q = DNSRecord.question(cname_target, qtype=qtype)
            upstream_reply = self._forward(q)
            if getattr(upstream_reply, "header", None) and upstream_reply.header.rcode == RCODE.NOERROR and getattr(upstream_reply, "rr", None):
                self.add_records(upstream_reply, cname_target)
                for rr in upstream_reply.rr:
                    reply.add_answer(rr)
                reply = self._resolve_cname_chain(reply, request, cname_target, qtype, depth + 1)
            else:
                logger.warn("CNAME_CHAIN", f"No result for {cname_target}")
        except Exception as e:
            logger.error("CNAME_CHAIN", str(e))
        return reply

    # ===== DGA检测相关方法 =====
    
    def _is_whitelisted(self, qname):
        """检查域名是否在白名单中（委托给 config.is_whitelisted）"""
        return is_whitelisted(qname)
    
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
            logger.error("DGA", f"Failed to check {qname}: {e}")
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
    
    # (refuse reply helper removed; using sinkhole or normal replies)

if __name__ == "__main__":

    #Initiating resolver and the DNSServer object
    resolver = HybridResolver()
    server = DNSServer(resolver, port=PORT, address=ADDRESS, logger=DnslibLogger(logf=_dnslib_logf))
    logger.info("SERVER", f"DNS Server running on {ADDRESS}:{PORT}")

    #Start the server until being terminated by the keyboard
    try:      
        server.start()
    except KeyboardInterrupt:
        # stop background cleaner and close cache
        try:
            resolver._stop_cleaner.set()
        except Exception:
            pass
        try:
            resolver.cache.close()
        except Exception:
            pass
        #The average processing time for a request is about 0.2 sec. 
        #With cache in hand, we can accelerate it to lesser than 0.01 sec!
        #How to manage it is another problem, though...
        print(f'\n{"="*60}')
        print(f'DNS Server Statistics:')
        print(f'{"="*60}')
        print(f'Total requests: {resolver.count}')
        print(f'Total processing time: {resolver.processing_time:.2f}s')
        if resolver.count > 0:
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
