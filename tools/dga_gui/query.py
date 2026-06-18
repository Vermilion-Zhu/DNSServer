#!/usr/bin/env python3
"""DNS query & cache utilities for the DGA GUI.

Thin wrapper around the project's dns_cache.DNSCache and dnspython,
implementing the same cache-first strategy as simpleServer.resolve().
"""

import os
import sys

# Project root
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from config import PORT, ADDRESS as DNS_SERVER_ADDRESS

_QTYPE_MAP_INT = {"A": 1, "AAAA": 28, "MX": 15, "TXT": 16, "CNAME": 5, "NS": 2, "SOA": 6, "PTR": 12}


# Lazy singletons
_dns_cache = None
_CACHE_AVAILABLE = False


def _ensure_cache():
    global _dns_cache, _CACHE_AVAILABLE
    if _dns_cache is not None:
        return _CACHE_AVAILABLE
    try:
        from dns_cache import DNSCache
        _dns_cache = DNSCache(os.path.join(_PROJECT_ROOT, "dns_cache.db"))
        _dns_cache.clear_expired()
        _CACHE_AVAILABLE = True
    except Exception as exc:
        _CACHE_AVAILABLE = False
        print(f"[WARN] DNSCache unavailable: {exc}")
    return _CACHE_AVAILABLE


def cached_lookup(domain: str, qtype: str):
    """Return (rdata, remaining_ttl) from cache, or None."""
    if not _ensure_cache():
        return None
    qname = domain if domain.endswith(".") else domain + "."
    try:
        import dns.rdatatype
        return _dns_cache.get(qname, dns.rdatatype.from_text(qtype.upper()))
    except Exception:
        return None


def dns_query(qname: str, qtype: str = "A", server: str = "8.8.8.8",
              port: int = 53, use_cache: bool = True):
    """DNS query with cache-first strategy.

    Args:
        qname: Domain name to query.
        qtype: Record type (A, AAAA, MX, etc.).
        server: DNS server address.
        port: DNS server port (default 53; use 5353 for local server).
        use_cache: Whether to check/write local cache.

    Returns (resp, text, cache_hit):
        resp      - dnspython Message or None
        text      - formatted result string
        cache_hit - bool
    """
    # 1. Negative cache lookup (RFC 2308 NXDOMAIN)
    if use_cache and _ensure_cache():
        qtype_int = _QTYPE_MAP_INT.get(qtype, 1)
        qname_dot = qname if qname.endswith(".") else qname + "."
        neg = _dns_cache.get_negative(qname_dot, qtype_int)
        if neg is not None:
            soa_rdata, remaining_ttl = neg
            lines = [f"[NEG CACHE HIT] {qname} {qtype}  NXDOMAIN",
                     f"  否定缓存 TTL: {remaining_ttl}s",
                     f"  返回 NXDOMAIN（含 SOA 授权信息）"]
            return None, "\n".join(lines), True

    # 2. Cache lookup
    if use_cache:
        cached = cached_lookup(qname, qtype)
        if cached is not None:
            rdata, remaining_ttl = cached
            lines = [f"[CACHE HIT] {qname} {qtype}", f"  剩余 TTL: {remaining_ttl}s"]
            if isinstance(rdata, list):
                lines.append(f"  {qname}  {remaining_ttl}  IN  {qtype}  {', '.join(rdata)}")
            else:
                lines.append(f"  {qname}  {remaining_ttl}  IN  {qtype}  {rdata}")
            return None, "\n".join(lines), True

    # 2. Upstream query (dnspython)
    import dns.message, dns.query, dns.rdatatype, dns.rcode
    q = dns.message.make_query(qname, qtype)
    try:
        resp = dns.query.udp(q, server, port=port, timeout=3)
    except Exception:
        try:
            resp = dns.query.tcp(q, server, port=port, timeout=5)
        except Exception as e:
            return None, f"Query failed: {e}", False

    # Format response
    lines = [f"Status: {dns.rcode.to_text(resp.rcode())}  |  ID: {resp.id}", ""]
    for q in resp.question:
        lines.append(f"Question: {q.name.to_text()}  IN  {dns.rdatatype.to_text(q.rdtype)}")
    for title, section in [("Answer", resp.answer), ("Authority", resp.authority), ("Additional", resp.additional)]:
        if not section:
            continue
        lines.append(f"\n{title}:")
        for rrset in section:
            name = rrset.name.to_text()
            ttl = getattr(rrset, "ttl", "")
            rtype = dns.rdatatype.to_text(rrset.rdtype)
            rdatas = [r.to_text() for r in rrset]
            lines.append(f"  {name}  {ttl}  IN  {rtype}  {', '.join(rdatas)}")

    # 3. Cache records or negative cache
    if use_cache and _ensure_cache():
        _cache_records(resp, qname, qtype)

    return resp, "\n".join(lines), False


