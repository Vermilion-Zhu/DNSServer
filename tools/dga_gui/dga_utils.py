#!/usr/bin/env python3
"""DGA detection utilities for the DGA GUI.

Wraps model_training.dga_runtime with lazy loading and JSON file parsing.
"""

import json
import os
import sys

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from config import DGA_THRESHOLD, is_whitelisted

_dga_runtime = None
_DGA_AVAILABLE = False


def ensure_dga():
    """Lazily import the DGA runtime. Returns True if available."""
    global _dga_runtime, _DGA_AVAILABLE
    if _dga_runtime is not None:
        return _DGA_AVAILABLE
    try:
        from model_training import dga_runtime as _mod
        _dga_runtime = _mod
        _DGA_AVAILABLE = True
    except Exception as exc:
        _DGA_AVAILABLE = False
        print(f"[WARN] DGA runtime unavailable: {exc}")
    return _DGA_AVAILABLE


def check_dga(domain: str, threshold: float = DGA_THRESHOLD):
    """Check a single domain for DGA. Returns (is_dga, score)."""
    if not ensure_dga():
        return None, None
    try:
        return _dga_runtime.predict(domain, threshold=threshold)
    except Exception as e:
        return None, f"Error: {e}"


def check_dga_many(domains: list, threshold: float = DGA_THRESHOLD):
    """Check multiple domains for DGA. Returns (is_dga_list, scores_list)."""
    if not ensure_dga():
        return None, None
    try:
        return _dga_runtime.predict_many(domains, threshold=threshold)
    except Exception as e:
        return None, f"Error: {e}"


def load_domains_from_json(filepath: str) -> list:
    """Load domain list from a JSON file. Supports multiple formats."""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    domains = []
    if isinstance(data, list):
        for item in data:
            if isinstance(item, str):
                domains.append(item)
            elif isinstance(item, dict) and "domain" in item:
                domains.append(item["domain"])
    elif isinstance(data, dict):
        if "domains" in data:
            for item in data["domains"]:
                if isinstance(item, str):
                    domains.append(item)
                elif isinstance(item, dict) and "domain" in item:
                    domains.append(item["domain"])
        elif "domain" in data:
            domains.append(data["domain"])
    return domains

