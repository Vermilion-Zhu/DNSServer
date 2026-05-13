#!/usr/bin/env python3
"""Unified logging module for DNSServer components.

Provides a centralized DNSLogger with pluggable handlers so that
simpleServer.py, the DGA GUI, and other tools share the same
timestamp format, tag system, and log levels.

Usage (simpleServer.py):
    from logger import DNSLogger, FileHandler, ConsoleHandler

    logger = DNSLogger("DNSServer")
    logger.add_handler(FileHandler("log", "DNSlog"))
    logger.add_handler(ConsoleHandler())

    logger.info("CACHE_HIT", f"{qname} -> {rdata} (remaining TTL: {ttl}s)")
    logger.warn("UPSTREAM_ERR", f"{qname} - RCODE: {rcode}")
    logger.error("FORWARD_ERR", str(e))

Usage (GUI):
    from logger import DNSLogger, WidgetHandler

    logger = DNSLogger("DGA_GUI")
    logger.add_handler(WidgetHandler(self.log_txt, self.root))

    logger.info("QUERY", f"查询 {domain} {qtype}")
"""

import os
import threading
from datetime import datetime


# ---------------------------------------------------------------------------
#  Tag → Chinese label mapping (for GUI display)
# ---------------------------------------------------------------------------

TAG_LABELS = {
    "CACHE_HIT":    "缓存命中",
    "CACHE_SET":    "缓存写入",
    "CACHE_SET_CNAME": "缓存写入CNAME",
    "DGA_BLOCKED":  "DGA拦截",
    "DGA_PASS":     "DGA通过",
    "WHITELIST":    "白名单",
    "UPSTREAM_ERR": "上游错误",
    "FORWARD_ERR":  "转发错误",
    "CNAME_CHAIN":  "CNAME链",
    "CNAME_RESOLVED": "CNAME解析",
    "CLEANUP_ERR":  "清理错误",
    "SERVER":       "服务器",
    "QUERY":        "查询",
    "BATCH":        "批量检测",
    "CACHE":        "缓存",
    "DGA":          "DGA检测",
    "DNS":          "DNS",
    "EXPORT":       "导出",
    "GIT":          "Git",
}


# ---------------------------------------------------------------------------
#  Handlers
# ---------------------------------------------------------------------------

class FileHandler:
    """Write log lines to a timestamped file.

    A new file is created each time a FileHandler is instantiated
    (i.e. each server start).
    """

    def __init__(self, log_dir="log", prefix="DNSlog"):
        os.makedirs(log_dir, exist_ok=True)
        ts = datetime.now().strftime("%m_%d_%H_%M_%S")
        self.path = os.path.join(log_dir, f"{prefix}_{ts}.txt")
        self._lock = threading.Lock()

    def __call__(self, line: str):
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")


class ConsoleHandler:
    """Print log lines to the console (with explicit flush)."""

    def __call__(self, line: str):
        print(line, flush=True)


class WidgetHandler:
    """Append log lines to a tkinter ScrolledText widget.

    Thread-safe: uses root.after(0, ...) to schedule inserts on the
    main thread, avoiding tkinter threading issues.
    """

    def __init__(self, widget, root):
        self.widget = widget
        self.root = root

    def __call__(self, line: str):
        def _insert():
            try:
                self.widget.configure(state="normal")
                self.widget.insert("end", line + "\n")
                self.widget.see("end")
                self.widget.configure(state="disabled")
            except Exception:
                pass
        try:
            self.root.after(0, _insert)
        except Exception:
            pass


# ---------------------------------------------------------------------------
#  DNSLogger
# ---------------------------------------------------------------------------

class DNSLogger:
    """Centralized logger with pluggable handlers.

    Each log line has the format:
        [YYYY-MM-DD HH:MM:SS] [LEVEL] [TAG] message

    Levels: INFO, WARN, ERROR
    Tags:   see TAG_LABELS for the canonical set
    """

    def __init__(self, name="DNSServer"):
        self.name = name
        self._handlers: list = []
        self._lock = threading.Lock()

    # -- handler management --------------------------------------------------

    def add_handler(self, handler):
        """Register a handler callable. It will receive formatted log lines."""
        with self._lock:
            self._handlers.append(handler)

    def remove_handler(self, handler):
        """Unregister a previously added handler."""
        with self._lock:
            self._handlers = [h for h in self._handlers if h is not handler]

    # -- core emit -----------------------------------------------------------

    def _emit(self, level: str, tag: str, msg: str):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] [{level}] [{tag}] {msg}"
        with self._lock:
            for h in list(self._handlers):
                try:
                    h(line)
                except Exception:
                    pass

    # -- public API ----------------------------------------------------------

    def info(self, tag: str, msg: str):
        """Log an informational message."""
        self._emit("INFO", tag, msg)

    def warn(self, tag: str, msg: str):
        """Log a warning message."""
        self._emit("WARN", tag, msg)

    def error(self, tag: str, msg: str):
        """Log an error message."""
        self._emit("ERROR", tag, msg)