def _cache_records(resp, qname: str, qtype: str = "A"):
    """Cache A/AAAA/CNAME from a dnspython response, or NXDOMAIN negative cache.

    Uses rr.rdtype (integer: 1=A, 28=AAAA, 5=CNAME, 6=SOA) — NOT dnslib's QTYPE.
    Mirrors simpleServer.add_records() logic + negative cache support.
    """
    import dns.rcode
    qtype_int = _QTYPE_MAP_INT.get(qtype, 1)
    try:
        qname_dot = qname if qname.endswith(".") else qname + "."

        # Handle NXDOMAIN — cache negative result (RFC 2308)
        if resp.rcode() == dns.rcode.NXDOMAIN:
            neg_ttl = 300
            # Try to extract SOA minimum from authority section
            for rr in resp.authority:
                if rr.rdtype == 6:  # SOA
                    for r in rr:
                        soa_text = r.to_text()
                        soa_parts = soa_text.split()
                        if len(soa_parts) >= 7:
                            try:
                                neg_ttl = max(int(soa_parts[6]), 300)
                            except ValueError:
                                pass
                        break
                    break
            _dns_cache.set_negative(qname_dot, qtype_int, None, neg_ttl)
            return

        a_list, a_ttl = [], None
        aaaa_list, aaaa_ttl = [], None
        for rr in resp.answer:
            # dnspython uses rr.rdtype (int), NOT rr.rtype (dnslib)
            if rr.rdtype == 1:  # A
                for r in rr:
                    a_list.append(r.to_text())
                a_ttl = rr.ttl if a_ttl is None else min(a_ttl, rr.ttl)
            elif rr.rdtype == 28:  # AAAA
                for r in rr:
                    aaaa_list.append(r.to_text())
                aaaa_ttl = rr.ttl if aaaa_ttl is None else min(aaaa_ttl, rr.ttl)

        if a_list:
            _dns_cache.set(qname_dot, 1, a_list, a_ttl or 60)
        if aaaa_list:
            _dns_cache.set(qname_dot, 28, aaaa_list, aaaa_ttl or 60)
        if not (a_list or aaaa_list):
            for rr in resp.answer:
                if rr.rdtype == 5:  # CNAME
                    for r in rr:
                        _dns_cache.set(qname_dot, 5, r.to_text(), rr.ttl)
                    break
    except Exception:
        pass


def clear_expired_cache():
    """清理过期缓存记录。暴露给 GUI 调用。"""
    if not _ensure_cache():
        return 0
    try:
        _dns_cache.clear_expired()
        return -1  # DNSCache 无计数接口，返回 -1 表示已执行，具体数量未知
    except Exception:
        return 0


def cache_stats():
    """返回缓存统计信息。暴露给 GUI 调用。"""
    if not _ensure_cache():
        return None
    try:
        import time
        now = int(time.time())
        conn = _dns_cache.conn
        total_pos = conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
        active_pos = conn.execute("SELECT COUNT(*) FROM cache WHERE expire > ?", (now,)).fetchone()[0]
        total_neg = conn.execute("SELECT COUNT(*) FROM neg_cache").fetchone()[0]
        active_neg = conn.execute("SELECT COUNT(*) FROM neg_cache WHERE expire > ?", (now,)).fetchone()[0]
        rows = conn.execute("SELECT domain, qtype, rdata, expire FROM cache ORDER BY expire DESC LIMIT 20").fetchall()
        return {
            "total": total_pos + total_neg,
            "active": active_pos + active_neg,
            "expired": (total_pos - active_pos) + (total_neg - active_neg),
            "pos_total": total_pos, "pos_active": active_pos,
            "neg_total": total_neg, "neg_active": active_neg,
            "now": now, "rows": rows,
        }
    except Exception:
        return None


def close_cache():
    if _dns_cache is not None:
        try:
            _dns_cache.close()
        except Exception:
            pass
