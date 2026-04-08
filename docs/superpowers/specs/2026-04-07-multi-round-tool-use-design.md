# 多轮 Tool-Use 设计

**日期**：2026-04-07
**状态**：已批准
**作用域**：`api/ai_generator.py`（+ 小改 `core/config.py`、`api/search_tools.py`）

## 背景

当前 `api/ai_generator.py` 的 tool-use 是**单轮**：Claude 第一次返回 `tool_use` 时，执行工具、把结果塞回去要最终答案，就结束。如果第一次搜索 query 写得不好或结果不理想，模型没有第二次重新搜索的机会，只能拿着烂结果硬答。

## 目标

允许 Claude 在一次用户提问内最多调用工具 **2 轮**（硬上限），让模型可以：
- 看第一次搜索结果后改写 query 再搜一次
- 先查课程大纲再查具体 lesson 这类两步场景

保持 `ToolManager` 和 `search_tools.py` 的接口不变——多轮是调用层的事，工具层无感。

## 设计

### 循环结构

把当前"初始请求 → if tool_use → 执行 → 第二次请求 → 返回"的线性流程，替换为 `while` 循环：

```python
MAX_TOOL_ROUNDS = config.MAX_TOOL_ROUNDS  # = 2

messages = [{"role": "user", "content": query}]
for _ in range(MAX_TOOL_ROUNDS):
    response = client.messages.create(messages=messages, tools=tools, ...)
    if response.stop_reason != "tool_use":
        return extract_text(response)
    # 执行所有 tool_use block
    messages.append({"role": "assistant", "content": response.content})
    messages.append({"role": "user", "content": run_tools(response, tool_manager)})

# 耗尽兜底：最后再调一次，不带 tools，强制 Claude 出文本
final = client.messages.create(messages=messages, tools=None, ...)
return extract_text(final)
```

### 关键点

1. **硬上限 `MAX_TOOL_ROUNDS = 2`** 放到 `core/config.py`，方便以后调。
2. **每轮都传 `tools`**（除了兜底那次），让模型每轮都有"继续搜"或"直接答"的选择。
3. **耗尽兜底**：循环跑完 2 轮还在 `tool_use`，再发一次**不带 tools** 的请求，强制 Claude 出文本——避免无限循环、也避免返回空。
4. **`ToolManager` / `search_tools.py` 不动**。

### Sources 累积

当前 `CourseSearchTool` 在每次 `execute()` 调用时把 sources 存在实例属性上，多轮会**覆盖**前一轮的 sources。改成**追加**，这样最终答案能引用所有轮次搜过的来源。

- 追加到 `self.last_sources` 列表
- 去重按 `(course, lesson, chunk_index)` 三元组
- `RAGSystem.query()` 在调完 `generate_response()` 后读取 + 清空 `last_sources`，逻辑不变

## 验收

### Evals 回归（sanity gate）

`uv run python evals/run_retrieval_eval.py` 前后对比。

**注意**：retrieval eval 只测 `VectorStore.search()`，不测 `ai_generator`，所以这个 eval 对本改动**不敏感**——分数应该基本不变。它只起"没搞坏底层"的 sanity 作用。

### 手工 A/B（真正的质量信号）

挑几个当前答得不好的 query，在 N=1 和 N=2 下各跑一次，对比答案质量。由开发者手动评估。

### 无自动化单元测试

项目本来就没有单元测试框架，evals 是唯一的回归 gate。

## 风险 & 成本

- **API 调用次数**：最坏 1→3（2 轮 tool + 1 轮兜底）。大部分 query 仍然是 1–2 次。
- **延迟**：相应增加。
- **Sources 重复**：通过三元组去重缓解。
- **回滚**：`git revert` 即可。

## 不在范围内

- 工具层改动（`search_tools.py` 接口、ChromaDB 查询逻辑）
- 自动化 answer-quality eval（留给未来）
- 把 `MAX_TOOL_ROUNDS` 暴露给前端/API
