import json
import threading
import time

from playwright.sync_api import expect


def test_page_loads(mock_page):
    """Page loads with correct title, input, send button, and welcome message."""
    expect(mock_page).to_have_title("Course Materials Assistant")
    expect(mock_page.locator("#chatInput")).to_be_visible()
    expect(mock_page.locator("#sendButton")).to_be_visible()
    welcome = mock_page.locator(".message.assistant.welcome-message")
    expect(welcome).to_be_visible()
    expect(welcome).to_contain_text("Welcome")


def test_course_stats_load(mock_page):
    """Sidebar shows course count and titles after expanding."""
    mock_page.locator(".stats-collapsible summary").click()
    expect(mock_page.locator("#totalCourses")).to_have_text("3")
    titles = mock_page.locator("#courseTitles .course-title-item")
    expect(titles).to_have_count(3)
    expect(titles.nth(0)).to_have_text("Course A")
    expect(titles.nth(1)).to_have_text("Course B")
    expect(titles.nth(2)).to_have_text("Course C")


def test_send_message(mock_page):
    """Sending a message shows user message and assistant response."""
    mock_page.fill("#chatInput", "What courses are available?")
    mock_page.click("#sendButton")

    user_msg = mock_page.locator(".message.user")
    expect(user_msg).to_be_visible()
    expect(user_msg).to_contain_text("What courses are available?")

    assistant_msg = mock_page.locator(".message.assistant:not(.welcome-message)")
    expect(assistant_msg).to_be_visible()
    expect(assistant_msg.locator(".message-content")).to_contain_text(
        "This is a test answer."
    )


def test_loading_state(mock_page):
    """Loading spinner appears and input is disabled while waiting for response."""
    # Override fetch in the browser to add a delay, since Playwright's sync API
    # doesn't support delayed route fulfillment from other threads.
    mock_page.unroute("**/api/query")
    mock_page.evaluate(
        """() => {
        const originalFetch = window.fetch;
        window.fetch = async function(...args) {
            if (typeof args[0] === 'string' && args[0].includes('/api/query')) {
                await new Promise(resolve => setTimeout(resolve, 2000));
                return new Response(JSON.stringify({
                    answer: "Delayed answer.",
                    sources: [],
                    session_id: "test-session-123"
                }), {
                    status: 200,
                    headers: {'Content-Type': 'application/json'}
                });
            }
            return originalFetch.apply(this, args);
        };
    }"""
    )

    mock_page.fill("#chatInput", "test question")
    mock_page.click("#sendButton")

    # Assert loading state
    loading = mock_page.locator("#chatMessages .loading")
    expect(loading).to_be_visible(timeout=3000)
    expect(mock_page.locator("#sendButton")).to_be_disabled()
    expect(mock_page.locator("#chatInput")).to_be_disabled()

    # Assert loading disappears and controls re-enable after response
    expect(loading).not_to_be_visible(timeout=5000)
    expect(mock_page.locator("#sendButton")).to_be_enabled()
    expect(mock_page.locator("#chatInput")).to_be_enabled()


def test_suggested_questions(mock_page):
    """Clicking a suggested question sends it and gets a response."""
    mock_page.locator(".suggested-collapsible summary").click()
    first_suggestion = mock_page.locator(".suggested-item").first
    question_text = first_suggestion.get_attribute("data-question")

    first_suggestion.click()

    user_msg = mock_page.locator(".message.user")
    expect(user_msg).to_be_visible()
    expect(user_msg).to_contain_text(question_text)

    assistant_msg = mock_page.locator(".message.assistant:not(.welcome-message)")
    expect(assistant_msg).to_be_visible()


def test_sources_displayed(mock_page):
    """Sources collapsible shows source list when expanded."""
    mock_page.fill("#chatInput", "test query")
    mock_page.click("#sendButton")

    assistant_msg = mock_page.locator(".message.assistant:not(.welcome-message)")
    expect(assistant_msg).to_be_visible()

    sources = assistant_msg.locator(".sources-collapsible")
    expect(sources).to_be_visible()

    # Expand sources
    sources.locator("summary").click()
    sources_content = sources.locator(".sources-content")
    expect(sources_content).to_contain_text("Source 1")
    expect(sources_content).to_contain_text("Source 2")


def test_error_handling(mock_page):
    """Error message displayed when API returns 500."""
    mock_page.route(
        "**/api/query",
        lambda route: route.fulfill(
            status=500,
            content_type="application/json",
            body='{"detail": "Internal server error"}',
        ),
    )

    mock_page.fill("#chatInput", "test query")
    mock_page.click("#sendButton")

    assistant_msg = mock_page.locator(".message.assistant:not(.welcome-message)")
    expect(assistant_msg).to_be_visible()
    expect(assistant_msg).to_contain_text("Error")


def test_enter_key_sends(mock_page):
    """Pressing Enter in the input sends the message."""
    mock_page.fill("#chatInput", "Enter key test")
    mock_page.press("#chatInput", "Enter")

    user_msg = mock_page.locator(".message.user")
    expect(user_msg).to_be_visible()
    expect(user_msg).to_contain_text("Enter key test")

    assistant_msg = mock_page.locator(".message.assistant:not(.welcome-message)")
    expect(assistant_msg).to_be_visible()


def test_empty_input_no_send(mock_page):
    """Clicking send with empty input does not create a user message."""
    mock_page.click("#sendButton")
    user_messages = mock_page.locator(".message.user")
    expect(user_messages).to_have_count(0)


def test_session_id_persistence(mock_page):
    """Session ID from first response is sent in subsequent requests."""
    captured_requests = []

    def capture_handler(route):
        body = json.loads(route.request.post_data)
        captured_requests.append(body)
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "answer": f"Response {len(captured_requests)}",
                    "sources": [],
                    "session_id": "sess-abc",
                }
            ),
        )

    mock_page.unroute("**/api/query")
    mock_page.route("**/api/query", capture_handler)

    # First message
    mock_page.fill("#chatInput", "first question")
    mock_page.click("#sendButton")
    expect(
        mock_page.locator(".message.assistant:not(.welcome-message)")
    ).to_have_count(1, timeout=5000)

    # Second message
    mock_page.fill("#chatInput", "second question")
    mock_page.click("#sendButton")
    expect(
        mock_page.locator(".message.assistant:not(.welcome-message)")
    ).to_have_count(2, timeout=5000)

    assert len(captured_requests) == 2
    assert captured_requests[0].get("session_id") is None
    assert captured_requests[1].get("session_id") == "sess-abc"
