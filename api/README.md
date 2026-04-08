# api/

课程资料 RAG 聊天机器人的 FastAPI 服务。处理来自前端的 HTTP 请求，调用 Claude 的 tool-use 回答问题，从 `db/` 填充的 ChromaDB 向量库中读取数据。

本模块对向量库**只读**——它不做任何文档摄取。摄取是独立的离线步骤（`python -m db.ingest`）。

## 运行

在项目根目录下：

```bash
uv run uvicorn api.app:app --reload --port 8000
```

或使用先摄取再启动的封装脚本：

```bash
./run.sh
```

打开 http://localhost:8000 （Web 界面）或 http://localhost:8000/docs （OpenAPI）。

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/query` | 回答一个问题。Body：`{query, session_id?}`。返回 `{answer, sources, session_id}`。 |
| `POST` | `/api/new-session` | 创建一个新的会话。 |
| `GET`  | `/api/courses` | 课程目录统计：`{total_courses, course_titles}`。 |

## 文件

- `app.py` — FastAPI 入口。定义接口、把 `frontend/` 挂载为静态文件、实例化全局 `RAGSystem`。
- `rag_system.py` — 编排器。`query()` 构建 prompt、取会话历史、带工具调用 AI、收集来源、更新会话。
- `ai_generator.py` — Anthropic Claude 客户端。实现单轮 tool-use 循环：初次请求 → 若 Claude 调用工具，则通过 `ToolManager` 执行 → 把结果回传换取最终回答。
- `search_tools.py` — 工具抽象层。`Tool` 抽象基类、`CourseSearchTool` 与 `CourseOutlineTool`（都封装 `core.vector_store`）、负责注册与分发的 `ToolManager`。
- `session_manager.py` — 内存中按 session 存对话历史。历史以格式化文本注入 system prompt，而非作为 message history。

## 依赖

- `core/` — `VectorStore`、`Config`、Pydantic 模型
- `db/chroma_db/` — 由 `db/ingest.py` 填充；本模块只读
- 环境变量：项目根目录 `.env` 中的 `ANTHROPIC_API_KEY`
