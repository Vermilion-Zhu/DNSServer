import argparse
import gzip
import json
import math
import os
import random
import re
import zipfile
from collections import Counter
import hashlib

import joblib
import numpy as np
try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    HAS_MATPLOTLIB = True
except Exception:
    plt = None
    HAS_MATPLOTLIB = False
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, roc_curve, auc
from sklearn.model_selection import train_test_split


NGRAM_BUCKETS = 32
NGRAM_MAX_N = 3
MARKOV_LOW_PROB_TH = 1e-3
MARKOV_CHARS = "abcdefghijklmnopqrstuvwxyz0123456789-"


def resolve_existing_path(path, fallback_dirs=None):
    if not path:
        return path
    if os.path.exists(path):
        return path

    fallback_dirs = fallback_dirs or []
    if os.path.isabs(path):
        return path

    name = os.path.basename(path)
    for d in fallback_dirs:
        candidate = os.path.join(d, name)
        if os.path.exists(candidate):
            return candidate
    return path


def normalize_domain(value):
    if not value:
        return None
    domain = value.strip().lower()
    if not domain:
        return None
    if domain.endswith("."):
        domain = domain[:-1]
    if not re.fullmatch(r"[a-z0-9.-]+", domain):
        return None
    if len(domain) < 4 or len(domain) > 50:
        return None
    return domain


def domain_base(domain):
    if "." in domain:
        return domain.split(".")[0]
    return domain


def shannon_entropy(text):
    if not text:
        return 0.0
    counts = Counter(text)
    length = len(text)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def max_consonant_run(text):
    if not text:
        return 0
    runs = re.findall(r"[bcdfghjklmnpqrstvwxyz]+", text)
    return max((len(run) for run in runs), default=0)


def ngram_buckets(text, n, buckets):
    counts = [0] * buckets
    if len(text) < n:
        return counts
    for i in range(len(text) - n + 1):
        ng = text[i : i + n]
        digest = hashlib.md5(ng.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "little") % buckets
        counts[idx] += 1
    total = sum(counts)
    if total == 0:
        return counts
    return [c / total for c in counts]


def fit_markov_model(domains, alpha=0.1, chars=MARKOV_CHARS):
    alpha = float(alpha)
    if alpha <= 0:
        raise ValueError("markov alpha must be > 0")
    chars = "".join(dict.fromkeys(chars))
    if not chars:
        raise ValueError("markov chars must not be empty")

    counts = {c: Counter() for c in chars}
    totals = Counter()

    for domain in domains:
        base = domain_base(domain)
        if len(base) < 2:
            continue
        for a, b in zip(base[:-1], base[1:]):
            if a in counts and b in counts:
                counts[a][b] += 1
                totals[a] += 1

    vocab = len(chars)
    transitions = {}
    for a in chars:
        row = {}
        denom = totals[a] + alpha * vocab
        if denom <= 0:
            uniform = 1.0 / vocab
            for b in chars:
                row[b] = uniform
        else:
            for b in chars:
                row[b] = (counts[a][b] + alpha) / denom
        transitions[a] = row

    return {
        "chars": chars,
        "alpha": alpha,
        "transitions": transitions,
    }


def markov_features(domain, markov_model):
    if not markov_model:
        return []

    base = domain_base(domain)
    if len(base) < 2:
        return [0.0, 0.0, 0.0, 0.0]

    chars = set(markov_model.get("chars", ""))
    transitions = markov_model.get("transitions", {})
    if not chars or not transitions:
        return [0.0, 0.0, 0.0, 0.0]

    eps = 1e-12
    low_th = float(MARKOV_LOW_PROB_TH)
    logps = []
    low_cnt = 0

    for a, b in zip(base[:-1], base[1:]):
        if a not in chars or b not in chars:
            continue
        p = transitions.get(a, {}).get(b, eps)
        p = max(float(p), eps)
        logp = math.log(p)
        logps.append(logp)
        if p < low_th:
            low_cnt += 1

    if not logps:
        return [0.0, 0.0, 0.0, 0.0]

    avg_logp = sum(logps) / len(logps)
    min_logp = min(logps)
    low_prob_ratio = low_cnt / len(logps)
    perplexity = math.exp(-avg_logp)
    return [avg_logp, min_logp, low_prob_ratio, perplexity]


