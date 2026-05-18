# prefetcher.py
import threading
import time
import queue
import logging
from collections import defaultdict, deque
from typing import Tuple, List

prefetch_logger = logging.getLogger("Prefetch")
prefetch_logger.setLevel(logging.INFO)
if not prefetch_logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('[%(asctime)s] [%(levelname)s] [PREFETCH] %(message)s'))
    prefetch_logger.addHandler(handler)

def mylogf(msg):
    prefetch_logger.info(msg)


SLIDING_WINDOW_SIZE = 200
CORRELATION_BACKTRACK = 15
MIN_COUNT = 3
CONFIDENCE_THRESHOLD = 0.7
PREFETCH_INTERVAL_SEC = 30
PREFETCH_QTYPE = 'A'


class PrefetchManager:
    
    def __init__(self, resolver, window_size=SLIDING_WINDOW_SIZE,
                 backtrack=CORRELATION_BACKTRACK, min_count=MIN_COUNT,
                 confidence_thresh=CONFIDENCE_THRESHOLD,
                 prefetch_interval=PREFETCH_INTERVAL_SEC):
        self.resolver = resolver
        self.window_size = window_size
        self.backtrack = backtrack
        self.min_count = min_count
        self.confidence_thresh = confidence_thresh
        self.prefetch_interval = prefetch_interval
        
        self.history = deque(maxlen=window_size)
        self.co_occurrence = defaultdict(int)
        self.lock = threading.RLock()
        
        self.query_queue = queue.Queue()
        
        self._stop_event = threading.Event()
        self._record_thread = None
        self._prefetch_thread = None
    
    def start(self):
        if self._record_thread is None or not self._record_thread.is_alive():
            self._record_thread = threading.Thread(target=self._record_worker,
                                                   name="PrefetchRecordWorker",
                                                   daemon=True)
            self._record_thread.start()
        if self._prefetch_thread is None or not self._prefetch_thread.is_alive():
            self._prefetch_thread = threading.Thread(target=self._prefetch_loop,
                                                     name="PrefetchAnalyzer",
                                                     daemon=True)
            self._prefetch_thread.start()
        mylogf("PrefetchManager started")
    
    def stop(self):
        self._stop_event.set()
        self.query_queue.put(None)
        if self._record_thread and self._record_thread.is_alive():
            self._record_thread.join(timeout=3)
        if self._prefetch_thread and self._prefetch_thread.is_alive():
            self._prefetch_thread.join(timeout=3)
        mylogf("PrefetchManager stopped")
    
    def record_query(self, domain: str):
        self.query_queue.put(domain)
    
    def _record_worker(self):
        while not self._stop_event.is_set():
            try:
                domain = self.query_queue.get(timeout=1.0)
                if domain is None:
                    continue
                self._update_stats(domain)
            except queue.Empty:
                continue
            except Exception as e:
                mylogf(f"Record error: {e}")
    
    def _update_stats(self, domain: str):
        with self.lock:
            cur_len = len(self.history)
            self.history.append(domain)
            if cur_len > 0:
                start = max(0, len(self.history) - self.backtrack - 1)
                for i in range(start, len(self.history) - 1):
                    prev_domain = self.history[i]
                    if prev_domain != domain:
                        key = self._make_key(prev_domain, domain)
                        self.co_occurrence[key] += 1
    
    @staticmethod
    def _make_key(a: str, b: str) -> Tuple[str, str]:
        return (a, b)
    
    def _get_confidence(self, domain_a: str, domain_b: str) -> float:
        with self.lock:
            count_a = sum(1 for d in self.history if d == domain_a)
            if count_a == 0:
                return 0.0
            key = self._make_key(domain_a, domain_b)
            count_ab = self.co_occurrence.get(key, 0)
            return count_ab / count_a
    
    def _get_top_candidates(self, limit=10) -> List[Tuple[str, str, float]]:
        with self.lock:
            candidates = []
            for (a, b), cnt in self.co_occurrence.items():
                if cnt >= self.min_count:
                    conf_ab = self._get_confidence(a, b)
                    if conf_ab >= self.confidence_thresh:
                        candidates.append((a, b, conf_ab))
                    if a != b:
                        conf_ba = self._get_confidence(b, a)
                        if conf_ba >= self.confidence_thresh:
                            candidates.append((b, a, conf_ba))
        unique = {}
        for src, tgt, conf in candidates:
            key = f"{src}->{tgt}"
            if key not in unique or unique[key] < conf:
                unique[key] = conf
        sorted_items = sorted(unique.items(), key=lambda x: x[1], reverse=True)
        result = []
        for key, conf in sorted_items[:limit]:
            src, tgt = key.split("->")
            result.append((src, tgt, conf))
        return result
    
    def _prefetch_domain(self, domain: str, qtype=PREFETCH_QTYPE):
        try:
            from dnslib import DNSRecord
            clean_domain = domain.rstrip('.')
            q = DNSRecord.question(clean_domain, qtype)
            reply = self.resolver._forward(q)
            if reply and reply.header.rcode == 0 and reply.rr:
                self.resolver.add_records(reply, clean_domain)
                mylogf(f"Successfully cached {clean_domain} (type {qtype})")
            else:
                mylogf(f"No valid response for {clean_domain}")
        except Exception as e:
            mylogf(f"Failed to prefetch {domain}: {e}")
    
    def _prefetch_loop(self):
        while not self._stop_event.is_set():
            if self._stop_event.wait(self.prefetch_interval):
                break
            try:
                candidates = self._get_top_candidates(limit=5)
                if not candidates:
                    continue
                mylogf(f"Found {len(candidates)} candidate pairs")
                for src, tgt, conf in candidates:
                    mylogf(f"Candidate: {src} -> {tgt} (conf={conf:.2f})")
                    self._prefetch_domain(tgt)
                    time.sleep(0.5)
            except Exception as e:
                mylogf(f"Error in prefetch loop: {e}")