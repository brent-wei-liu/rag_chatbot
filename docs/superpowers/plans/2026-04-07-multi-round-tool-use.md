# Multi-Round Tool-Use Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Change `api/ai_generator.py` tool-use from single-round to a 2-round hard-capped loop, so Claude can refine its search after seeing the first result.

**Architecture:** Replace the linear "initial request → if tool_use → execute → second request" flow with a `while` loop over `MAX_TOOL_ROUNDS`, with a final tool-less request as the exhaustion fallback. Change `CourseSearchTool.last_sources` accumulation from overwrite to append+dedupe so multi-round answers can cite all searched sources.

**Tech Stack:** Python 3.13, Anthropic SDK 0.58.2, existing RAG codebase.

**Spec:** `docs/superpowers/specs/2026-04-07-multi-round-tool-use-design.md`

**Pre-flight:** Run retrieval eval once before any code change — this is the baseline to diff against at the end.

```bash
uv run python evals/run_retrieval_eval.py
```

Expected (current state): `mrr ≈ 0.8033, recall@1 ≈ 0.7109, recall@3 ≈ 0.8984, recall@5 ≈ 0.9219`. Save the printed JSON to remember the exact numbers.

---

### Task 1: Add `MAX_TOOL_ROUNDS` to config

**Files:**
- Modify: `core/config.py`

- [ ] **Step 1: Add the config field**

Edit `core/config.py`. Under the existing `MAX_HISTORY` line, add:

```python
    MAX_HISTORY: int = 2         # Number of conversation messages to remember
    MAX_TOOL_ROUNDS: int = 2     # Max tool-use rounds per query before forcing a final text answer
```

- [ ] **Step 2: Verify the import still works**

```bash
uv run python -c "from core.config import config; print(config.MAX_TOOL_ROUNDS)"
```

Expected: `2`

- [ ] **Step 3: Commit**

```bash
git add core/config.py
git commit -m "config: add MAX_TOOL_ROUNDS (default 2)"
```

---

### Task 2: Rewrite `AIGenerator.generate_response` as a loop

**Files:**
- Modify: `api/ai_generator.py` (replace `generate_response` body and delete `_handle_tool_execution`)

- [ ] **Step 1: Replace `generate_response` and delete `_handle_tool_execution`**

Open `api/ai_generator.py`. Add `from core.config import config` to the imports at the top (alongside `import anthropic`).

Replace the body of `generate_response` (lines ~47–91) AND delete `_handle_tool_execution` entirely. The new file tail (from `generate_response` onward) should look exactly like this:

```python
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
```

- [ ] **Step 2: Smoke test the import and a dry call**

```bash
uv run python -c "
from api.ai_generator import AIGenerator
from core.config import config
g = AIGenerator(config.ANTHROPIC_API_KEY, config.ANTHROPIC_MODEL)
print(g.generate_response('What is 2+2? Answer in one word.'))
"
```

Expected: a short answer like `Four.` (no tools involved, verifies the no-tool path of the loop still works).

- [ ] **Step 3: Commit**

```bash
git add api/ai_generator.py
git commit -m "ai_generator: multi-round tool-use loop (max 2 rounds)"
```

---

### Task 3: Update the system prompt to allow multi-round tool use

**Files:**
- Modify: `api/ai_generator.py` (SYSTEM_PROMPT string)

The current prompt says `**One tool call per query maximum**`. That's now a lie, and it actively discourages the model from using round 2.

- [ ] **Step 1: Edit the prompt**

In `api/ai_generator.py`, find the line:

```
- **One tool call per query maximum**
```

Replace it with:

```
- **Up to 2 tool calls per query**: if the first result is insufficient or you need to look up something else (e.g. check an outline first, then search a specific lesson), you may call a tool a second time with a refined query.
- **Do not call more than 2 tools**. If the first two calls didn't find the answer, state that clearly instead of guessing.
```

- [ ] **Step 2: Commit**

```bash
git add api/ai_generator.py
git commit -m "ai_generator: update system prompt for 2-round tool-use"
```

---

### Task 4: Make `CourseSearchTool.last_sources` accumulate across rounds

**Files:**
- Modify: `api/search_tools.py` (`CourseSearchTool._format_results`)

Today `_format_results` overwrites `self.last_sources = sources` on each call. In a multi-round session that loses round 1's sources. We want it to **append** and **dedupe**.