def extract_features(domain, markov_model=None):
    base = domain_base(domain)
    length = len(base)
    extra_dims = max(0, NGRAM_MAX_N - 1) * NGRAM_BUCKETS
    markov_dims = 4 if markov_model else 0
    if length == 0:
        return [0, 0.0, 0.0, 0.0, 0] + [0.0] * extra_dims + [0.0] * markov_dims
    vowels = len(re.findall(r"[aeiou]", base))
    digits = len(re.findall(r"\d", base))
    vowel_ratio = vowels / length
    digit_ratio = digits / length
    entropy = shannon_entropy(base)
    consonant_run = max_consonant_run(base)
    ngrams = []
    for n in range(2, NGRAM_MAX_N + 1):
        ngrams += ngram_buckets(base, n, NGRAM_BUCKETS)
    mk = markov_features(domain, markov_model)
    return [length, vowel_ratio, digit_ratio, entropy, consonant_run] + ngrams + mk


def iter_tranco_domains(path, limit):
    count = 0
    if path.lower().endswith(".zip"):
        with zipfile.ZipFile(path, "r") as zf:
            csv_names = [n for n in zf.namelist() if n.endswith(".csv")]
            if not csv_names:
                return
            with zf.open(csv_names[0]) as fh:
                for raw in fh:
                    line = raw.decode("utf-8", errors="ignore").strip()
                    if not line:
                        continue
                    parts = line.split(",")
                    if len(parts) < 2:
                        continue
                    domain = normalize_domain(parts[1])
                    if not domain:
                        continue
                    yield domain
                    count += 1
                    if count >= limit:
                        return
    else:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(",")
                if len(parts) < 2:
                    continue
                domain = normalize_domain(parts[1])
                if not domain:
                    continue
                yield domain
                count += 1
                if count >= limit:
                    return


def iter_ranked_domains(path, limit):
    count = 0
    if path.lower().endswith(".zip"):
        with zipfile.ZipFile(path, "r") as zf:
            csv_names = [n for n in zf.namelist() if n.endswith(".csv")]
            if not csv_names:
                return
            with zf.open(csv_names[0]) as fh:
                for raw in fh:
                    line = raw.decode("utf-8", errors="ignore").strip()
                    if not line:
                        continue
                    parts = line.split(",")
                    if len(parts) < 2:
                        continue
                    domain = normalize_domain(parts[1])
                    if not domain:
                        continue
                    yield domain
                    count += 1
                    if count >= limit:
                        return
    else:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(",")
                if len(parts) < 2:
                    continue
                domain = normalize_domain(parts[1])
                if not domain:
                    continue
                yield domain
                count += 1
                if count >= limit:
                    return


def iter_extrahop_domains(path, limit):
    count = 0
    opener = gzip.open if path.lower().endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("threat") != "dga":
                continue
            domain = normalize_domain(record.get("domain"))
            if not domain:
                continue
            yield domain
            count += 1
            if count >= limit:
                return


def build_dataset(tranco_path, dga_path, per_class, seed):
    benign = list(iter_tranco_domains(tranco_path, per_class))
    malicious = list(iter_extrahop_domains(dga_path, per_class))
    rnd = random.Random(seed)
    rnd.shuffle(benign)
    rnd.shuffle(malicious)
    size = min(len(benign), len(malicious))
    benign = benign[:size]
    malicious = malicious[:size]
    return benign, malicious


