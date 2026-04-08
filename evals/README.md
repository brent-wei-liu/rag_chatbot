# 检索评估

本目录包含针对 RAG 检索层的最小评估工具。
它**不**评估 Claude 的回答质量——只评估 `VectorStore.search()`
能否为给定问题找到正确的课程/课时。

## 文件说明

- `generate_groundtruth.py` — 使用 Claude 按课时合成问题
- `groundtruth_retrieval.jsonl` — 生成的数据集（每行一条记录）
- `run_retrieval_eval.py` — 通过 `VectorStore` 跑查询，计算 Recall@k + MRR
- `baselines/YYYY-MM-DD.json` — 保存的指标快照，用于对比

## 运行方式

```bash
# 1. 生成数据集（会用到 ANTHROPIC_API_KEY，花费少量 API 费用）
uv run python evals/generate_groundtruth.py

# 2. 确保 ChromaDB 已被填充
uv run python -m db.ingest --docs docs

# 3. 跑评估
uv run python evals/run_retrieval_eval.py
```

评估会打印 JSON 报告，并保存到 `evals/baselines/<今天日期>.json`。

## 指标

- **Recall@k**：正确课时出现在前 k 个 chunk 中的问题占比。二元判断（命中/未命中），不区分在前 k 内的具体排名。
- **MRR**（Mean Reciprocal Rank，平均倒数排名）：所有问题的 `1 / 第一个正确 chunk 的排名` 的平均值。取值范围 0–1；1.0 表示正确 chunk 总是排第 1 位。关心命中**落在前 k 的哪个位置**。
- **by_course**：按课程细分的同样指标（用于发现某门课表现特别差的情况）

### MRR vs DCG / NDCG

| | MRR | DCG / NDCG |
|---|---|---|
| **关心几个正确结果** | 只关心**第一个**正确结果 | 关心**所有**正确结果 |
| **相关性是几档** | 二元（对/错） | 支持多档（0/1/2/3...，越相关分越高） |
| **排名惩罚** | `1/rank`（线性倒数） | `1/log2(rank+1)`（对数折损，更平缓） |
| **适用场景** | 只有一个"正确答案"，找到就停 | 一个查询有多个相关结果，排名都重要 |

**公式**

MRR（对单个查询）：

```
RR = 1 / rank_of_first_correct
```

DCG@k（对单个查询）：

```
DCG = Σ (rel_i / log2(i+1))    for i=1..k
```

其中 `rel_i` 是第 i 位结果的相关性分数。NDCG = DCG / IDCG（理想排序下的 DCG），归一化到 0–1。

**举例**

假设 top-5 结果的相关性是 `[0, 1, 0, 1, 1]`（两个完全相关）：

- **MRR**：第一个正确在第 2 位 → RR = 1/2 = **0.5**
  （第 4、第 5 位的两个正确结果完全被忽略）
- **DCG@5**：`1/log2(3) + 1/log2(5) + 1/log2(6)` ≈ 0.63 + 0.43 + 0.39 = **1.45**
  （三个正确结果都计入，但越靠后权重越低）

**为什么本项目用 MRR**

NDCG 能处理 MRR 处理不了的两件事：
1. 一个查询有多个相关结果
2. 分级相关性（非常相关 vs. 略微相关）

本项目中每条 ground truth 问题**只对应一个**正确课时，相关性是二元的——所以 MRR 是合适的选择。如果以后要评估"多个课时都能合理回答同一个问题"的场景，再切换到 NDCG。

简单记忆：**MRR 看第一名，NDCG 看整张排行榜。**

## 对比改动

调整 `CHUNK_SIZE`、`MAX_RESULTS`、embedding 模型等之后，重新 ingest 文档
（删除 `db/chroma_db/` 后跑 `python -m db.ingest --clear`），然后重跑评估，
并与之前的 baseline 文件做 diff。

## 改进记录

### 2026-04-07 — 统一 chunk 前缀

**改动**：`db/document_processor.py` 重构后，每个 chunk 都加上
`"Course <title> Lesson N content: ..."` 前缀。之前的实现里，只有每节的
**第一个** chunk 有 `"Lesson N content: "` 前缀（且不带课程名），
其余 chunk 是裸文本——只有"最后一节"是个例外，每个 chunk 都带完整前缀。
这是历史不一致，重构时统一为"全部 chunk 都带完整前缀"。

**指标变化**（n=128）：

| 指标 | 前 | 后 | 变化 |
|---|---|---|---|
| mrr      | 0.7887 | **0.8033** | +1.5pp |
| recall@1 | 0.6953 | **0.7109** | +1.6pp |
| recall@3 | 0.9062 | 0.8984     | −0.8pp |
| recall@5 | 0.9219 | 0.9219     | 持平 |

**解读**：净改进。2 题从 rank 2/3 爬到了 rank 1（mrr 和 recall@1 上升），
1 题从 top-3 滑到了 top-5（recall@3 微降），但 recall@5 不变意味着
**没有任何题真的丢失**——只是顶端排名重排。机制是前缀给每个 chunk 单独
加上了课程/课时锚点，让强信号更突出，但同时把同一节内不同 chunk 在
embedding 空间里推得更近，造成顶端竞争更紧。

## Sanity 检查

- 抽检 `groundtruth_retrieval.jsonl` 中的 10 条记录——问题应该是**改写**，
  而不是逐字照抄原文里的特征短语。如果发现泄漏，调整
  `generate_groundtruth.py` 里的 prompt 并重新生成。
- 把 `MAX_RESULTS` 改成 1 再跑一次：Recall@3/@5 应该明显下降，
  以此验证脚本的命中检测逻辑没写错。

## 未覆盖（有意为之）

- 答案质量 / faithfulness（LLM-as-Judge）—— 见 `PLAN.md` 第 2 层
- Tool-use 行为（Claude 选了哪个工具、怎么改写 query）—— 第 3 层
- CI 集成 —— 第 4 层
