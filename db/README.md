# db/

课程资料 RAG 聊天机器人的离线数据层。包含文档解析器、摄取 CLI 和本地 ChromaDB 存储。

从应用视角看，本模块对向量库**只写**——它产出的数据由 `api/` 之后读取。它作为独立 CLI 运行，**不**被 API 进程引用。

## 运行

在项目根目录下：

```bash
# 摄取 docs/，跳过库中已存在的课程
uv run python -m db.ingest

# 自定义 docs 文件夹
uv run python -m db.ingest --docs path/to/docs

# 清空已有 collection 后重新摄取
uv run python -m db.ingest --clear
```

幂等：用默认参数重复运行是安全的——按课程标题匹配，已存在的课程会被跳过。

## 文件

- `ingest.py` — CLI 入口。遍历 docs 文件夹，用 `DocumentProcessor` 解析每个文件，通过 `core.vector_store` 写入 ChromaDB。打印新增/跳过课程的汇总。
- `document_processor.py` — 解析项目特定格式的课程 `.txt` 文件（Course Title / Link / Instructor 头 + `Lesson N:` 段落）。按句子切片，遵循 `core.config` 的 `CHUNK_SIZE` / `CHUNK_OVERLAP`。
- `chroma_db/` — ChromaDB 持久化目录。包含两个 collection：`course_catalog`（课程元数据，title 作为 ID）和 `course_content`（文本切片）。已 gitignore。

## 课程文件格式

`document_processor.py` 期望的文件格式：

```
Course Title: <标题>
Course Link: <链接>
Course Instructor: <讲师>

Lesson 1: <课时标题>
Lesson Link: <链接>
<课时正文...>

Lesson 2: <课时标题>
...
```

不符合此头格式的文件会被跳过，并向 stderr 输出错误。

## 依赖

- `core/` — `Config`、`VectorStore`、Pydantic 模型
- ChromaDB（通过 `core.vector_store`）—— 持久化到 `db/chroma_db/`

## 不在范围内

- 文件监听 / 自动重新摄取
- 超出按标题去重的逐文件增量更新
- 回答质量评估 —— 见 `evals/` 中的检索评估工具