def split_domains(benign, malicious, seed, val_ratio=0.1, test_ratio=0.2):
    val_ratio = float(val_ratio)
    test_ratio = float(test_ratio)
    if val_ratio < 0 or test_ratio < 0 or (val_ratio + test_ratio) >= 1.0:
        raise ValueError("val_ratio/test_ratio must be >=0 and val_ratio+test_ratio < 1")

    holdout_ratio = val_ratio + test_ratio
    if holdout_ratio <= 0:
        b_train, b_val, b_test = benign, [], []
        m_train, m_val, m_test = malicious, [], []
    else:
        b_train, b_holdout = train_test_split(
            benign,
            test_size=holdout_ratio,
            random_state=seed,
            shuffle=True,
        )
        m_train, m_holdout = train_test_split(
            malicious,
            test_size=holdout_ratio,
            random_state=seed + 1,
            shuffle=True,
        )

        if test_ratio <= 0:
            b_val, b_test = b_holdout, []
            m_val, m_test = m_holdout, []
        elif val_ratio <= 0:
            b_val, b_test = [], b_holdout
            m_val, m_test = [], m_holdout
        else:
            test_in_holdout = test_ratio / holdout_ratio
            b_val, b_test = train_test_split(
                b_holdout,
                test_size=test_in_holdout,
                random_state=seed,
                shuffle=True,
            )
            m_val, m_test = train_test_split(
                m_holdout,
                test_size=test_in_holdout,
                random_state=seed + 1,
                shuffle=True,
            )

    d_train = b_train + m_train
    y_train = [0] * len(b_train) + [1] * len(m_train)
    d_val = b_val + m_val
    y_val = [0] * len(b_val) + [1] * len(m_val)
    d_test = b_test + m_test
    y_test = [0] * len(b_test) + [1] * len(m_test)

    rnd = random.Random(seed)

    def _shuffle(ds, ys):
        pairs = list(zip(ds, ys))
        rnd.shuffle(pairs)
        if not pairs:
            return [], []
        a, b = zip(*pairs)
        return list(a), list(b)

    d_train, y_train = _shuffle(d_train, y_train)
    d_val, y_val = _shuffle(d_val, y_val)
    d_test, y_test = _shuffle(d_test, y_test)

    return (
        d_train,
        np.array(y_train, dtype=np.int32),
        d_val,
        np.array(y_val, dtype=np.int32),
        d_test,
        np.array(y_test, dtype=np.int32),
    )


def build_features(domains, markov_model):
    return np.array([extract_features(d, markov_model=markov_model) for d in domains], dtype=np.float32)


