"""CLI entry point for ingesting course documents into ChromaDB.

Usage:
    python -m db.ingest                     # ingest ./docs, skip existing
    python -m db.ingest --docs path/to/docs # custom docs folder
    python -m db.ingest --clear             # drop existing collections first
"""
import argparse
import os
import sys

from core.config import config
from core.vector_store import VectorStore
from db.document_processor import DocumentProcessor


def ingest(docs_path: str, clear_existing: bool) -> tuple[int, int]:
    """Ingest all course files from docs_path into ChromaDB.

    Returns (courses_added, chunks_added). Courses already present (by title)
    are skipped unless clear_existing is True.
    """
    if not os.path.exists(docs_path):
        print(f"ERROR: docs folder not found: {docs_path}", file=sys.stderr)
        sys.exit(1)

    processor = DocumentProcessor(config.CHUNK_SIZE, config.CHUNK_OVERLAP)
    store = VectorStore(config.CHROMA_PATH, config.EMBEDDING_MODEL, config.MAX_RESULTS)

    if clear_existing:
        print("Clearing existing collections...")
        store.clear_all_data()

    existing_titles = set(store.get_existing_course_titles())

    courses_added = 0
    chunks_added = 0
    skipped = 0

    for file_name in sorted(os.listdir(docs_path)):
        file_path = os.path.join(docs_path, file_name)
        if not (os.path.isfile(file_path) and file_name.lower().endswith((".pdf", ".docx", ".txt"))):
            continue

        try:
            course, course_chunks = processor.process_course_document(file_path)
        except Exception as e:
            print(f"  error parsing {file_name}: {e}", file=sys.stderr)
            continue

        if not course:
            continue

        if course.title in existing_titles:
            print(f"  skip (exists): {course.title}")
            skipped += 1
            continue

        store.add_course_metadata(course)
        store.add_course_content(course_chunks)
        existing_titles.add(course.title)
        courses_added += 1
        chunks_added += len(course_chunks)
        print(f"  added: {course.title} ({len(course_chunks)} chunks)")

    print(f"\nDone. Added {courses_added} course(s), {chunks_added} chunk(s). Skipped {skipped}.")
    return courses_added, chunks_added


def main():
    parser = argparse.ArgumentParser(description="Ingest course documents into ChromaDB.")
    parser.add_argument("--docs", default="docs", help="Path to docs folder (default: docs)")
    parser.add_argument("--clear", action="store_true", help="Clear existing collections before ingesting")
    args = parser.parse_args()
    ingest(args.docs, args.clear)


if __name__ == "__main__":
    main()
