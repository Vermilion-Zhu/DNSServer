import os

import joblib
import numpy as np

import train_dga_model as fe

# DEFAULT_MODEL_PATH = "dga_model_ng128_n3.pkl"
DEFAULT_MODEL_PATH = "artifacts/models/active/dga_model_light_markov_100k_v2.pkl"
DEFAULT_NGRAM_BUCKETS = 128
DEFAULT_NGRAM_MAX_N = 3

_model = None
_model_path = None
_artifact = None


def _resolve_model_path(model_path):
    """兼容新旧目录结构，优先使用传入路径。"""
    candidates = [model_path]
    if not os.path.isabs(model_path):
        name = os.path.basename(model_path)
        candidates.extend(
            [
                os.path.join("artifacts", "models", "active", name),
                os.path.join("artifacts", "models", "legacy", name),
                name,
            ]
        )

    seen = set()
    ordered = []
    for p in candidates:
        if p in seen:
            continue
        seen.add(p)
        ordered.append(p)

    for p in ordered:
        if os.path.exists(p):
            return p

    raise FileNotFoundError(
        f"Model file not found: {model_path}. Checked: {ordered}"
    )


def _ensure_feature_config(ngram_buckets, ngram_max_n):
    fe.NGRAM_BUCKETS = int(ngram_buckets)
    fe.NGRAM_MAX_N = int(ngram_max_n)


def _align_feature_dim(X, model):
    """对齐特征维度，兼容历史模型缺少 feature_config/markov_model 的场景。"""
    expected = getattr(model, "n_features_in_", None)
    if expected is None:
        return X
    expected = int(expected)
    current = int(X.shape[1])
    if current == expected:
        return X
    if current < expected:
        pad = np.zeros((X.shape[0], expected - current), dtype=X.dtype)
        return np.concatenate([X, pad], axis=1)
    return X[:, :expected]


def load_artifact(model_path=DEFAULT_MODEL_PATH):
    """
    兼容两种模型格式：
    1) 旧格式：直接是 sklearn 模型对象
    2) 新格式：dict，包含 model + feature_config (+ markov_model)
    """
    global _artifact, _model, _model_path
    resolved_model_path = _resolve_model_path(model_path)
    if _artifact is not None and _model_path == resolved_model_path:
        return _artifact

    obj = joblib.load(resolved_model_path)
    if isinstance(obj, dict) and "model" in obj:
        model = obj["model"]
        cfg = obj.get("feature_config", {}) or {}
        artifact = {
            "model": model,
            "markov_model": obj.get("markov_model"),
            "ngram_buckets": int(cfg.get("ngram_buckets", DEFAULT_NGRAM_BUCKETS)),
            "ngram_max_n": int(cfg.get("ngram_max_n", DEFAULT_NGRAM_MAX_N)),
            "use_markov": bool(cfg.get("use_markov", False)),
            "markov_low_prob_th": float(cfg.get("markov_low_prob_th", fe.MARKOV_LOW_PROB_TH)),
        }
    else:
        # 向后兼容旧模型（无配置与 Markov 信息）
        artifact = {
            "model": obj,
            "markov_model": None,
            "ngram_buckets": DEFAULT_NGRAM_BUCKETS,
            "ngram_max_n": DEFAULT_NGRAM_MAX_N,
            "use_markov": False,
            "markov_low_prob_th": fe.MARKOV_LOW_PROB_TH,
        }

    _artifact = artifact
    _model = artifact["model"]
    _model_path = resolved_model_path
    return artifact


def load_model(model_path=DEFAULT_MODEL_PATH):
    return load_artifact(model_path)["model"]


def predict(
    domain,
    threshold=0.7,
    model_path=DEFAULT_MODEL_PATH,
    ngram_buckets=None,
    ngram_max_n=None,
):
    artifact = load_artifact(model_path)
    if ngram_buckets is None:
        ngram_buckets = artifact["ngram_buckets"]
    if ngram_max_n is None:
        ngram_max_n = artifact["ngram_max_n"]

    _ensure_feature_config(ngram_buckets, ngram_max_n)
    fe.MARKOV_LOW_PROB_TH = float(artifact.get("markov_low_prob_th", fe.MARKOV_LOW_PROB_TH))

    model = artifact["model"]
    markov_model = artifact.get("markov_model")
    d = fe.normalize_domain(domain)
    if not d:
        return False, 0.0
    x = np.array([fe.extract_features(d, markov_model=markov_model)], dtype=np.float32)
    x = _align_feature_dim(x, model)
    if hasattr(model, "predict_proba"):
        score = float(model.predict_proba(x)[0, 1])
    else:
        score = float(model.predict(x)[0])
    return score >= float(threshold), score


def predict_many(
    domains,
    threshold=0.7,
    model_path=DEFAULT_MODEL_PATH,
    ngram_buckets=None,
    ngram_max_n=None,
):
    artifact = load_artifact(model_path)
    if ngram_buckets is None:
        ngram_buckets = artifact["ngram_buckets"]
    if ngram_max_n is None:
        ngram_max_n = artifact["ngram_max_n"]

    _ensure_feature_config(ngram_buckets, ngram_max_n)
    fe.MARKOV_LOW_PROB_TH = float(artifact.get("markov_low_prob_th", fe.MARKOV_LOW_PROB_TH))

    model = artifact["model"]
    markov_model = artifact.get("markov_model")
    ngram_buckets = int(ngram_buckets)
    ngram_max_n = int(ngram_max_n)
    dim = 5 + max(0, ngram_max_n - 1) * ngram_buckets + (4 if markov_model else 0)
    zero_feat = [0.0] * dim
    ds = [fe.normalize_domain(d) for d in domains]
    feats = [fe.extract_features(d, markov_model=markov_model) if d else zero_feat for d in ds]
    X = np.array(feats, dtype=np.float32)
    X = _align_feature_dim(X, model)
    if hasattr(model, "predict_proba"):
        scores = model.predict_proba(X)[:, 1].astype(np.float32)
    else:
        scores = model.predict(X).astype(np.float32)
    is_dga = (scores >= float(threshold)).astype(bool).tolist()
    return is_dga, scores.tolist()


def model_info(model_path=DEFAULT_MODEL_PATH):
    artifact = load_artifact(model_path)
    model = artifact["model"]
    n_features = getattr(model, "n_features_in_", None)
    base_dims = 5 + max(0, int(artifact["ngram_max_n"]) - 1) * int(artifact["ngram_buckets"])
    inferred_use_markov = bool(artifact["use_markov"])
    if n_features is not None and int(n_features) == base_dims + 4:
        inferred_use_markov = True
    return {
        "model_path": _model_path,
        "n_features_in": n_features,
        "ngram_buckets": artifact["ngram_buckets"],
        "ngram_max_n": artifact["ngram_max_n"],
        "use_markov": artifact["use_markov"],
        "use_markov_inferred": inferred_use_markov,
        "has_markov_model": artifact.get("markov_model") is not None,
    }