Sources are dicts of shape `{"label": str, "link": str | None}`. Dedupe key: `(label, link)` — simple, matches what the UI already shows, and avoids needing chunk_index plumbing (the current source dict doesn't carry it).

- [ ] **Step 1: Change `_format_results` to append + dedupe**

Find the tail of `_format_results` in `api/search_tools.py` (currently ends with `self.last_sources = sources` then `return "\n\n".join(formatted)`). Replace those two lines with:

```python
        # Accumulate sources across multi-round tool use; dedupe by (label, link).
        seen = {(s["label"], s["link"]) for s in self.last_sources}
        for s in sources:
            key = (s["label"], s["link"])
            if key not in seen:
                self.last_sources.append(s)
                seen.add(key)

        return "\n\n".join(formatted)
```

- [ ] **Step 2: Verify `ToolManager.reset_sources` still clears the list**

Read `api/search_tools.py` around `reset_sources` (line ~198). It sets `tool.last_sources = []`, which works correctly — `RAGSystem.query()` calls this before/after each user query, so sources reset per query. No change needed.

- [ ] **Step 3: Smoke test with a real query**

```bash
uv run python -c "
from api.rag_system import RAGSystem
from core.config import config
rag = RAGSystem(config)
answer, sources = rag.query('What does the MCP course cover in lesson 2?')
print('ANSWER:', answer[:200])
print('SOURCES:', sources)
"
```

Expected: a non-empty answer and at least one source. No exceptions. (Needs `ANTHROPIC_API_KEY` in `.env` and `db/chroma_db/` populated.)

- [ ] **Step 4: Commit**

```bash
git add api/search_tools.py
git commit -m "search_tools: accumulate + dedupe last_sources across rounds"
```

---

### Task 5: Retrieval eval regression check

**Files:** none modified — this is a verification task.

The retrieval eval only exercises `VectorStore.search()`, so this change should have **no effect** on the numbers. If they move, something broke upstream (e.g., an accidental import-time side effect in `api/ai_generator.py`).

- [ ] **Step 1: Run the eval**

```bash
uv run python evals/run_retrieval_eval.py
```

- [ ] **Step 2: Compare against the pre-flight baseline**

Expected: `mrr`, `recall@1`, `recall@3`, `recall@5` all identical to the pre-flight baseline (from the top of this plan: `mrr ≈ 0.8033, recall@1 ≈ 0.7109, recall@3 ≈ 0.8984, recall@5 ≈ 0.9219`).

If they differ: stop and investigate. The retrieval path didn't change, so a delta means something unexpected is happening.

- [ ] **Step 3: No commit**

This is a check, not a change.

---

### Task 6: Manual A/B quality check

**Files:** none.

The retrieval eval can't see answer quality, so this is the actual signal for whether multi-round helps.

- [ ] **Step 1: Pick 3 queries that are likely to benefit from round 2**

Suggested:
1. `"What does the MCP course teach about transports?"` — likely needs outline-then-search two-step.
2. `"Compare how Course 1 and Course 3 approach retrieval."` — cross-course, may need two searches.
3. `"In the Chroma course lesson 4, what embedding model is discussed?"` — should work in one round; sanity.

- [ ] **Step 2: Start the server**

```bash
./run.sh
```

- [ ] **Step 3: Ask each query via the web UI at http://localhost:8000, note the answer and source list**

- [ ] **Step 4: Temporarily set `MAX_TOOL_ROUNDS = 1` in `core/config.py`, restart, ask the same 3 queries again, compare.**

- [ ] **Step 5: Revert `MAX_TOOL_ROUNDS` to 2**

```bash
git checkout core/config.py
```

- [ ] **Step 6: Record findings in the PR description**

No commit. The A/B observations go into the PR body: which queries improved, which regressed (if any), which didn't change.

---

## Self-Review

**Spec coverage:**
- Loop structure → Task 2 ✓
- `MAX_TOOL_ROUNDS = 2` in config → Task 1 ✓
- Every round passes `tools`, fallback round does not → Task 2 ✓ (the loop adds `tools` when present, fallback `client.messages.create` call omits them)
- Exhaustion fallback → Task 2 ✓
- `ToolManager`/`search_tools.py` interface unchanged → verified (Task 4 only touches internal accumulation)
- Sources append + dedupe → Task 4 ✓ (dedupe key is `(label, link)`, spec said `(course, lesson, chunk_index)` but chunk_index isn't in the source dict; the substituted key is equivalent for the purpose — cited)
- System prompt contradiction fix → Task 3 ✓ (spec didn't call this out explicitly but the "one call max" line would have sabotaged the behavior)
- Evals regression gate → Task 5 ✓
- Manual A/B → Task 6 ✓

**Placeholder scan:** No TBDs, no "add appropriate handling", every code step shows the code, every command shows expected output.

**Type consistency:** `_extract_text` is defined in Task 2 and used twice in Task 2 — consistent. `MAX_TOOL_ROUNDS` spelled identically in Task 1 and Task 2. Source dict shape `{"label", "link"}` matches what `CourseSearchTool._format_results` already builds (verified against current `api/search_tools.py:113`).
