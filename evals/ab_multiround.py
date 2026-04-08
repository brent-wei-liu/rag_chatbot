"""Quick A/B: run the same queries with MAX_TOOL_ROUNDS=1 vs =2 and print
both answers side-by-side so a human can judge.

Usage:
    uv run python evals/ab_multiround.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.config import config  # noqa: E402
from api.rag_system import RAGSystem  # noqa: E402

QUERIES = [
    # Vague — the model probably has to search once, realize it's underspecified,
    # then search again with a better query
    "那门讲 compression 的课里，那个需要一个额外小模型的技术叫什么？",
    # Outline-then-content two-step: need to resolve "lesson 5" to actual content
    "MCP 课程的 lesson 5 具体讲了什么？给三个要点。",
    # Cross-course attribution: "which course first introduced X" — naturally two searches
    "HyDE 这个技术在哪门课里讲过？具体是哪一节？",
    # Empty/negative — first search will find nothing relevant, model should try again
    "Anthropic 的 computer use 课里关于 vision transformer 的内容",
]


def run_with_rounds(queries: list[str], max_rounds: int) -> list[tuple[str, list]]:
    config.MAX_TOOL_ROUNDS = max_rounds
    rag = RAGSystem(config)
    results = []
    for q in queries:
        answer, sources = rag.query(q)
        results.append((answer, sources))
    return results


def main():
    print(f"# A/B: MAX_TOOL_ROUNDS = 1 vs 2\n")
    print(f"Running {len(QUERIES)} queries at N=1...")
    n1 = run_with_rounds(QUERIES, 1)
    print(f"Running {len(QUERIES)} queries at N=2...")
    n2 = run_with_rounds(QUERIES, 2)

    for i, q in enumerate(QUERIES):
        print("\n" + "=" * 80)
        print(f"Q{i + 1}: {q}")
        print("=" * 80)

        a1, s1 = n1[i]
        a2, s2 = n2[i]

        print(f"\n--- N=1 ({len(s1)} source{'s' if len(s1) != 1 else ''}) ---")
        print(a1)
        if s1:
            print("\nSources:")
            for s in s1:
                label = s["label"] if isinstance(s, dict) else s
                print(f"  - {label}")

        print(f"\n--- N=2 ({len(s2)} source{'s' if len(s2) != 1 else ''}) ---")
        print(a2)
        if s2:
            print("\nSources:")
            for s in s2:
                label = s["label"] if isinstance(s, dict) else s
                print(f"  - {label}")


if __name__ == "__main__":
    main()
