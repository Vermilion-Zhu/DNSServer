import sqlite3
import time
import threading
import json

class DNSCache:
    def __init__(self, db_path="dns_cache.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.lock = threading.Lock()
        self._create_table()
    
    def _create_table(self):
        self.conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cache(
        domain TEXT,
        qtype INTEGER,
        rdata TEXT,
        ttl INTEGER,
        expire INTEGER,
        PRIMARY KEY(domain, qtype)
        )
        """
        )
        # 否定缓存表：存储 NXDOMAIN 结果及 SOA 信息（RFC 2308）
        # 使用 (domain, qtype) 联合主键，与正向缓存一致，防止跨类型截断
        # 先删除旧版单主键表（如存在），再重建
        self.conn.execute("DROP TABLE IF EXISTS neg_cache")
        self.conn.execute(
        """
        CREATE TABLE IF NOT EXISTS neg_cache(
        domain TEXT,
        qtype INTEGER,
        soa_rdata TEXT,
        ttl INTEGER,
        expire INTEGER,
        PRIMARY KEY(domain, qtype)
        )
        """
        )
        self.conn.commit()

    def get(self, domain, qtype):
        with self.lock:
            cur = self.conn.execute(
                "SELECT rdata, ttl, expire FROM cache WHERE domain=? AND qtype=?",
                (domain, qtype)
            )
            row = cur.fetchone()
            if not row:
                return None
            rdata_str, ttl, expire = row
            now = int(time.time())
            if expire <= now:
                self.conn.execute("DELETE FROM cache WHERE domain=? AND qtype=?", (domain, qtype))
                self.conn.commit()
                return None
            remaining_ttl = expire - now
        try:
            rdata = json.loads(rdata_str)
        except Exception:
            rdata = rdata_str
        return rdata, remaining_ttl
    
    def set(self, domain, qtype, rdata, ttl):
        now = int(time.time())
        expire = now + ttl
        # allow storing lists/objects by JSON-encoding
        if isinstance(rdata, (list, dict)):
            rdata_to_store = json.dumps(rdata)
        else:
            rdata_to_store = str(rdata)
        with self.lock:
            self.conn.execute(
                "REPLACE INTO cache (domain, qtype, rdata, ttl, expire) VALUES (?, ?, ?, ?, ?)",
                (domain, qtype, rdata_to_store, ttl, expire)
            )
            self.conn.commit()

    def delete(self, domain, qtype):
        with self.lock:
            self.conn.execute(
                "DELETE FROM cache WHERE domain=? AND qtype=?",
                (domain, qtype)
            )
            self.conn.commit()

    # ===== 否定缓存方法（RFC 2308 NXDOMAIN 缓存） =====

    def get_negative(self, domain, qtype):
        """查询否定缓存。返回 (soa_rdata_dict, remaining_ttl) 或 None。
        
        soa_rdata_dict 包含: mname, rname, serial, refresh, retry, expire, minimum
        """
        with self.lock:
            cur = self.conn.execute(
                "SELECT soa_rdata, ttl, expire FROM neg_cache WHERE domain=? AND qtype=?",
                (domain, qtype)
            )
            row = cur.fetchone()
            if not row:
                return None
            soa_rdata_str, ttl, expire = row
            now = int(time.time())
            if expire <= now:
                self.conn.execute("DELETE FROM neg_cache WHERE domain=? AND qtype=?", (domain, qtype))
                self.conn.commit()
                return None
            remaining_ttl = expire - now
        try:
            soa_rdata = json.loads(soa_rdata_str)
        except Exception:
            soa_rdata = soa_rdata_str
        return soa_rdata, remaining_ttl

    def set_negative(self, domain, qtype, soa_rdata, ttl):
        """写入否定缓存。

        Args:
            domain: 域名（带末尾点号）
            qtype: 查询类型（整数，如 QTYPE.A=1）
            soa_rdata: SOA 记录数据 dict，包含 mname, rname, serial, refresh, retry, expire, minimum
            ttl: 否定缓存 TTL（通常取 SOA minimum 字段）
        """
        now = int(time.time())
        expire = now + ttl
        if isinstance(soa_rdata, dict):
            soa_rdata_str = json.dumps(soa_rdata)
        else:
            soa_rdata_str = str(soa_rdata)
        with self.lock:
            self.conn.execute(
                "REPLACE INTO neg_cache (domain, qtype, soa_rdata, ttl, expire) VALUES (?, ?, ?, ?, ?)",
                (domain, qtype, soa_rdata_str, ttl, expire)
            )
            self.conn.commit()

    def delete_negative(self, domain, qtype):
        """删除指定域名和查询类型的否定缓存条目。"""
        with self.lock:
            self.conn.execute("DELETE FROM neg_cache WHERE domain=? AND qtype=?", (domain, qtype))
            self.conn.commit()

    def clear_expired(self):
        now = int(time.time())
        with self.lock:
            self.conn.execute("DELETE FROM cache WHERE expire <= ?", (now,))
            self.conn.execute("DELETE FROM neg_cache WHERE expire <= ?", (now,))
            self.conn.commit()

    def close(self):
        with self.lock:
            try:
                self.conn.close()
            except Exception:
                pass