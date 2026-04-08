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

### 示例输出

`--clear` 重新摄取当前 `docs/` 的输出（含每节切片数量的 debug 行）：

```
$ uv run python -m db.ingest --clear --docs docs
Clearing existing collections...
  [debug] course1_script.txt: 153 chunks across 9 lesson(s) -> L0=8, L1=13, L2=24, L3=19, L4=28, L5=18, L6=25, L7=16, L8=2
  added: Building Towards Computer Use with Anthropic (153 chunks)
  [debug] course2_script.txt: 164 chunks across 11 lesson(s) -> L0=6, L1=14, L2=24, L3=14, L4=14, L5=14, L6=19, L7=18, L8=12, L9=13, L10=16
  added: MCP: Build Rich-Context AI Apps with Anthropic (164 chunks)
  [debug] course3_script.txt: 90 chunks across 7 lesson(s) -> L0=5, L1=20, L2=20, L3=17, L4=10, L5=14, L6=4
  added: Advanced Retrieval for AI with Chroma (90 chunks)
  [debug] course4_script.txt: 121 chunks across 7 lesson(s) -> L0=8, L1=40, L2=23, L3=13, L4=15, L5=20, L6=2
  added: Prompt Compression and Query Optimization (121 chunks)

Done. Added 4 course(s), 528 chunk(s). Skipped 0.
```

`L<n>=<count>` 表示该课时被切成的 chunk 数。如果某节远多于其他节
（比如上面 course4 的 L1=40），通常说明该课时正文特别长，
可以作为调整 `CHUNK_SIZE` 的参考。

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

## 切片与 embedding

### 一句话总结

每节课的正文按**句子边界**拆成 ≤800 字符的 chunk（**保证不切断句子**，
相邻 chunk 之间整句重叠 ≤100 字符），每个 chunk 加上
`Course X Lesson N content:` 前缀后喂给 `all-MiniLM-L6-v2` 模型生成
**384 维**向量；向量 + HNSW 图索引存到 `db/chroma_db/<segment-uuid>/*.bin`，
chunk 原文 + metadata 存到 `db/chroma_db/chroma.sqlite3`，两者通过
chunk ID 关联。

### 切片细节

切片由 `DocumentProcessor.chunk_text()` 完成，关键规则：

- **以句子为最小单位**：先用正则按句尾标点切句，然后**按句子累加**直到
  加下一句会超过 `CHUNK_SIZE`（默认 800）才停。所以每个 chunk **≤ 800**
  字符，但通常略小，**永远不会切断句子中间**。
- **每节独立切片**：chunker 不跨课时合并。短课时只产出极少 chunk
  （示例输出里 `L8=2` 就是只有 2 个 chunk 的课时）。
- **重叠是字符上限，不是句子数**：`CHUNK_OVERLAP`（默认 100）是相邻
  chunk 之间允许重叠的字符总数。从当前 chunk 末尾倒数完整句子，
  累计长度 ≤ 100 才会被纳入下一个 chunk。

  因此**重叠的句子数量是动态的**：

  | 句子长度 | 实际重叠 |
  |---|---|
  | 都很短（~10 字符） | 8–10 句 |
  | 中等（~30–50 字符） | 2–3 句 |
  | 都很长（>100 字符） | **0 句**——单句已超 100，倒数循环直接 break |

- **超长单句的兜底**：如果某句本身就超过 800 字符，循环里的
  `if current_size + total_addition > self.chunk_size and current_chunk`
  保证 `current_chunk` 至少塞进 1 句（避免死循环）。这种情况下该 chunk
  会**超过 800 字符**——这是已知的边界行为，不是 bug。

### Embedding 与存储

- **前缀**：每个 chunk 在送入 embedding 前会加上
  `Course <课程标题> Lesson <N> content: ` 前缀，让单看一个 chunk 也带有
  课程/课时的语义锚点。这一步是 `process_course_document` 在 chunker
  之后做的。
- **模型**：`sentence-transformers/all-MiniLM-L6-v2`（22M 参数，CPU 推理，
  本地运行；权重首次使用时由 `sentence-transformers` 库自动从 HuggingFace
  下载到 `~/.cache/huggingface/`）。输出 **384 维 float32 向量**。
- **写入路径**：通过 `chromadb.PersistentClient` 嵌入式（in-process）写入
  `db/chroma_db/`，无独立服务进程。
  - **`chroma.sqlite3`** 是权威源，存：collection / segment 元数据、每个
    chunk 的 ID、原文、metadata（`course_title`、`lesson_number`、
    `chunk_index`）以及 FTS5 全文索引
  - **`<segment-uuid>/*.bin`** 是 [HNSW](https://arxiv.org/abs/1603.09320)
    图索引（由 `hnswlib` 写）。`data_level0.bin` 存最底层节点的 384 维
    向量本体 + 邻居指针，`link_lists.bin` 存上层稀疏节点的邻居，用于加速
    近似最近邻检索
  - 两者通过 **chunk ID** 关联——查询时 HNSW 给出最相近的 ID 列表，
    sqlite 据此回填文本和 metadata

## 依赖

- `core/` — `Config`、`VectorStore`、Pydantic 模型
- ChromaDB（通过 `core.vector_store`）—— 持久化到 `db/chroma_db/`

## 不在范围内

- 文件监听 / 自动重新摄取
- 超出按标题去重的逐文件增量更新
- 回答质量评估 —— 见 `evals/` 中的检索评估工具
