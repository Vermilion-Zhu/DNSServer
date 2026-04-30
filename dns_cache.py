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
        self.conn.commit()

    def get(self, domain, qtype):
        with self.lock:
            cur = self.conn.execute(
                "SELECT rdata, ttl, expire FROM cache WHERE domain=? AND qtype=?",
                (domain, qtype)
            )
            row = cur.fetchone()
        if row:
            rdata, ttl, expire = row
            try:
                # rdata may be a JSON-encoded list or object
                rdata_parsed = json.loads(rdata)
                rdata = rdata_parsed
            except Exception:
                # keep original string when not JSON
                pass
            now = int(time.time())
            if expire > now:
                remaining_ttl = expire - now
                return rdata, remaining_ttl
            self.delete(domain, qtype)
        return None
    
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

    def clear_expired(self):
        now = int(time.time())
        with self.lock:
            self.conn.execute("DELETE FROM cache WHERE expire <= ?", (now,))
            self.conn.commit()

    def close(self):
        with self.lock:
            try:
                self.conn.close()
            except Exception:
                pass