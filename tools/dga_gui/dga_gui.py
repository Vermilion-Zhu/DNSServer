#!/usr/bin/env python3
"""DGA Detector & DNS Query GUI — main entry point.

Usage:
    python tools/dga_gui/dga_gui.py
    python -m tools.dga_gui.dga_gui
"""

import csv
import json
import os
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

import dns.rdatatype

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# Import from sibling modules (supports both direct run and module run)
from config import DGA_THRESHOLD, is_whitelisted, PORT, ADDRESS as DNS_SERVER_ADDRESS, UPSTREAM_DNS
try:
    from .query import dns_query, _ensure_cache, _dns_cache, close_cache
    from .dga_utils import check_dga, check_dga_many, ensure_dga, load_domains_from_json
except ImportError:
    from query import dns_query, _ensure_cache, _dns_cache, close_cache
    from dga_utils import check_dga, check_dga_many, ensure_dga, load_domains_from_json

# 统一日志器
from logger import DNSLogger, WidgetHandler

# GUI 专用日志器实例（WidgetHandler 在 __init__ 中注册）
logger = DNSLogger("DGA_GUI")

# 本地 DNS 服务器的端口（从 config.PORT 获取）
DNS_SERVER_PORT = PORT


# ===================================================================
#  GUI Application
# ===================================================================

