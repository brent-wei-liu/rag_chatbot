import os
import re
from typing import List, Tuple
from core.models import Course, Lesson, CourseChunk

class DocumentProcessor:
    """Processes course documents and extracts structured information"""
    
    def __init__(self, chunk_size: int, chunk_overlap: int):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
    
    def read_file(self, file_path: str) -> str:
        """Read content from file with UTF-8 encoding"""
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                return file.read()
        except UnicodeDecodeError:
            # If UTF-8 fails, try with error handling
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
                return file.read()
    


    def chunk_text(self, text: str) -> List[str]:
        """Split text into sentence-based chunks with overlap using config settings"""
        
        # Clean up the text
        text = re.sub(r'\s+', ' ', text.strip())  # Normalize whitespace
        
        # Better sentence splitting that handles abbreviations
        # This regex looks for periods followed by whitespace and capital letters
        # but ignores common abbreviations
        sentence_endings = re.compile(r'(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\!|\?)\s+(?=[A-Z])')
        sentences = sentence_endings.split(text)
        
        # Clean sentences
        sentences = [s.strip() for s in sentences if s.strip()]
        
        chunks = []
        i = 0
        
        while i < len(sentences):
            current_chunk = []
            current_size = 0
            
            # Build chunk starting from sentence i
            for j in range(i, len(sentences)):
                sentence = sentences[j]
                
                # Calculate size with space
                space_size = 1 if current_chunk else 0
                total_addition = len(sentence) + space_size
                
                # Check if adding this sentence would exceed chunk size
                if current_size + total_addition > self.chunk_size and current_chunk:
                    break
                
                current_chunk.append(sentence)
                current_size += total_addition
            
            # Add chunk if we have content
            if current_chunk:
                chunks.append(' '.join(current_chunk))
                
                # Calculate overlap for next chunk
                if self.chunk_overlap > 0:
                    # Find how many sentences to overlap
                    overlap_size = 0
                    overlap_sentences = 0
                    
                    # Count backwards from end of current chunk
                    for k in range(len(current_chunk) - 1, -1, -1):
                        sentence_len = len(current_chunk[k]) + (1 if k < len(current_chunk) - 1 else 0)
                        if overlap_size + sentence_len <= self.chunk_overlap:
                            overlap_size += sentence_len
                            overlap_sentences += 1
                        else:
                            break
                    
                    # Move start position considering overlap
                    next_start = i + len(current_chunk) - overlap_sentences
                    i = max(next_start, i + 1)  # Ensure we make progress
                else:
                    # No overlap - move to next sentence after current chunk
                    i += len(current_chunk)
            else:
                # No sentences fit, move to next
                i += 1
        
        return chunks




    
    # Regexes used by the document parser
    _COURSE_TITLE_RE = re.compile(r'^Course Title:\s*(.+)$', re.IGNORECASE)
    _COURSE_LINK_RE = re.compile(r'^Course Link:\s*(.+)$', re.IGNORECASE)
    _INSTRUCTOR_RE = re.compile(r'^Course Instructor:\s*(.+)$', re.IGNORECASE)
    _LESSON_RE = re.compile(r'^Lesson\s+(\d+):\s*(.+)$', re.IGNORECASE)
    _LESSON_LINK_RE = re.compile(r'^Lesson Link:\s*(.+)$', re.IGNORECASE)

    def _parse_course_header(self, lines: List[str], filename: str) -> Tuple[Course, int]:
        """Parse the course metadata header.

        Returns the Course object and the line index where the lesson body starts.
        """
        course_title = filename  # fallback
        course_link = None
        instructor = None

        if lines and lines[0].strip():
            m = self._COURSE_TITLE_RE.match(lines[0].strip())
            course_title = m.group(1).strip() if m else lines[0].strip()

        for line in (l.strip() for l in lines[1:4]):
            if not line:
                continue
            if m := self._COURSE_LINK_RE.match(line):
                course_link = m.group(1).strip()
            elif m := self._INSTRUCTOR_RE.match(line):
                instructor = m.group(1).strip()

        course = Course(title=course_title, course_link=course_link, instructor=instructor)

        # Body starts after metadata; skip the blank line after the instructor if present
        body_start = 4 if len(lines) > 3 and not lines[3].strip() else 3
        return course, body_start

    def _emit_lesson_chunks(
        self,
        course: Course,
        lesson_number: int,
        lesson_title: str,
        lesson_link: str,
        lesson_lines: List[str],
        chunk_counter: int,
    ) -> Tuple[List[CourseChunk], int]:
        """Build CourseChunks for a single lesson and append the Lesson to the course.

        Returns the list of new chunks and the updated chunk counter.
        """
        lesson_text = '\n'.join(lesson_lines).strip()
        if not lesson_text:
            return [], chunk_counter

        course.lessons.append(Lesson(
            lesson_number=lesson_number,
            title=lesson_title,
            lesson_link=lesson_link,
        ))

        chunks: List[CourseChunk] = []
        for chunk in self.chunk_text(lesson_text):
            content = f"Course {course.title} Lesson {lesson_number} content: {chunk}"
            chunks.append(CourseChunk(
                content=content,
                course_title=course.title,
                lesson_number=lesson_number,
                chunk_index=chunk_counter,
            ))
            chunk_counter += 1

        return chunks, chunk_counter

    def process_course_document(self, file_path: str) -> Tuple[Course, List[CourseChunk]]:
        """
        Process a course document with expected format:
        Line 1: Course Title: [title]
        Line 2: Course Link: [url]
        Line 3: Course Instructor: [instructor]
        Following lines: Lesson markers and content
        """
        content = self.read_file(file_path)
        lines = content.strip().split('\n')

        course, body_start = self._parse_course_header(lines, os.path.basename(file_path))

        course_chunks: List[CourseChunk] = []
        chunk_counter = 0

        current_lesson: int | None = None
        lesson_title: str | None = None
        lesson_link: str | None = None
        lesson_content: List[str] = []

        i = body_start
        while i < len(lines):
            line = lines[i]
            lesson_match = self._LESSON_RE.match(line.strip())

            if lesson_match:
                # Flush the previous lesson, if any
                if current_lesson is not None:
                    new_chunks, chunk_counter = self._emit_lesson_chunks(
                        course, current_lesson, lesson_title, lesson_link,
                        lesson_content, chunk_counter,
                    )
                    course_chunks.extend(new_chunks)

                # Start a new lesson
                current_lesson = int(lesson_match.group(1))
                lesson_title = lesson_match.group(2).strip()
                lesson_link = None
                lesson_content = []

                # Optional "Lesson Link:" on the next line — consume it so it doesn't
                # leak into the lesson body
                if i + 1 < len(lines):
                    if m := self._LESSON_LINK_RE.match(lines[i + 1].strip()):
                        lesson_link = m.group(1).strip()
                        i += 1
            else:
                lesson_content.append(line)

            i += 1

        # Flush the final lesson
        if current_lesson is not None:
            new_chunks, chunk_counter = self._emit_lesson_chunks(
                course, current_lesson, lesson_title, lesson_link,
                lesson_content, chunk_counter,
            )
            course_chunks.extend(new_chunks)

        # Fallback: no lesson markers found — treat the whole body as one untagged blob
        if not course_chunks and len(lines) > 2:
            remaining = '\n'.join(lines[body_start:]).strip()
            if remaining:
                for chunk in self.chunk_text(remaining):
                    course_chunks.append(CourseChunk(
                        content=chunk,
                        course_title=course.title,
                        chunk_index=chunk_counter,
                    ))
                    chunk_counter += 1

        return course, course_chunks
