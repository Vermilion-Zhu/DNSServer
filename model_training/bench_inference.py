import argparse
import time
import zipfile
import io

import dga_runtime
import train_dga_model as fe


def iter_ranked_csv_in_zip(zip_path, limit):
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = [n for n in zf.namelist() if n.endswith(".csv")]
        if not names:
            return
        with zf.open(names[0]) as fh:
            wrapper = io.TextIOWrapper(fh, encoding="utf-8", errors="ignore")
            count = 0
            for line in wrapper:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(",")
                if len(parts) < 2:
                    continue
                domain = fe.normalize_domain(parts[1])
                if not domain:
                    continue
                yield domain
                count += 1
                if count >= limit:
                    return


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    p.add_argument("--zip", default="data/raw/archive.zip")
    p.add_argument("--n", type=int, default=200000)
    p.add_argument("--warmup", type=int, default=5000)
    p.add_argument("--batch", type=int, default=2048)
    p.add_argument("--threshold", type=float, default=0.7)
    return p.parse_args()


def main():
    args = parse_args()
    info = dga_runtime.model_info(args.model)

    domains = list(iter_ranked_csv_in_zip(args.zip, args.n))
    if not domains:
        raise SystemExit("No domains loaded for benchmark")

    warm_n = min(args.warmup, len(domains))
    if warm_n > 0:
        dga_runtime.predict_many(
            domains[:warm_n],
            threshold=args.threshold,
            model_path=args.model,
        )

    start = time.perf_counter()
    total = 0
    for i in range(0, len(domains), args.batch):
        batch = domains[i : i + args.batch]
        dga_runtime.predict_many(
            batch,
            threshold=args.threshold,
            model_path=args.model,
        )
        total += min(args.batch, len(domains) - i)
    end = time.perf_counter()

    elapsed = end - start
    qps = total / elapsed if elapsed > 0 else 0.0
    avg_ms = (elapsed / total) * 1000 if total > 0 else 0.0

    print(f"Model: {args.model}")
    print(
        "Model info: "
        f"n_features_in={info.get('n_features_in')}, "
        f"ngram_buckets={info.get('ngram_buckets')}, "
        f"ngram_max_n={info.get('ngram_max_n')}, "
        f"use_markov={info.get('use_markov')}, "
        f"has_markov_model={info.get('has_markov_model')}"
    )
    print(f"Samples: {total}")
    print(f"Batch size: {args.batch}")
    print(f"Elapsed: {elapsed:.4f}s")
    print(f"Avg per query: {avg_ms:.6f} ms")
    print(f"Throughput: {qps:.2f} queries/s")


if __name__ == "__main__":
    main()