class DGAGuiApp:
    CLR_BG = "#f5f5f5"
    CLR_SAFE = "#4caf50"
    CLR_WARN = "#ff9800"
    CLR_DANGER = "#f44336"

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("DGA Detector & DNS Query Tool")
        self.root.geometry("980x820")
        self.root.minsize(800, 600)
        self.root.configure(bg=self.CLR_BG)

        self._batch_results = []
        self._dns_server_process = None
        self._dns_server_running = False
        self._stdout_reader_thread = None

        # 任务状态管理
        self._task_running = False
        self._cancel_event = threading.Event()

        self._build_styles()
        self._build_input_frame()
        self._build_buttons()
        
        # Use PanedWindow for resizable layout
        self.paned = ttk.PanedWindow(self.root, orient=tk.VERTICAL)
        self.paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)
        
        dns_frame = self._build_dns_result_frame()
        self.paned.add(dns_frame, weight=1)
        
        dga_frame = self._build_dga_result_frame()
        self.paned.add(dga_frame, weight=3)
        
        log_frame = self._build_log_frame()
        self.paned.add(log_frame, weight=2)

        # 注册 WidgetHandler 到统一日志器
        logger.add_handler(WidgetHandler(self.log_txt, self.root))

        logger.info("SERVER", "Application started.")
        logger.info("DGA", f"model: {'✓' if ensure_dga() else '✗'}")
        logger.info("CACHE", f"DNS 缓存: {'✓' if _ensure_cache() else '✗'}")

        # 自动启动本地 DNS 服务器
        self.root.after(100, self._start_server)

    # ── Styles ─────────────────────────────────────────────────────
    def _build_styles(self):
        s = ttk.Style(); s.theme_use("clam")
        s.configure("S.TLabelframe.Label", font=("Microsoft YaHei UI", 10, "bold"))
        s.configure("Safe.TLabel", foreground=self.CLR_SAFE, font=("Microsoft YaHei UI", 10, "bold"))
        s.configure("Danger.TLabel", foreground=self.CLR_DANGER, font=("Microsoft YaHei UI", 10, "bold"))

    # ── Input ──────────────────────────────────────────────────────
    def _build_input_frame(self):
        fr = ttk.LabelFrame(self.root, text=" 输入配置 ", style="S.TLabelframe", padding=10)
        fr.pack(fill=tk.X, padx=10, pady=(10, 4))

        # Mode
        self.mode_var = tk.StringVar(value="single")
        r0 = ttk.Frame(fr); r0.pack(fill=tk.X, pady=(0, 6))
        ttk.Radiobutton(r0, text="单个域名", variable=self.mode_var, value="single",
                        command=self._toggle_mode).pack(side=tk.LEFT, padx=(0, 20))
        ttk.Radiobutton(r0, text="JSON 文件批量", variable=self.mode_var, value="batch",
                        command=self._toggle_mode).pack(side=tk.LEFT)

        # Single
        self.single_fr = ttk.Frame(fr); self.single_fr.pack(fill=tk.X, pady=2)
        ttk.Label(self.single_fr, text="域名:").pack(side=tk.LEFT)
        self.domain_var = tk.StringVar()
        ttk.Entry(self.single_fr, textvariable=self.domain_var, width=35).pack(side=tk.LEFT, padx=4)
        ttk.Label(self.single_fr, text="记录类型:").pack(side=tk.LEFT)
        self.qtype_var = tk.StringVar(value="A")
        ttk.Combobox(self.single_fr, textvariable=self.qtype_var,
                     values=["A", "AAAA", "CNAME"], width=8,
                     state="readonly").pack(side=tk.LEFT, padx=4)

        # Options
        r2 = ttk.Frame(fr); r2.pack(fill=tk.X, pady=4)
        ttk.Label(r2, text="DGA 阈值:").pack(side=tk.LEFT)
        self.threshold_var = tk.DoubleVar(value=DGA_THRESHOLD)
        ttk.Scale(r2, from_=0.0, to=1.0, variable=self.threshold_var,
                  orient=tk.HORIZONTAL, length=180, command=self._on_thresh).pack(side=tk.LEFT, padx=4)
        self.thresh_lbl = ttk.Label(r2, text=f"{DGA_THRESHOLD:.2f}", width=5)
        self.thresh_lbl.pack(side=tk.LEFT, padx=(0, 16))
        self.use_cache_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(r2, text="使用 DNS 缓存", variable=self.use_cache_var).pack(side=tk.LEFT, padx=(0, 12))
        self.use_wl_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(r2, text="白名单跳过 DGA", variable=self.use_wl_var).pack(side=tk.LEFT)

        # Batch
        self.batch_fr = ttk.Frame(fr)
        ttk.Label(self.batch_fr, text="JSON 文件:").pack(side=tk.LEFT)
        self.filepath_var = tk.StringVar()
        ttk.Entry(self.batch_fr, textvariable=self.filepath_var, width=50).pack(side=tk.LEFT, padx=4)
        ttk.Button(self.batch_fr, text="浏览...", command=self._browse).pack(side=tk.LEFT, padx=4)

    def _toggle_mode(self, *_):
        if self.mode_var.get() == "single":
            self.batch_fr.pack_forget(); self.single_fr.pack(fill=tk.X, pady=2)
        else:
            self.single_fr.pack_forget(); self.batch_fr.pack(fill=tk.X, pady=2)

    def _on_thresh(self, *_):
        self.thresh_lbl.config(text=f"{self.threshold_var.get():.2f}")

    def _browse(self):
        p = filedialog.askopenfilename(title="选择 JSON 文件",
                                       filetypes=[("JSON", "*.json"), ("All", "*.*")])
        if p: self.filepath_var.set(p)

    # ── Buttons ────────────────────────────────────────────────────
    def _build_buttons(self):
        f1 = ttk.Frame(self.root); f1.pack(fill=tk.X, padx=10, pady=(4, 2))
        self.btn_query = ttk.Button(f1, text="🔍 查询&检测", command=self._run_query_detect)
        self.btn_query.pack(side=tk.LEFT, padx=4)
        self.btn_dga = ttk.Button(f1, text="📊 仅DGA检测", command=self._run_dga_only)
        self.btn_dga.pack(side=tk.LEFT, padx=4)
        ttk.Button(f1, text="🗑️ 清空", command=self._clear).pack(side=tk.LEFT, padx=4)
        ttk.Button(f1, text="💾 导出", command=self._export).pack(side=tk.LEFT, padx=4)
        self.btn_cancel = ttk.Button(f1, text="⏹ 取消", command=self._cancel_task, state=tk.DISABLED)
        self.btn_cancel.pack(side=tk.LEFT, padx=4)
        ttk.Separator(f1, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
        ttk.Button(f1, text="📋 仓库状态", command=self._git_status).pack(side=tk.LEFT, padx=4)

        # 服务器控制行：上游DNS + 重启 + 状态
        f2 = ttk.Frame(self.root); f2.pack(fill=tk.X, padx=10, pady=(2, 4))
        ttk.Label(f2, text="上游 DNS:", font=("Microsoft YaHei UI", 9, "bold")).pack(side=tk.LEFT)
        self.upstream_var = tk.StringVar(value=UPSTREAM_DNS)
        ttk.Entry(f2, textvariable=self.upstream_var, width=14).pack(side=tk.LEFT, padx=4)
        self.btn_restart = ttk.Button(f2, text="🔄 重启服务器", command=self._restart_server)
        self.btn_restart.pack(side=tk.LEFT, padx=4)
        self.srv_lbl = ttk.Label(f2, text="● 启动中...", foreground=self.CLR_WARN)
        self.srv_lbl.pack(side=tk.LEFT, padx=8)
        ttk.Separator(f2, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
        ttk.Label(f2, text="缓存:", font=("Microsoft YaHei UI", 9, "bold")).pack(side=tk.LEFT)
        ttk.Button(f2, text="📦 统计", command=self._cache_stats).pack(side=tk.LEFT, padx=4)
        ttk.Button(f2, text="🧹 清理过期", command=self._cache_clear).pack(side=tk.LEFT, padx=4)

        # 进度条
        pf = ttk.Frame(self.root); pf.pack(fill=tk.X, padx=10, pady=(0, 2))
        self.progress_bar = ttk.Progressbar(pf, mode="determinate", length=300)
        self.progress_bar.pack(side=tk.LEFT, padx=(0, 8))
        self.progress_lbl = ttk.Label(pf, text="", font=("Microsoft YaHei UI", 9))
        self.progress_lbl.pack(side=tk.LEFT)

    # ── Task state management ──────────────────────────────────────
    def _set_busy(self, total: int = 0):
        """Mark a task as running; disable action buttons, enable cancel."""
        self._task_running = True
        self._cancel_event.clear()
        self.btn_query.config(state=tk.DISABLED)
        self.btn_dga.config(state=tk.DISABLED)
        self.btn_cancel.config(state=tk.NORMAL)
        if total > 0:
            self.progress_bar.config(mode="determinate", maximum=total, value=0)
            self.progress_lbl.config(text=f"0/{total}")
        else:
            self.progress_bar.config(mode="indeterminate")
            self.progress_bar.start(15)
            self.progress_lbl.config(text="处理中...")

    def _set_idle(self):
        """Mark task as finished; re-enable action buttons, reset progress."""
        self._task_running = False
        self._cancel_event.clear()
        self.btn_query.config(state=tk.NORMAL)
        self.btn_dga.config(state=tk.NORMAL)
        self.btn_cancel.config(state=tk.DISABLED)
        self.progress_bar.stop()
        self.progress_bar.config(mode="determinate", value=0, maximum=1)
        self.progress_lbl.config(text="")

    def _cancel_task(self):
        """Request cancellation of the running task."""
        if not self._task_running: return
        self._cancel_event.set()
        self.btn_cancel.config(state=tk.DISABLED)
        self.progress_lbl.config(text="正在取消...")
        logger.info("BATCH", "用户请求取消任务")

    def _update_progress(self, current: int, total: int):
        """Update progress bar (called from main thread via root.after)."""
        self.progress_bar.config(value=current, maximum=total)
        self.progress_lbl.config(text=f"{current}/{total}")

    # ── Result areas ───────────────────────────────────────────────
    def _build_dns_result_frame(self):
        fr = ttk.LabelFrame(self.root, text=" DNS 查询结果 ", style="S.TLabelframe", padding=6)
        # Cache status indicator
        self.cache_status_var = tk.StringVar(value="")
        self.cache_status_lbl = ttk.Label(fr, textvariable=self.cache_status_var, font=("Microsoft YaHei UI", 9))
        self.cache_status_lbl.pack(anchor=tk.W, pady=(0, 2))
        self.dns_txt = scrolledtext.ScrolledText(fr, height=7, wrap=tk.WORD,
                                                  font=("Consolas", 9), state=tk.DISABLED, bg="#fafafa")
        self.dns_txt.pack(fill=tk.BOTH, expand=True)
        return fr

    def _build_dga_result_frame(self):
        fr = ttk.LabelFrame(self.root, text=" DGA 检测结果 ", style="S.TLabelframe", padding=6)

        self.dga_detail = ttk.Frame(fr); self.dga_detail.pack(fill=tk.X, pady=(0, 4))
        self.lbl_domain = ttk.Label(self.dga_detail, text="域名: —", font=("Microsoft YaHei UI", 10))
        self.lbl_domain.pack(anchor=tk.W)
        self.lbl_score = ttk.Label(self.dga_detail, text="DGA 分数: —", font=("Microsoft YaHei UI", 11, "bold"))
        self.lbl_score.pack(anchor=tk.W, pady=2)
        self.lbl_verdict = ttk.Label(self.dga_detail, text="判定: —", font=("Microsoft YaHei UI", 11, "bold"))
        self.lbl_verdict.pack(anchor=tk.W)

        ttk.Separator(fr, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=4)
        tf = ttk.Frame(fr); tf.pack(fill=tk.BOTH, expand=True)

        cols = ("domain", "ip", "score", "verdict", "status", "cache")
        self.tree = ttk.Treeview(tf, columns=cols, show="headings", height=6)
        for c, w in zip(cols, [220, 130, 90, 70, 50, 60]):
            self.tree.heading(c, text={"domain":"域名","ip":"IP地址","score":"DGA 分数","verdict":"判定","status":"状态","cache":"缓存"}[c])
            self.tree.column(c, width=w, minwidth=50, anchor=tk.CENTER if c not in ("domain", "ip") else tk.W)
        sb = ttk.Scrollbar(tf, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); sb.pack(side=tk.RIGHT, fill=tk.Y)
        for tag, clr in [("safe", self.CLR_SAFE), ("danger", self.CLR_DANGER), ("warn", self.CLR_WARN), ("wl", "#2196f3")]:
            self.tree.tag_configure(tag, foreground=clr)
        return fr

    def _build_log_frame(self):
        fr = ttk.LabelFrame(self.root, text=" 日志 ", style="S.TLabelframe", padding=6)
        bf = ttk.Frame(fr); bf.pack(fill=tk.X, pady=(0, 4))
        ttk.Button(bf, text="清空", command=lambda: self._log_clear()).pack(side=tk.LEFT, padx=2)
        ttk.Button(bf, text="导出", command=self._log_export).pack(side=tk.LEFT, padx=2)
        self.log_txt = scrolledtext.ScrolledText(fr, height=8, wrap=tk.WORD,
                                                  font=("Consolas", 9), state=tk.DISABLED, bg="#fafafa")
        self.log_txt.pack(fill=tk.BOTH, expand=True)
        return fr

    # ── Helpers ────────────────────────────────────────────────────
    def _log_clear(self):
        self.log_txt.configure(state=tk.NORMAL); self.log_txt.delete("1.0", tk.END); self.log_txt.configure(state=tk.DISABLED)

    def _log_export(self):
        p = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("TXT", "*.txt")])
        if p:
            with open(p, "w", encoding="utf-8") as f: f.write(self.log_txt.get("1.0", tk.END))
            logger.info("EXPORT", f"日志导出: {p}")

    def _set_dns(self, text):
        self.dns_txt.configure(state=tk.NORMAL); self.dns_txt.delete("1.0", tk.END)
        self.dns_txt.insert(tk.END, text); self.dns_txt.configure(state=tk.DISABLED)

    def _set_dga_single(self, domain, score, is_dga, whitelisted=False):
        self.lbl_domain.config(text=f"域名: {domain}")
        if whitelisted:
            self.lbl_score.config(text="DGA 分数: — (白名单)", foreground="#2196f3")
            self.lbl_verdict.config(text="判定: 🔵 白名单域名", style="TLabel"); return
        if score is None or isinstance(score, str):
            self.lbl_score.config(text=f"DGA 分数: {score}", foreground="gray")
            self.lbl_verdict.config(text="判定: 检测失败", foreground="gray"); return
        sf = float(score)
        self.lbl_score.config(text=f"DGA 分数: {sf:.4f}")
        if is_dga:
            self.lbl_score.config(foreground=self.CLR_DANGER)
            self.lbl_verdict.config(text="判定: 🔴 DGA 恶意域名", style="Danger.TLabel")
        else:
            self.lbl_score.config(foreground=self.CLR_SAFE)
            self.lbl_verdict.config(text="判定: 🟢 正常域名", style="Safe.TLabel")

    def _add_row(self, domain, score, is_dga, whitelisted=False, ip_addr="—", cache_hit=None):
        cache_text = self._cache_hit_text(cache_hit)
        if whitelisted:
            self.tree.insert("", tk.END, values=(domain, ip_addr, "—", "白名单", "🔵", cache_text), tags=("wl",))
        elif score is None or isinstance(score, str):
            if is_dga:
                self.tree.insert("", tk.END, values=(domain, ip_addr, str(score) or "N/A", "DGA", "🔴", cache_text), tags=("danger",))
            else:
                self.tree.insert("", tk.END, values=(domain, ip_addr, "—", "正常", "🟢", cache_text), tags=("safe",))
        else:
            sf = float(score); dga = is_dga
            self.tree.insert("", tk.END, values=(domain, ip_addr, f"{sf:.4f}", "DGA" if dga else "正常", "🔴" if dga else "🟢", cache_text),
                             tags=("danger" if dga else "safe",))

    @staticmethod
    def _cache_hit_text(cache_hit):
        if cache_hit is True:
            return "✓ 命中"
        elif cache_hit is False:
            return "✗ 上游"
        else:
            return "—"

    def _clear(self):
        self.dns_txt.configure(state=tk.NORMAL); self.dns_txt.delete("1.0", tk.END); self.dns_txt.configure(state=tk.DISABLED)
        self.cache_status_var.set("")
        self.lbl_domain.config(text="域名: —"); self.lbl_score.config(text="DGA 分数: —", foreground="black")
        self.lbl_verdict.config(text="判定: —", style="TLabel")
        for i in self.tree.get_children(): self.tree.delete(i)
        self._batch_results.clear()

    # ── DNS Server ─────────────────────────────────────────────────
    def _check_server_alive(self) -> bool:
        """Check if the DNS server subprocess is still alive.

        Updates internal state and UI if the process has exited.
        Returns True if alive, False otherwise.
        """
        if not self._dns_server_running or self._dns_server_process is None:
            return False
        if self._dns_server_process.poll() is not None:
            # Process has exited
            self._dns_server_running = False
            self._dns_server_process = None
            self._stdout_reader_thread = None
            self.srv_lbl.config(text="● 已退出", foreground=self.CLR_WARN)
            logger.warn("SERVER", "DNS 服务器进程已意外退出")
            return False
        return True

    def _start_server(self):
        """Start the local DNS server subprocess with the current upstream setting."""
        if self._dns_server_running: return
        script = os.path.join(_PROJECT_ROOT, "simpleServer.py")
        if not os.path.isfile(script):
            logger.error("SERVER", "未找到 simpleServer.py")
            self.srv_lbl.config(text="● 启动失败", foreground=self.CLR_DANGER)
            return

        upstream = self.upstream_var.get().strip() or UPSTREAM_DNS
        logger.info("SERVER", f"启动本地 DNS 服务器 (上游: {upstream})...")
        try:
            self._dns_server_process = subprocess.Popen(
                [sys.executable, script, "--upstream", upstream],
                cwd=_PROJECT_ROOT,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0)
            # 启动后台线程读取服务器 stdout 并转发到统一日志器
            def _read_stdout():
                for line in iter(self._dns_server_process.stdout.readline, b""):
                    try:
                        text = line.decode("utf-8", errors="replace").rstrip()
                        if text:
                            logger.info("SERVER", text)
                    except Exception:
                        pass
            self._stdout_reader_thread = threading.Thread(target=_read_stdout, daemon=True)
            self._stdout_reader_thread.start()

            time.sleep(0.5)
            if self._dns_server_process.poll() is not None:
                # 进程已退出，读取剩余输出
                remaining = self._dns_server_process.stdout.read().decode("utf-8", errors="replace")
                err = remaining.strip()
                logger.error("SERVER", f"启动失败: {err}")
                self.srv_lbl.config(text="● 启动失败", foreground=self.CLR_DANGER)
                return
            self._dns_server_running = True
            self.srv_lbl.config(text=f"● 运行中 ({DNS_SERVER_ADDRESS}:{PORT} → {upstream})", foreground=self.CLR_SAFE)
            logger.info("SERVER", f"DNS 服务器已启动: {DNS_SERVER_ADDRESS}:{PORT}, 上游: {upstream}")
        except Exception as e:
            logger.error("SERVER", f"启动异常: {e}")
            self.srv_lbl.config(text="● 启动失败", foreground=self.CLR_DANGER)

    def _stop_server(self):
        """Stop the local DNS server subprocess."""
        if not self._dns_server_running: return
        logger.info("SERVER", "停止 DNS 服务器...")
        try:
            self._dns_server_process.terminate()
            self._dns_server_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._dns_server_process.kill()
        except Exception: pass
        self._dns_server_running = False; self._dns_server_process = None
        self._stdout_reader_thread = None
        self.srv_lbl.config(text="● 已停止", foreground="gray")
        logger.info("SERVER", "DNS 服务器已停止")

    def _restart_server(self):
        """Restart the DNS server with the current upstream setting."""
        if self._task_running:
            messagebox.showinfo("提示", "有任务正在运行，请等待或取消后再重启"); return
        self._stop_server()
        time.sleep(0.3)
        self._start_server()

    # ── Cache ──────────────────────────────────────────────────────
    def _cache_stats(self):
        if not _ensure_cache(): messagebox.showwarning("缓存", "不可用"); return
        try:
            from query import cache_stats as qs
            s = qs()
            if s is None:
                logger.warn("CACHE", "缓存统计失败"); return
            lines = [f"DNS 缓存统计:", f"  总: {s['total']}  有效: {s['active']}  过期: {s['expired']}", ""]
            if s["rows"]:
                lines.append("最近记录:")
                for dom, qt, rd, exp in s["rows"]:
                    rem = exp - s["now"]; st = f"剩余{rem}s" if rem > 0 else "过期"
                    try:
                        qt_str = dns.rdatatype.to_text(qt)
                    except Exception:
                        qt_str = str(qt)
                    lines.append(f"  {dom} {qt_str} → {rd[:40]} ({st})")
            else: lines.append("(空)")
            self._set_dns("\n".join(lines))
            logger.info("CACHE", f"缓存: {s['total']}条, {s['active']}有效")
        except Exception as e:
            logger.error("CACHE", f"缓存统计失败: {e}")

    def _cache_clear(self):
        if not _ensure_cache(): return
        try:
            from query import clear_expired_cache as cec
            removed = cec()
            logger.info("CACHE", f"已清理过期缓存 ({removed} 条)")
        except Exception as e:
            logger.error("CACHE", f"清理失败: {e}")

    # ── Core actions ───────────────────────────────────────────────
    def _run_query_detect(self):
        if self._task_running:
            messagebox.showinfo("提示", "有任务正在运行，请等待或取消"); return
        if not self._check_server_alive():
            messagebox.showwarning("服务器", "本地 DNS 服务器未运行，请重启"); return
        if self.mode_var.get() == "batch": return self._run_batch()
        domain = self.domain_var.get().strip()
        if not domain: messagebox.showwarning("错误", "请输入域名"); return
        qtype = self.qtype_var.get(); thr = self.threshold_var.get()
        use_cache = self.use_cache_var.get(); use_wl = self.use_wl_var.get()
        logger.info("QUERY", f"查询 {domain} {qtype} @ {DNS_SERVER_ADDRESS}:{DNS_SERVER_PORT}...")
        self._set_busy()

        def _do():
            resp, text, hit = dns_query(domain, qtype, DNS_SERVER_ADDRESS, port=DNS_SERVER_PORT, use_cache=use_cache)
            if self._cancel_event.is_set():
                self.root.after(0, self._set_idle)
                return
            self.root.after(0, lambda: self._on_dns_done(domain, resp, text, thr, hit, use_wl))
        threading.Thread(target=_do, daemon=True).start()

    def _on_dns_done(self, domain, resp, text, thr, cache_hit, use_wl):
        self._set_idle()
        self._set_dns(text)
        if cache_hit:
            self.cache_status_var.set("🟢 缓存命中")
            self.cache_status_lbl.configure(foreground=self.CLR_SAFE)
        elif resp:
            self.cache_status_var.set("🟠 上游查询 (已缓存)")
            self.cache_status_lbl.configure(foreground=self.CLR_WARN)
        else:
            self.cache_status_var.set("🔴 查询失败")
            self.cache_status_lbl.configure(foreground=self.CLR_DANGER)
        if cache_hit:
            logger.info("CACHE_HIT", "DNS 缓存命中")
        elif resp:
            logger.info("QUERY", "DNS 查询完成 (已缓存)")
        else:
            logger.warn("QUERY", "DNS 失败")
        qname_dot = domain if domain.endswith(".") else domain + "."
        if use_wl and is_whitelisted(qname_dot):
            logger.info("WHITELIST", domain); self._set_dga_single(domain, None, False, True); return
        is_dga, score = check_dga(domain, thr)
        if score is not None and not isinstance(score, str):
            logger.info("DGA", f"{domain} → {float(score):.4f} ({'DGA' if is_dga else '正常'})")
        self._set_dga_single(domain, score, is_dga)

    def _run_dga_only(self):
        if self._task_running:
            messagebox.showinfo("提示", "有任务正在运行，请等待或取消"); return
        if self.mode_var.get() == "batch": return self._run_batch()
        domain = self.domain_var.get().strip()
        if not domain: messagebox.showwarning("错误", "请输入域名"); return
        thr = self.threshold_var.get()
        qname_dot = domain if domain.endswith(".") else domain + "."
        if self.use_wl_var.get() and is_whitelisted(qname_dot):
            logger.info("WHITELIST", domain); self._set_dga_single(domain, None, False, True); return
        logger.info("DGA", f"检测: {domain}...")
        self._set_busy()

        def _do():
            is_dga, score = check_dga(domain, thr)
            if self._cancel_event.is_set():
                self.root.after(0, self._set_idle)
                return
            def _on_done():
                self._set_dga_single(domain, score, is_dga)
                self._set_idle()
            self.root.after(0, _on_done)
        threading.Thread(target=_do, daemon=True).start()

    def _run_batch(self):
        if self._task_running:
            messagebox.showinfo("提示", "有任务正在运行，请等待或取消"); return
        if not self._check_server_alive():
            messagebox.showwarning("服务器", "本地 DNS 服务器未运行，请重启"); return
        fp = self.filepath_var.get().strip()
        if not fp or not os.path.isfile(fp): messagebox.showwarning("错误", "选择 JSON 文件"); return
        thr = self.threshold_var.get(); use_wl = self.use_wl_var.get()
        use_cache = self.use_cache_var.get()
        qtype = self.qtype_var.get()
        logger.info("BATCH", f"批量模式: 使用本地 DNS 服务器 (DGA 检测已启用)")
        logger.info("BATCH", f"加载 JSON: {fp}")
        try: domains = load_domains_from_json(fp)
        except Exception as e: logger.error("BATCH", f"JSON 错误: {e}"); return
        if not domains: logger.warn("BATCH", "无域名"); return
        logger.info("BATCH", f"批量检测 {len(domains)} 域名...")
        for i in self.tree.get_children(): self.tree.delete(i)
        self._batch_results.clear()
        self._set_busy(len(domains))

        def _do():
            wl_set = {d for d in domains if use_wl and is_whitelisted(d if d.endswith(".") else d + ".")} if use_wl else set()
            non_wl = [d for d in domains if d not in wl_set]
            is_list, sc_list = (check_dga_many(non_wl, thr) if non_wl else (None, None))

            # 通过本地DNS服务器查询所有域名，DGA域名由服务器返回sinkhole(0.0.0.0)
            dns_results = {}
            dns_cache_hits = {}
            total = len(domains)
            for i, d in enumerate(domains):
                if self._cancel_event.is_set():
                    logger.info("BATCH", f"任务已取消 (已完成 {i}/{total})")
                    break
                try:
                    resp, text, hit = dns_query(d, qtype, DNS_SERVER_ADDRESS, port=DNS_SERVER_PORT, use_cache=use_cache)
                    dns_cache_hits[d] = hit
                    ip_addr = "—"
                    if resp and resp.answer:
                        for rrset in resp.answer:
                            if rrset.rdtype in (1, 28, 5):  # A / AAAA / CNAME
                                ips = [r.to_text() for r in rrset]
                                ip_addr = ", ".join(ips) if ips else "—"
                                break
                    elif hit and text:
                        m = re.search(r'IN\s+(?:A|AAAA|CNAME)\s+(\S+)', text)
                        if m:
                            ip_addr = m.group(1)
                    # sinkhole响应(0.0.0.0)表示DGA被拦截，显示"—"
                    if ip_addr == "0.0.0.0":
                        ip_addr = "—"
                    dns_results[d] = ip_addr
                except Exception:
                    dns_results[d] = "—"
                    dns_cache_hits[d] = None
                # 更新进度
                self.root.after(0, lambda cur=i + 1, tot=total: self._update_progress(cur, tot))

            cancelled = self._cancel_event.is_set()
            self.root.after(0, lambda: self._on_batch_done(
                domains, wl_set, non_wl, is_list, sc_list, thr,
                dns_results, dns_cache_hits, cancelled))
        threading.Thread(target=_do, daemon=True).start()

    def _on_batch_done(self, domains, wl_set, non_wl, is_list, sc_list, thr,
                       dns_results, dns_cache_hits=None, cancelled=False):
        if dns_cache_hits is None:
            dns_cache_hits = {}
        dga_n = wl_n = ok_n = 0; idx = 0
        for d in domains:
            if d not in dns_results:
                break  # cancelled — stop at last processed domain
            ip_addr = dns_results.get(d, "—")
            ch = dns_cache_hits.get(d, None)
            if d in wl_set:
                self._add_row(d, None, False, True, ip_addr, ch)
                self._batch_results.append({"domain": d, "ip": ip_addr, "score": None, "is_dga": False, "whitelisted": True, "threshold": thr, "cache_hit": ch})
                wl_n += 1
            else:
                is_d = is_list[idx] if is_list and idx < len(is_list) else False
                sc = sc_list[idx] if sc_list and idx < len(sc_list) else None
                self._add_row(d, sc, is_d, False, ip_addr, ch)
                self._batch_results.append({"domain": d, "ip": ip_addr, "score": float(sc) if sc is not None and not isinstance(sc, str) else None, "is_dga": bool(is_d), "whitelisted": False, "threshold": thr, "cache_hit": ch})
                if is_d: dga_n += 1
                else: ok_n += 1
                idx += 1
        cache_hit_count = sum(1 for v in dns_cache_hits.values() if v is True)
        cache_miss_count = sum(1 for v in dns_cache_hits.values() if v is False)
        self.cache_status_var.set(f"✓ 命中: {cache_hit_count}  ✗ 上游: {cache_miss_count}")
        self.cache_status_lbl.configure(foreground=self.CLR_SAFE if cache_hit_count > cache_miss_count else "gray")
        processed = wl_n + dga_n + ok_n
        if cancelled:
            logger.warn("BATCH", f"批量已取消: {processed}/{len(domains)} 域, {wl_n}白名单, {dga_n}DGA, {ok_n}正常")
        else:
            logger.info("BATCH", f"批量完成: {len(domains)}域, {wl_n}白名单, {dga_n}DGA, {ok_n}正常 | 缓存命中{cache_hit_count}")
        self.lbl_domain.config(text=f"批量汇总: {processed}/{len(domains)} 域名")
        self.lbl_score.config(text=f"DGA: {dga_n} | 白名单: {wl_n} | 正常: {ok_n}", foreground=self.CLR_WARN if dga_n else self.CLR_SAFE)
        self.lbl_verdict.config(text=f"阈值: {thr:.2f}" + (" (已取消)" if cancelled else ""), style="TLabel")
        self._set_idle()

    # ── Git ────────────────────────────────────────────────────────
    def _git(self, *args):
        try:
            r = subprocess.run(["git"] + list(args), cwd=_PROJECT_ROOT, capture_output=True, text=True, timeout=60, encoding="utf-8", errors="replace")
            return (r.returncode == 0, r.stdout.strip() if r.returncode == 0 else (r.stdout.strip() + "\n" + r.stderr.strip()).strip())
        except Exception as e: return (False, str(e))

    def _git_status(self):
        def _do():
            lines = []
            ok, out = self._git("branch", "--show-current"); lines.append(f"分支: {out if ok else '?'}")
            ok, out = self._git("log", "-1", "--format=%h %s (%cr)"); lines.append(f"最新: {out if ok else '?'}")
            ok, out = self._git("status", "--short")
            lines.append(f"修改: {len(out.splitlines()) if ok and out else 0} 文件" if ok else "状态: ?")
            self.root.after(0, lambda: (logger.info("GIT", "\n".join(lines)), self._set_dns("\n".join(lines))))
        threading.Thread(target=_do, daemon=True).start()

    # ── Export ─────────────────────────────────────────────────────
    def _export(self):
        if not self._batch_results: messagebox.showwarning("导出", "无结果"); return
        p = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json"), ("CSV", "*.csv")])
        if not p: return
        try:
            if p.endswith(".csv"):
                with open(p, "w", newline="", encoding="utf-8") as f:
                    w = csv.DictWriter(f, fieldnames=["domain", "ip", "score", "is_dga", "whitelisted", "threshold", "cache_hit"]); w.writeheader(); w.writerows(self._batch_results)
            else:
                with open(p, "w", encoding="utf-8") as f: json.dump(self._batch_results, f, ensure_ascii=False, indent=2)
            logger.info("EXPORT", f"导出: {p}")
        except Exception as e: messagebox.showerror("导出失败", str(e))

    # ── Cleanup ────────────────────────────────────────────────────
    def on_closing(self):
        if self._task_running:
            if not messagebox.askyesno("确认退出", "有任务正在运行，确定要退出吗？"):
                return
            self._cancel_event.set()
        if self._dns_server_running: self._stop_server()
        close_cache()
        self.root.destroy()


def main():
    root = tk.Tk()
    app = DGAGuiApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()

if __name__ == "__main__":
    main()
