"""Generate retrieval ground truth by asking Claude to write questions per lesson.

For each lesson in docs/*.txt, calls Claude with ONLY that lesson's text and
asks for 3-5 questions that can be answered from the lesson alone. Writes
records to evals/groundtruth_retrieval.jsonl.
"""
import json
import os
import re
import sys
from pathlib import Path

# Make project root importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from anthropic import Anthropic  # noqa: E402
from core.config import config  # noqa: E402

DOCS_DIR = ROOT / "docs"
OUT_PATH = Path(__file__).resolve().parent / "groundtruth_retrieval.jsonl"

QUESTIONS_PER_LESSON = 4
MIN_LESSON_CHARS = 400  # skip stub lessons

GEN_PROMPT = """You are generating evaluation questions for a retrieval system.

Below is the full text of ONE lesson from a course. Write {n} questions that:
- Can be answered using ONLY this lesson's content (not general knowledge, not other lessons)
- Are specific enough that the correct lesson is clearly the right source
- REPHRASE concepts in your own words; do NOT copy distinctive phrases verbatim from the text
- Cover a mix of styles: factual recall, conceptual understanding, and application
- Are standalone (do not reference "this lesson" or "the video")

Course: {course}
Lesson {lesson_num}: {lesson_title}

--- LESSON TEXT ---
{lesson_text}
--- END LESSON ---

Output ONLY a JSON array of {n} strings, no prose, no markdown fences. Example:
["question one?", "question two?", "question three?", "question four?"]
"""


def parse_course_file(path: Path):
    """Yield (course_title, lesson_number, lesson_title, lesson_text) tuples."""
    text = path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()

    course_title = path.stem
    if lines:
        m = re.match(r"^Course Title:\s*(.+)$", lines[0].strip(), re.IGNORECASE)
        if m:
            course_title = m.group(1).strip()
        elif lines[0].strip():
            course_title = lines[0].strip()

    # Split body on lesson headers
    body = "\n".join(lines)
    # Find all lesson markers with positions
    pattern = re.compile(r"^Lesson\s+(\d+):\s*(.+)$", re.IGNORECASE | re.MULTILINE)
    matches = list(pattern.finditer(body))
    for i, m in enumerate(matches):
        lesson_num = int(m.group(1))
        lesson_title = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        lesson_text = body[start:end].strip()
        # Strip a leading "Lesson Link: ..." line if present
        lesson_text = re.sub(
            r"^Lesson Link:\s*\S+\s*\n?", "", lesson_text, flags=re.IGNORECASE
        ).strip()
        yield course_title, lesson_num, lesson_title, lesson_text


def generate_questions(client: Anthropic, course, lesson_num, lesson_title, lesson_text):
    prompt = GEN_PROMPT.format(
        n=QUESTIONS_PER_LESSON,
        course=course,
        lesson_num=lesson_num,
        lesson_title=lesson_title,
        lesson_text=lesson_text[:8000],  # safety cap
    )
    resp = client.messages.create(
        model=config.ANTHROPIC_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.content[0].text.strip()
    # Strip code fences if any
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
    try:
        questions = json.loads(raw)
    except json.JSONDecodeError:
        print(f"  ! failed to parse JSON for lesson {lesson_num}: {raw[:120]}")
        return []
    return [q for q in questions if isinstance(q, str) and q.strip()]


def main():
    if not config.ANTHROPIC_API_KEY:
        print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    client = Anthropic(api_key=config.ANTHROPIC_API_KEY)

    files = sorted(DOCS_DIR.glob("*.txt"))
    if not files:
        print(f"ERROR: no .txt files in {DOCS_DIR}", file=sys.stderr)
        sys.exit(1)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with OUT_PATH.open("w", encoding="utf-8") as out:
        for f in files:
            print(f"Processing {f.name}")
            for course, lnum, ltitle, ltext in parse_course_file(f):
                if len(ltext) < MIN_LESSON_CHARS:
                    print(f"  skip lesson {lnum} (too short: {len(ltext)} chars)")
                    continue
                print(f"  lesson {lnum}: {ltitle}")
                questions = generate_questions(client, course, lnum, ltitle, ltext)
                for q in questions:
                    record = {
                        "question": q,
                        "course_title": course,
                        "lesson_number": lnum,
                    }
                    out.write(json.dumps(record, ensure_ascii=False) + "\n")
                    written += 1
    print(f"\nWrote {written} records to {OUT_PATH}")


if __name__ == "__main__":
    main()