def train_model(
    d_train,
    y_train,
    d_val,
    y_val,
    d_test,
    y_test,
    seed,
    tune,
    use_markov=False,
    markov_alpha=0.1,
    rf_n_estimators=200,
    rf_max_depth=None,
    rf_min_samples_leaf=1,
):
    markov_model = None
    if use_markov:
        train_benign = [d for d, label in zip(d_train, y_train) if int(label) == 0]
        markov_model = fit_markov_model(train_benign, alpha=markov_alpha)

    X_train = build_features(d_train, markov_model)
    X_val = build_features(d_val, markov_model) if len(d_val) else np.zeros((0, X_train.shape[1]), dtype=np.float32)
    X_test = build_features(d_test, markov_model)

    if not tune:
        model = RandomForestClassifier(
            n_estimators=int(rf_n_estimators),
            max_depth=rf_max_depth,
            min_samples_leaf=int(rf_min_samples_leaf),
            n_jobs=-1,
            random_state=seed,
        )
        X_fit = np.concatenate([X_train, X_val], axis=0) if len(X_val) else X_train
        y_fit = np.concatenate([y_train, y_val], axis=0) if len(y_val) else y_train
        model.fit(X_fit, y_fit)
        y_pred = model.predict(X_test)
        report = classification_report(y_test, y_pred, digits=4)
        return model, report, None, X_test, y_test, d_test, markov_model

    candidates = [
        {"n_estimators": 200, "max_depth": None, "min_samples_leaf": 1},
        {"n_estimators": 300, "max_depth": 30, "min_samples_leaf": 1},
        {"n_estimators": 400, "max_depth": 20, "min_samples_leaf": 2},
        {"n_estimators": 500, "max_depth": 25, "min_samples_leaf": 2},
        {
            "n_estimators": int(rf_n_estimators),
            "max_depth": rf_max_depth,
            "min_samples_leaf": int(rf_min_samples_leaf),
        },
    ]
    uniq = []
    seen = set()
    for p in candidates:
        k = (p["n_estimators"], p["max_depth"], p["min_samples_leaf"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(p)
    candidates = uniq

    best = None
    best_report = None
    best_f1 = -1.0
    for params in candidates:
        model = RandomForestClassifier(
            n_estimators=params["n_estimators"],
            max_depth=params["max_depth"],
            min_samples_leaf=params["min_samples_leaf"],
            n_jobs=-1,
            random_state=seed,
        )
        if len(X_val) == 0:
            X_eval, y_eval = X_train, y_train
        else:
            X_eval, y_eval = X_val, y_val
        model.fit(X_train, y_train)
        y_pred = model.predict(X_eval)
        report = classification_report(y_eval, y_pred, digits=4, output_dict=True)
        f1 = report["macro avg"]["f1-score"]
        if f1 > best_f1:
            best_f1 = f1
            best = model
            best_report = report

    X_fit = np.concatenate([X_train, X_val], axis=0) if len(X_val) else X_train
    y_fit = np.concatenate([y_train, y_val], axis=0) if len(y_val) else y_train
    best.fit(X_fit, y_fit)
    report_text = classification_report(y_test, best.predict(X_test), digits=4)
    return best, report_text, best_report, X_test, y_test, d_test, markov_model


def feature_names(use_markov=False):
    base = ["length", "vowel_ratio", "digit_ratio", "entropy", "max_consonant_run"]
    ngrams = []
    for n in range(2, NGRAM_MAX_N + 1):
        ngrams += [f"{n}gram_{i}" for i in range(NGRAM_BUCKETS)]
    markov = ["mk_avg_logp", "mk_min_logp", "mk_low_prob_ratio", "mk_perplexity"] if use_markov else []
    return base + ngrams + markov


def save_feature_importance(model, output_path, use_markov=False):
    if not HAS_MATPLOTLIB:
        return []
    names = feature_names(use_markov=use_markov)
    importances = model.feature_importances_
    idx = np.argsort(importances)[-20:]
    top_names = [names[i] for i in idx]
    top_vals = importances[idx]
    plt.figure(figsize=(8, 6))
    plt.barh(top_names, top_vals)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    return list(zip(top_names, top_vals.tolist()))


def save_roc_curve(model, X_test, y_test, output_path):
    if not HAS_MATPLOTLIB:
        return None
    if not hasattr(model, "predict_proba"):
        return None
    probs = model.predict_proba(X_test)[:, 1]
    fpr, tpr, _ = roc_curve(y_test, probs)
    roc_auc = auc(fpr, tpr)
    plt.figure(figsize=(6, 5))
    plt.plot(fpr, tpr, label=f"AUC={roc_auc:.4f}")
    plt.plot([0, 1], [0, 1], linestyle="--")
    plt.xlabel("False Positive Rate")
    plt.ylabel("True Positive Rate")
    plt.legend(loc="lower right")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    return float(roc_auc)


def save_misclassified_examples(model, X_test, y_test, domains_test, output_path, limit):
    if limit <= 0:
        return
    y_pred = model.predict(X_test)
    if hasattr(model, "predict_proba"):
        y_prob = model.predict_proba(X_test)[:, 1]
    else:
        y_prob = np.zeros(len(y_test), dtype=np.float32)

    fp = np.where((y_test == 0) & (y_pred == 1))[0]
    fn = np.where((y_test == 1) & (y_pred == 0))[0]

    fp_sorted = fp[np.argsort(-y_prob[fp])] if len(fp) else fp
    fn_sorted = fn[np.argsort(y_prob[fn])] if len(fn) else fn

    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write("# 误判样例\n\n")
        fh.write("## False Positive（真实正常，被判为DGA）\n\n")
        fh.write("|domain|p(dga)|length|vowel_ratio|digit_ratio|entropy|max_consonant_run|\n")
        fh.write("|---|---:|---:|---:|---:|---:|---:|\n")
        for i in fp_sorted[:limit]:
            f = X_test[i][:5]
            fh.write(
                f"|{domains_test[i]}|{float(y_prob[i]):.4f}|{int(f[0])}|{float(f[1]):.4f}|{float(f[2]):.4f}|{float(f[3]):.4f}|{int(f[4])}|\n"
            )

        fh.write("\n## False Negative（真实DGA，被判为正常）\n\n")
        fh.write("|domain|p(dga)|length|vowel_ratio|digit_ratio|entropy|max_consonant_run|\n")
        fh.write("|---|---:|---:|---:|---:|---:|---:|\n")
        for i in fn_sorted[:limit]:
            f = X_test[i][:5]
            fh.write(
                f"|{domains_test[i]}|{float(y_prob[i]):.4f}|{int(f[0])}|{float(f[1]):.4f}|{float(f[2]):.4f}|{float(f[3]):.4f}|{int(f[4])}|\n"
            )


def save_external_benign_eval(model, benign_domains, output_path, limit, markov_model=None):
    if limit <= 0:
        return None
    domains = []
    for domain in benign_domains:
        domains.append(domain)
    X = np.array([extract_features(d, markov_model=markov_model) for d in domains], dtype=np.float32)
    y_pred = model.predict(X)
    if hasattr(model, "predict_proba"):
        y_prob = model.predict_proba(X)[:, 1]
    else:
        y_prob = np.zeros(len(domains), dtype=np.float32)

    fp_idx = np.where(y_pred == 1)[0]
    fp_rate = float(len(fp_idx) / len(domains)) if len(domains) else 0.0
    fp_sorted = fp_idx[np.argsort(-y_prob[fp_idx])] if len(fp_idx) else fp_idx

    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write("# 外部白样本误报评估（False Positive Rate）\n\n")
        fh.write(f"- 样本数：{len(domains)}\n")
        fh.write(f"- 误报数（被判为DGA）：{len(fp_idx)}\n")
        fh.write(f"- 误报率（FPR）：{fp_rate:.4%}\n\n")
        fh.write("## 误报 Top 样例（按 p(dga) 从高到低）\n\n")
        fh.write("|domain|p(dga)|length|vowel_ratio|digit_ratio|entropy|max_consonant_run|\n")
        fh.write("|---|---:|---:|---:|---:|---:|---:|\n")
        for i in fp_sorted[:20]:
            f = X[i][:5]
            fh.write(
                f"|{domains[i]}|{float(y_prob[i]):.4f}|{int(f[0])}|{float(f[1]):.4f}|{float(f[2]):.4f}|{float(f[3]):.4f}|{int(f[4])}|\n"
            )

    return fp_rate


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tranco", default="data/raw/tranco_6GYWX-1m.csv.zip")
    parser.add_argument("--dga", default="data/raw/dga-training-data-encoded.json.gz")
    parser.add_argument("--per-class", type=int, default=200000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default="artifacts/models/active/dga_model.pkl")
    parser.add_argument("--load-model", default="")
    parser.add_argument("--tune", action="store_true")
    parser.add_argument("--plots-dir", default="artifacts/plots/plots")
    parser.add_argument("--ngram-buckets", type=int, default=32)
    parser.add_argument("--ngram-max-n", type=int, default=3)
    parser.add_argument("--use-markov", action="store_true")
    parser.add_argument("--markov-alpha", type=float, default=0.1)
    parser.add_argument("--markov-low-prob-th", type=float, default=1e-3)
    parser.add_argument("--rf-n-estimators", type=int, default=200)
    parser.add_argument("--rf-max-depth", type=int, default=-1)
    parser.add_argument("--rf-min-samples-leaf", type=int, default=1)
    parser.add_argument("--model-compress", type=int, default=0)
    parser.add_argument("--misclassified", type=int, default=0)
    parser.add_argument("--eval-benign", default="")
    parser.add_argument("--eval-benign-limit", type=int, default=0)
    parser.add_argument("--val-ratio", type=float, default=0.1)
    parser.add_argument("--test-ratio", type=float, default=0.2)
    return parser.parse_args()


def load_model_bundle(path):
    obj = joblib.load(path)
    if isinstance(obj, dict) and "model" in obj:
        model = obj["model"]
        cfg = obj.get("feature_config", {}) or {}
        markov_model = obj.get("markov_model")
        return model, cfg, markov_model
    return obj, {}, None


def save_model_bundle(path, model, markov_model, compress_level, extra_config=None):
    cfg = {
        "ngram_buckets": int(NGRAM_BUCKETS),
        "ngram_max_n": int(NGRAM_MAX_N),
        "use_markov": bool(markov_model is not None),
        "markov_low_prob_th": float(MARKOV_LOW_PROB_TH),
    }
    if extra_config:
        cfg.update(extra_config)
    payload = {
        "model": model,
        "markov_model": markov_model,
        "feature_config": cfg,
    }
    joblib.dump(payload, path, compress=max(0, int(compress_level)))


def main():
    args = parse_args()
    global NGRAM_BUCKETS, NGRAM_MAX_N, MARKOV_LOW_PROB_TH
    NGRAM_BUCKETS = int(args.ngram_buckets)
    NGRAM_MAX_N = int(args.ngram_max_n)
    MARKOV_LOW_PROB_TH = float(args.markov_low_prob_th)

    args.tranco = resolve_existing_path(args.tranco, fallback_dirs=["data/raw"])
    args.dga = resolve_existing_path(args.dga, fallback_dirs=["data/raw"])
    args.eval_benign = resolve_existing_path(args.eval_benign, fallback_dirs=["data/raw"])
    args.load_model = resolve_existing_path(
        args.load_model,
        fallback_dirs=["artifacts/models/active", "artifacts/models/legacy"],
    )

    os.makedirs(args.plots_dir, exist_ok=True)
    output_dir = os.path.dirname(args.output)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    if args.load_model:
        if not os.path.exists(args.load_model):
            raise SystemExit(f"Model file not found: {args.load_model}")
        model, cfg, markov_model = load_model_bundle(args.load_model)
        if cfg.get("ngram_buckets"):
            NGRAM_BUCKETS = int(cfg["ngram_buckets"])
        if cfg.get("ngram_max_n"):
            NGRAM_MAX_N = int(cfg["ngram_max_n"])
        if cfg.get("markov_low_prob_th"):
            MARKOV_LOW_PROB_TH = float(cfg["markov_low_prob_th"])
        if args.eval_benign and args.eval_benign_limit > 0:
            benign_list = list(iter_ranked_domains(args.eval_benign, args.eval_benign_limit))
            fp_rate = save_external_benign_eval(
                model,
                benign_list,
                os.path.join(args.plots_dir, "external_benign_eval.md"),
                args.eval_benign_limit,
                markov_model=markov_model,
            )
            if fp_rate is not None:
                print(f"External benign FPR: {fp_rate:.4%}")
        return

    if not args.tranco or not os.path.exists(args.tranco):
        raise SystemExit(f"Tranco file not found: {args.tranco}")
    if not args.dga or not os.path.exists(args.dga):
        raise SystemExit(f"DGA file not found: {args.dga}")

    rf_max_depth = None if int(args.rf_max_depth) <= 0 else int(args.rf_max_depth)

    benign, malicious = build_dataset(
        args.tranco,
        args.dga,
        args.per_class,
        args.seed,
    )

    d_train, y_train, d_val, y_val, d_test, y_test = split_domains(
        benign,
        malicious,
        args.seed,
        val_ratio=args.val_ratio,
        test_ratio=args.test_ratio,
    )

    model, report, tune_report, X_test, y_test, d_test, markov_model = train_model(
        d_train,
        y_train,
        d_val,
        y_val,
        d_test,
        y_test,
        args.seed,
        args.tune,
        use_markov=args.use_markov,
        markov_alpha=args.markov_alpha,
        rf_n_estimators=args.rf_n_estimators,
        rf_max_depth=rf_max_depth,
        rf_min_samples_leaf=args.rf_min_samples_leaf,
    )

    save_model_bundle(
        args.output,
        model,
        markov_model,
        compress_level=args.model_compress,
        extra_config={
            "val_ratio": float(args.val_ratio),
            "test_ratio": float(args.test_ratio),
            "markov_alpha": float(args.markov_alpha),
            "rf_n_estimators": int(model.get_params().get("n_estimators")),
            "rf_max_depth": model.get_params().get("max_depth"),
            "rf_min_samples_leaf": int(model.get_params().get("min_samples_leaf")),
        },
    )

    used = len(benign) + len(malicious)
    print(f"Samples used: {used} (per class: {used // 2})")
    print(
        f"Split: train={len(y_train)}, val={len(y_val)}, test={len(y_test)} "
        f"(val_ratio={args.val_ratio}, test_ratio={args.test_ratio})"
    )
    print(
        f"RF params: n_estimators={model.get_params().get('n_estimators')}, "
        f"max_depth={model.get_params().get('max_depth')}, "
        f"min_samples_leaf={model.get_params().get('min_samples_leaf')}"
    )
    print(f"Model compress level: {max(0, int(args.model_compress))}")
    if not HAS_MATPLOTLIB:
        print("Warning: matplotlib is not available, plot artifacts will be skipped.")
    print(report)
    if args.use_markov:
        print(
            f"Markov features enabled: alpha={args.markov_alpha}, low_prob_th={MARKOV_LOW_PROB_TH}, dims=4"
        )
    if tune_report:
        print("Tuning selected params:")
        print(model.get_params())
    top_features = save_feature_importance(
        model,
        os.path.join(args.plots_dir, "feature_importance.png"),
        use_markov=args.use_markov,
    )
    roc_auc = save_roc_curve(model, X_test, y_test, os.path.join(args.plots_dir, "roc_curve.png"))
    save_misclassified_examples(
        model,
        X_test,
        y_test,
        d_test,
        os.path.join(args.plots_dir, "misclassified_examples.md"),
        args.misclassified,
    )
    if args.eval_benign and args.eval_benign_limit > 0:
        benign_list = list(iter_ranked_domains(args.eval_benign, args.eval_benign_limit))
        fp_rate = save_external_benign_eval(
            model,
            benign_list,
            os.path.join(args.plots_dir, "external_benign_eval.md"),
            args.eval_benign_limit,
            markov_model=markov_model,
        )
        if fp_rate is not None:
            print(f"External benign FPR: {fp_rate:.4%}")
    if roc_auc is not None:
        print(f"ROC AUC: {roc_auc:.4f}")
    if top_features:
        print("Top 10 features:")
        for name, val in top_features[-10:]:
            print(f"{name}\t{val:.6f}")
    if os.path.exists(args.output):
        size_mb = os.path.getsize(args.output) / 1024 / 1024
        print(f"Model size: {size_mb:.3f} MB")
    print(f"Saved model: {args.output}")


if __name__ == "__main__":
    main()
