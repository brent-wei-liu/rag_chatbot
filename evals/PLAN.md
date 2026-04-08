# RAG 系统效果评估方案

## Context

当前项目（`starting-ragchatbot-codebase`）是一个基于 Claude tool-use 的 RAG 问答系统，但**完全没有效果评估机制**：
- `tests/test_ui.py` 只覆盖前端 UI 行为（Playwright mock 后端），不验证检索或回答质量
- 没有 ground truth 数据集，没有 eval 脚本，没有指标记录
- 仅有少量 `print()` 日志，无法回放或离线分析

要判断一次改动（换 embedding、改 chunk 大小、改 prompt、改 tool schema）是否真的让系统变好，必须建立可重复的评估手段。本方案给出一套**分层评估方法**，从最轻量到最严谨。

## 系统中可观测的评估信号

参考探索结果，已有的可利用接口：
- `RAGSystem.query(query, session_id)` → `(answer, sources)`（`backend/rag_system.py:104`）
- `VectorStore.search()` → `SearchResults(documents, metadata, distances)`（`backend/vector_store.py:61`），含相似度分数
- `ToolManager.get_last_sources()` → 本次回答引用的 `[课程 - 课时]` 列表（`backend/rag_system.py:132`）
- Claude 的 tool_use 块包含工具名、参数、结果（`backend/ai_generator.py:114`）——可以观察"Claude 决定搜什么"

这意味着对每个 query 都可以采集：原问题、Claude 改写的检索 query、命中 chunks、相似度、最终答案、引用来源。

## 用户决定的范围

经确认，本次只落地**第 1 层（检索质量评估）**，且 ground truth 由 **Claude 自动合成**（不做人工标注）。下面第 2/3/4 层保留作为后续可选扩展，本次不实施。

## 推荐的四层评估方法

### 第 1 层：检索质量（Retrieval Eval）—— 最重要、性价比最高

**做什么**：构造 30–50 条 `(question, expected_course, expected_lesson)` 的小型 ground truth 集。直接调用 `VectorStore.search()`，计算：
- **Recall@k**：正确课时是否出现在前 k 条结果中
- **MRR**（Mean Reciprocal Rank）：正确结果的排名倒数
- **课程过滤准确率**：fuzzy 课程名解析是否命中（`vector_store.py` 的 catalog 查询）

**为什么先做这层**：检索是 RAG 上限。检索不到正确 chunk，下游再强的 LLM 也救不回来。这层不需要调用 Claude API，跑得快、成本低、确定性强，适合 CI。

**新增文件**：
- `evals/groundtruth_retrieval.jsonl` — 数据集
- `evals/run_retrieval_eval.py` — 直接 import `VectorStore`，输出指标表

### 第 2 层：端到端答案质量（LLM-as-Judge）

**做什么**：构造 20–30 条 `(question, reference_answer)` 集合。调用 `RAGSystem.query()` 拿到答案，然后用 Claude 作为评审，对每条打分：
- **Faithfulness**：答案是否完全基于 sources，有无幻觉
- **Relevance**：是否回答了问题
- **Completeness**：关键信息是否齐全

**为什么用 LLM-as-Judge**：人工评分太慢；标准 NLP 指标（BLEU/ROUGE）对开放生成不可靠；Claude 自评在 RAG 这类「有上下文有引用」场景下相关性不错。

**注意**：评审 prompt 要求 judge 同时看到 sources，让它判断 faithfulness 时有依据；评分用 1–5 等级 + 简短理由，便于 diff 分析。

### 第 3 层：工具使用行为评估

**做什么**：本项目特点是 Claude 自己决定调用 `search_course_content` 还是 `get_course_outline`，以及参数怎么填。需要单独观察：
- 该用 outline 时是否用了 outline（如「这门课有几节课？」）
- 检索查询改写是否合理（不是简单透传原问题）
- 是否过度调用 / 不必要调用

**实现**：在 `AIGenerator._handle_tool_execution()` 里加可选的 trace hook，把每次 tool_use 序列化成 JSON dump 到 `evals/traces/`。然后写一个轻量分析脚本统计工具使用分布。

