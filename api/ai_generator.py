import anthropic
from core.config import config
from typing import List, Optional, Dict, Any

class AIGenerator:
    """Handles interactions with Anthropic's Claude API for generating responses"""
    
    # Static system prompt to avoid rebuilding on each call
    SYSTEM_PROMPT = """ You are an AI assistant specialized in course materials and educational content with access to tools for course information.

Available Tools:
1. **search_course_content** — Search course materials for specific content or detailed educational information.
2. **get_course_outline** — Get a course's full outline: title, course link, and complete lesson list (number and title for each lesson). Use this for questions about course structure, outlines, what lessons a course contains, or what a course covers at a high level.

Tool Usage:
- **One tool call per query maximum**
- For outline/structure questions (e.g. "What is the outline of X?", "What lessons does X have?"): use **get_course_outline** and present the result exactly as a bullet list. Do NOT use tables. Format each lesson as a bullet point like `- Lesson N: Title`
- For content/detail questions: use **search_course_content**
- Synthesize tool results into accurate, fact-based responses
- If a tool yields no results, state this clearly without offering alternatives

Response Protocol:
- **General knowledge questions**: Answer using existing knowledge without searching
- **Course-specific questions**: Use the appropriate tool first, then answer
- **No meta-commentary**:
 - Provide direct answers only — no reasoning process, search explanations, or question-type analysis
 - Do not mention "based on the search results" or "based on the tool results"

All responses must be:
1. **Brief, Concise and focused** - Get to the point quickly
2. **Educational** - Maintain instructional value
3. **Clear** - Use accessible language
4. **Example-supported** - Include relevant examples when they aid understanding
Provide only the direct answer to what was asked.
"""
    
    def __init__(self, api_key: str, model: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        
        # Pre-build base API parameters
        self.base_params = {
            "model": self.model,
            "temperature": 0.3,
            "max_tokens": 800
        }
    
    def generate_response(self, query: str,
                         conversation_history: Optional[str] = None,
                         tools: Optional[List] = None,
                         tool_manager=None) -> str:
        """
        Generate AI response with optional multi-round tool usage.

        Runs up to config.MAX_TOOL_ROUNDS rounds of tool calls. If the model
        still wants to call tools after the last round, a final request is
        sent WITHOUT tools to force a text answer.
        """
        system_content = (
            f"{self.SYSTEM_PROMPT}\n\nPrevious conversation:\n{conversation_history}"
            if conversation_history
            else self.SYSTEM_PROMPT
        )

        messages: List[Dict[str, Any]] = [{"role": "user", "content": query}]

        # Tool-use loop: up to MAX_TOOL_ROUNDS rounds where the model is allowed
        # to call tools.
        for _ in range(config.MAX_TOOL_ROUNDS):
            api_params = {
                **self.base_params,
                "messages": messages,
                "system": system_content,
            }
            if tools and tool_manager:
                api_params["tools"] = tools
                api_params["tool_choice"] = {"type": "auto"}

            response = self.client.messages.create(**api_params)

            if response.stop_reason != "tool_use" or not tool_manager:
                return self._extract_text(response)

            # Append assistant's tool_use turn, execute tools, append results.
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = tool_manager.execute_tool(block.name, **block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
            messages.append({"role": "user", "content": tool_results})

        # Exhaustion fallback: budget used up but model still wants tools.
        # Call once more WITHOUT tools to force a text answer.
        final = self.client.messages.create(
            **self.base_params,
            messages=messages,
            system=system_content,
        )
        return self._extract_text(final)

    @staticmethod
    def _extract_text(response) -> str:
        """Return the first text block from a Claude response, or empty string."""
        for block in response.content:
            if getattr(block, "type", None) == "text":
                return block.text
        return ""