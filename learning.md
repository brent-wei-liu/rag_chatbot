# 课程材料 RAG 聊天机器人 — 学习文档

## 项目概览

这是一个课程材料 RAG（Retrieval-Augmented Generation）聊天机器人，用户通过网页界面提问，系统从课程文档中检索相关内容，再用 Claude AI 生成回答。

### 技术栈

- **后端**：Python 3.13 + FastAPI + ChromaDB + Anthropic Claude API
- **前端**：纯 HTML/CSS/JS（无构建步骤）
- **包管理**：uv
- **向量模型**：all-MiniLM-L6-v2（sentence-transformers）

### 核心流程

```
用户提问 → FastAPI 接收 → RAGSystem.query()
  → 构建 prompt + 获取会话历史
  → 调用 Claude API（带工具定义）
  → Claude 决定是否调用搜索工具
  → 如果调用：执行 CourseSearchTool → 向量搜索 ChromaDB → 返回结果给 Claude
  → Claude 基于搜索结果生成最终回答
  → 更新会话历史 → 返回前端
```

## 后端模块说明

| 文件 | 职责 |
|------|------|
| `app.py` | FastAPI 入口，两个 API：`POST /api/query`（问答）、`GET /api/courses`（课程统计），启动时自动加载 `docs/` 下的文档 |
| `rag_system.py` | 核心编排器，串联所有组件 |
| `ai_generator.py` | 封装 Claude API 调用，支持单轮工具调用循环 |
| `search_tools.py` | 工具抽象层，`CourseSearchTool` 将向量搜索封装为 Claude 可调用的工具 |
| `vector_store.py` | ChromaDB 封装，两个集合：`course_catalog`（课程元数据）和 `course_content`（分块内容），支持模糊课程名匹配 |
| `document_processor.py` | 解析课程 `.txt` 文件（固定格式：标题/链接/讲师 + Lesson 分段），按句子分块 |
| `session_manager.py` | 内存中的会话管理，历史对话以文本形式注入 system prompt |
| `models.py` | Pydantic 数据模型：`Course`、`Lesson`、`CourseChunk` |
| `config.py` | 配置项（分块大小 800、重叠 100、最多返回 5 条结果、记忆 2 轮对话） |

### 前端

`frontend/` 目录下的静态文件，由 FastAPI 挂载在 `/` 路径下。`index.html` + `script.js` + `style.css`，直接调用后端 API。

### 数据

`docs/` 目录下 4 个课程脚本文件（`course1_script.txt` 到 `course4_script.txt`），有固定的文本格式，包含课程标题、链接、讲师和按 Lesson 划分的内容。

## POST /api/query 调用栈

```
app.py:65  query_documents(request)
│
├── session_manager.py:18  SessionManager.create_session()          # 如果没有 session_id
│
└── rag_system.py:102  RAGSystem.query(query, session_id)
    │
    ├── session_manager.py:42  SessionManager.get_conversation_history(session_id)
    │
    └── ai_generator.py:43  AIGenerator.generate_response(query, history, tools, tool_manager)
        │
        ├── anthropic API 调用 (messages.create)
        │
        └── [如果 stop_reason == "tool_use"]
            │
            └── ai_generator.py:89  AIGenerator._handle_tool_execution(response, params, tool_manager)
                │
                ├── search_tools.py:135  ToolManager.execute_tool("search_course_content", **kwargs)
                │   │
                │   └── search_tools.py:52  CourseSearchTool.execute(query, course_name?, lesson_number?)
                │       │
                │       └── vector_store.py:61  VectorStore.search(query, course_name?, lesson_number?)
                │           │
                │           ├── vector_store.py:102  VectorStore._resolve_course_name()  # 如果有 course_name
                │           │   └── ChromaDB course_catalog.query()
                │           │
                │           ├── vector_store.py:118  VectorStore._build_filter()
                │           │
                │           └── ChromaDB course_content.query()
                │
                └── anthropic API 第二次调用 (带工具结果，无工具定义)
    │
    ├── search_tools.py:142  ToolManager.get_last_sources()
    ├── search_tools.py:150  ToolManager.reset_sources()
    └── session_manager.py:37  SessionManager.add_exchange(session_id, query, response)
```

## 调用栈逐层解释

### 1. app.py:65 — query_documents()

HTTP 入口层。接收前端的 JSON 请求，检查是否有 `session_id`，没有就创建一个新会话，然后把请求转给 RAGSystem。

### 2. rag_system.py:102 — RAGSystem.query()

编排层。把各个组件串起来，控制整个问答流程的顺序：取历史 → 调 AI → 收集来源 → 存会话。它本身不做具体工作，只负责协调。

### 3. session_manager.py:42 — get_conversation_history()

从内存字典中取出该 session 的历史消息，格式化成 `"User: xxx\nAssistant: xxx"` 的文本字符串，最多保留 2 轮对话（`MAX_HISTORY=2`）。

### 4. ai_generator.py:43 — generate_response()

构建 Claude API 请求。把系统提示词、历史对话、用户问题和工具定义组装成 API 参数，发送第一次请求。根据 Claude 的响应决定走哪条路径：直接返回文本，或者进入工具调用流程。

### 5. ai_generator.py:89 — _handle_tool_execution()

工具执行层。从 Claude 的响应中提取工具调用（名称 + 参数），交给 ToolManager 执行，把执行结果放回消息列表中，再发第二次 API 请求让 Claude 基于搜索结果生成最终回答。第二次请求**不带工具定义**，防止 Claude 再次调用工具。

### 6. search_tools.py:135 — ToolManager.execute_tool()

工具分发层。根据工具名称（`"search_course_content"`）在注册表中找到对应的工具实例，调用它的 `execute()` 方法。设计上支持多种工具，但目前只注册了一个搜索工具。

### 7. search_tools.py:52 — CourseSearchTool.execute()

搜索工具的具体实现。接收搜索参数，调用向量数据库，处理空结果和错误情况，格式化搜索结果为 `[课程名 - Lesson N]\n内容` 的文本，同时记录来源信息供前端展示。

### 8. vector_store.py:61 — VectorStore.search()

向量检索层，分三步：

- **课程名解析**：如果传了 `course_name`，先在 `course_catalog` 集合中做语义搜索，把模糊名称（如 "MCP"）匹配到准确的课程标题
- **构建过滤条件**：组合课程标题和课时号为 ChromaDB 的 where 过滤器
- **内容搜索**：在 `course_content` 集合中用语义搜索找到最相关的文本块（默认返回 5 条）

### 9. 回到 RAGSystem.query() — 收尾工作

- **get_last_sources()** — 从搜索工具中取出本次查询命中的来源列表（如 "课程A - Lesson 3"）
- **reset_sources()** — 清空来源状态，避免污染下次请求
- **add_exchange()** — 把这轮问答存入会话历史，供下次请求使用

## RAG 请求入口

RAG 请求的核心入口在 `backend/rag_system.py:102` 的 `RAGSystem.query()` 方法。

该方法被 `backend/app.py:75` 调用：

```python
answer, sources = rag_system.query(request.query, session_id)
```

## 关键设计点

- **工具调用模式**：不是直接把检索结果塞进 prompt，而是让 Claude 通过工具调用（tool use）自己决定是否需要搜索
- **单轮工具调用**：Claude 最多调用一次工具，拿到结果后直接生成答案
- **服务器工作目录是 `backend/`**，所以代码中的相对路径如 `../docs`、`../frontend` 都是相对于 backend 目录
- **ChromaDB 数据持久化在 `backend/chroma_db/`**