**为什么单独做**：tool-use RAG 的失败模式经常是「Claude 选错了工具」或「检索 query 写得太宽」，这是直接注入式 RAG 没有的失败模式，必须单独覆盖。

### 第 4 层：回归监控（可选，长期）

把第 1、2 层做成 `pytest` 用例（marker `@pytest.mark.eval`），配合一个 baseline JSON，PR 跑 eval 时自动 diff 指标。第 1 层进 CI；第 2 层手动触发（要花 API 费用）。

## 本次落地的具体步骤（第 1 层 + Claude 合成数据集）

1. **写 `evals/generate_groundtruth.py`** —— 遍历 `docs/course*_script.txt`，按课时切分；对每个课时调用 Claude（`claude-opus-4-6`），让它基于该课时内容生成 3–5 条具体问题，输出 `(question, expected_course_title, expected_lesson_number)`，写入 `evals/groundtruth_retrieval.jsonl`。
   - 关键约束：prompt 里要求问题"必须能在该课时内容中找到答案，不能问需要跨课时综合的问题"，否则 ground truth 不可靠
   - 每个课时只把该课时的文本喂给 Claude，避免它生成可在其他课时也找到答案的歧义问题
   - 目标量：约 50–100 条（4 门课 × 若干课时 × 3–5 条）
2. **写 `evals/run_retrieval_eval.py`** —— 直接 `from vector_store import VectorStore`，加载 `backend/chroma_db/`，对每条 ground truth 调用 `search(query, course_name=None, lesson_number=None)`（即不带过滤，模拟最坏情况），用返回的 `metadata` 比对 `course_title` + `lesson_number`，计算：
   - Recall@1 / Recall@3 / Recall@5
   - MRR
   - 按课程分组的指标（看是否某门课特别差）
3. **跑一遍现状**，输出写入 `evals/baselines/2026-04-07.json`，含完整指标 + 配置快照（CHUNK_SIZE、CHUNK_OVERLAP、MAX_RESULTS、embedding 模型名）
4. **写最简 README** `evals/README.md`，说明怎么重跑、怎么对比 baseline

后续若想做 LLM-as-Judge / tool-use 评估 / CI 集成，再回到本计划的第 2/3/4 层。

### 关于 Claude 合成数据集的风险

合成数据集最大的风险是「Claude 生成的问题措辞和原文太接近 → embedding 检索轻松命中 → 指标虚高」。缓解措施：
- 在 prompt 里要求 Claude **改写措辞**，不要照抄原文短语
- 生成时让它输出几种不同风格：直接事实问题、概念性问题、应用性问题
- 跑完 baseline 后，**人工抽检 10 条**确认问题质量；若发现明显泄漏（问题里含原文罕见术语），调整生成 prompt 重跑

## 关键文件清单（执行阶段会用到）

需要**读取**（不修改）：
- `backend/rag_system.py:104` — `query()` 主入口
- `backend/vector_store.py:61` — `search()`，retrieval eval 直接调用它
- `backend/search_tools.py:20` — 两个工具的实现
- `backend/config.py` — 调参对象
- `docs/course*_script.txt` — 生成 ground truth 的输入

需要**新建**：
- `evals/generate_groundtruth.py`
- `evals/groundtruth_retrieval.jsonl`
- `evals/run_retrieval_eval.py`
- `evals/baselines/2026-04-07.json`
- `evals/README.md`

## 验证方式

- `uv run python evals/generate_groundtruth.py` 应生成约 50–100 条 jsonl 记录
- `uv run python evals/run_retrieval_eval.py` 输出 Recall@1/3/5 和 MRR 数字
- Sanity check：故意把 `config.py` 的 `MAX_RESULTS` 改成 1，重跑应看到 Recall@3/@5 显著下降（验证脚本逻辑没写错）
- 抽检 10 条 ground truth，确认问题措辞不是直接照抄原文

## 已确认的决策

- 范围：仅第 1 层（检索质量评估）
- 数据集来源：纯 Claude 合成，不做人工标注（接受质量风险，靠抽检缓解）
