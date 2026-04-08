"""Run retrieval evaluation against the existing ChromaDB store.

For each ground truth record, calls VectorStore.search(question) WITHOUT
filters and computes Recall@1/3/5 + MRR by checking whether any returned
chunk's metadata matches (course_title, lesson_number).
"""
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.config import config  # noqa: E402
from core.vector_store import VectorStore  # noqa: E402

GT_PATH = Path(__file__).resolve().parent / "groundtruth_retrieval.jsonl"
BASELINE_DIR = Path(__file__).resolve().parent / "baselines"
KS = (1, 3, 5)
TOP_K = max(KS)


def load_groundtruth():
    records = []
    with GT_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def hit_rank(results, expected_course, expected_lesson):
    """Return 1-based rank of first matching chunk, or None."""
    for i, meta in enumerate(results.metadata):
        if (
            meta.get("course_title") == expected_course
            and meta.get("lesson_number") == expected_lesson
        ):
            return i + 1
    return None


def main():
    records = load_groundtruth()
    if not records:
        print(f"ERROR: no records in {GT_PATH}", file=sys.stderr)
        sys.exit(1)

    # CHROMA_PATH is relative to project root
    chroma_path = str(ROOT / config.CHROMA_PATH.lstrip("./"))
    store = VectorStore(
        chroma_path=chroma_path,
        embedding_model=config.EMBEDDING_MODEL,
        max_results=TOP_K,
    )

    total = 0
    recall_hits = {k: 0 for k in KS}
    rr_sum = 0.0
    by_course = defaultdict(lambda: {"total": 0, **{f"r@{k}": 0 for k in KS}, "rr": 0.0})
    misses = []

    for rec in records:
        q = rec["question"]
        course = rec["course_title"]
        lesson = rec["lesson_number"]
        results = store.search(q, limit=TOP_K)
        if results.error:
            print(f"  search error: {results.error}")
            continue

        rank = hit_rank(results, course, lesson)
        total += 1
        by_course[course]["total"] += 1

        if rank is not None:
            rr_sum += 1.0 / rank
            by_course[course]["rr"] += 1.0 / rank
            for k in KS:
                if rank <= k:
                    recall_hits[k] += 1
                    by_course[course][f"r@{k}"] += 1
        else:
            misses.append({"question": q, "expected": f"{course} L{lesson}"})

    if total == 0:
        print("ERROR: zero queries evaluated", file=sys.stderr)
        sys.exit(1)

    metrics = {
        "n": total,
        "mrr": round(rr_sum / total, 4),
        **{f"recall@{k}": round(recall_hits[k] / total, 4) for k in KS},
    }

    by_course_out = {}
    for course, d in by_course.items():
        n = d["total"]
        by_course_out[course] = {
            "n": n,
            "mrr": round(d["rr"] / n, 4),
            **{f"recall@{k}": round(d[f"r@{k}"] / n, 4) for k in KS},
        }

    report = {
        "date": date.today().isoformat(),
        "config": {
            "CHUNK_SIZE": config.CHUNK_SIZE,
            "CHUNK_OVERLAP": config.CHUNK_OVERLAP,
            "MAX_RESULTS": config.MAX_RESULTS,
            "EMBEDDING_MODEL": config.EMBEDDING_MODEL,
            "TOP_K_EVAL": TOP_K,
        },
        "overall": metrics,
        "by_course": by_course_out,
        "miss_count": len(misses),
        "sample_misses": misses[:10],
    }

    print(json.dumps(report, indent=2, ensure_ascii=False))

    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = BASELINE_DIR / f"{date.today().isoformat()}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote baseline to {out_path}")


if __name__ == "__main__":
    main()
