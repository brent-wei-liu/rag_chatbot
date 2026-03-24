import json
import functools
import http.server
import threading
import time
from pathlib import Path

import pytest

FRONTEND_DIR = str(Path(__file__).parent.parent / "frontend")
SERVER_PORT = 8765


@pytest.fixture(scope="session")
def server_url():
    """Start a static file server for the frontend."""
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler,
        directory=FRONTEND_DIR,
    )
    httpd = http.server.HTTPServer(("127.0.0.1", SERVER_PORT), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.3)
    yield f"http://127.0.0.1:{SERVER_PORT}"
    httpd.shutdown()


@pytest.fixture()
def mock_page(page, server_url):
    """Page with default API mocks configured before navigation."""
    # Set up route mocks BEFORE navigating (loadCourseStats fires on DOMContentLoaded)
    page.route(
        "**/api/courses",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "total_courses": 3,
                    "course_titles": ["Course A", "Course B", "Course C"],
                }
            ),
        ),
    )
    page.route(
        "**/api/query",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "answer": "This is a test answer.",
                    "sources": ["Source 1", "Source 2"],
                    "session_id": "test-session-123",
                }
            ),
        ),
    )
    page.goto(server_url)
    page.wait_for_load_state("networkidle")
    yield page
