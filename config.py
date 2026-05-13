#!/usr/bin/env python3
"""Shared configuration for DNSServer components.

This module centralizes configuration constants used by simpleServer.py,
the DGA GUI, and other tools — avoiding duplication across the codebase.
"""

# ---------------------------------------------------------------------------
# DNS Server configuration
# ---------------------------------------------------------------------------
PORT = 5353
ADDRESS = "127.0.0.1"
UPSTREAM_DNS = "8.8.8.8"

# ---------------------------------------------------------------------------
# DGA detection configuration
# ---------------------------------------------------------------------------
ENABLE_DGA_DETECTION = True   # Whether DGA detection is active
DGA_THRESHOLD = 0.7           # Confidence threshold (0.7 = 70%)
DGA_ACTION = "SINKHOLE"       # Action on DGA match: "SINKHOLE" (return 0.0.0.0) or "REFUSE"

# ---------------------------------------------------------------------------
# Whitelist — domains that bypass DGA checks
# ---------------------------------------------------------------------------
WHITELIST = {
    # Common trusted domains
    "google.com.", "www.google.com.", "youtube.com.", "www.youtube.com.",
    "facebook.com.", "www.facebook.com.", "twitter.com.", "www.twitter.com.",
    "github.com.", "www.github.com.", "stackoverflow.com.", "www.stackoverflow.com.",
    "baidu.com.", "www.baidu.com.", "taobao.com.", "www.taobao.com.",
    "qq.com.", "www.qq.com.", "weibo.com.", "www.weibo.com.",
    "bilibili.com.", "www.bilibili.com.", "zhihu.com.", "www.zhihu.com.",
    # Add more trusted domains here
}

# Whitelist suffixes — domains ending with these are also trusted
WHITELIST_SUFFIXES = {
    ".local.", ".localhost.", ".test.", ".example.",
    ".cn.", ".edu.cn.", ".gov.cn.",
}


def is_whitelisted(qname: str) -> bool:
    """Check whether *qname* (trailing-dot form) is in the whitelist.

    Mirrors the logic in simpleServer.HybridResolver._is_whitelisted().
    """
    if qname in WHITELIST:
        return True
    for suffix in WHITELIST_SUFFIXES:
        if qname.endswith(suffix):
            return True
    return False
