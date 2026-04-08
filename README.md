# 课程资料 RAG 系统

一个基于检索增强生成（RAG）的系统，通过语义搜索和 AI 驱动的回答来解答有关课程资料的问题。

## 概述

本应用是一个全栈 Web 应用，使用户能够查询课程资料并获得智能的、上下文感知的回答。它使用 ChromaDB 进行向量存储，使用 Anthropic 的 Claude 进行 AI 生成，并提供 Web 界面进行交互。

## 技术栈

| 层级 | 技术 | 版本 / 说明 |
|-------|-----------|-----------------|
| **应用** | FastAPI | 0.116.1 |
| | Uvicorn | 0.35.0 |
| **AI** | Anthropic SDK | 0.58.2（模型：`claude-opus-4-6`） |
| | sentence-transformers | 5.0.0（模型：`all-MiniLM-L6-v2`） |
| **数据** | ChromaDB | 1.0.15 |
| **前端** | HTML / CSS / JS | 静态，无框架 |
| **测试** | Playwright | 通过 pytest-playwright |
| | pytest | 9.0+ |
| **工具链** | Python | 3.13+ |
| | uv | 包管理器 |
| | python-dotenv | 1.1.1 |
| | python-multipart | 0.0.20 |

## RAG 检索设计：工具调用 vs 直接注入

传统 RAG 系统采用直接注入方式：拿到用户的问题，搜索向量数据库，然后把结果塞进 prompt。本项目采取了不同的方式——它给 Claude 一个**搜索工具**，让 AI 自己决定如何搜索。

| | 直接注入 | 工具调用（本项目） |
|---|---|---|
| **搜索查询** | 用户的原始问题 | Claude 构造优化后的搜索词 |
| **过滤** | 硬编码或无 | Claude 决定是否按课程/课时过滤 |
| **流程** | 问题 → 搜索 → Prompt → 回答 | 问题 → Claude → 工具调用 → 搜索 → 回答 |

关键组件是 `CourseSearchTool`（`backend/search_tools.py`），它将 ChromaDB 向量库封装为兼容 Anthropic 工具调用的工具。当用户提问时，Claude 接收问题和工具定义，决定搜索什么内容（以及是否按课程名或课时编号过滤），调用工具，接收结果，然后生成有依据的回答。

底层搜索仍然是访问本地 ChromaDB——工具只是让 **Claude 主导搜索策略**，而不是在后端硬编码。

## 先决条件

- Python 3.13 或更高版本
- uv（Python 包管理器）
- Anthropic API 密钥（用于 Claude AI）
- **Windows 用户**：使用 Git Bash 运行应用命令 - [下载 Git for Windows](https://git-scm.com/downloads/win)

## 安装

1. **安装 uv**（如果尚未安装）
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **安装 Python 依赖**
   ```bash
   uv sync
   ```

3. **配置环境变量**

   在根目录创建 `.env` 文件：
   ```bash
   ANTHROPIC_API_KEY=your_anthropic_api_key_here
   ```

## 运行应用

### 快速启动

使用提供的 shell 脚本：
```bash
chmod +x run.sh
./run.sh
```

### 手动启动

```bash
uv run uvicorn api.app:app --reload --port 8000
```

应用将运行于：
- Web 界面：`http://localhost:8000`
- API 文档：`http://localhost:8000/docs`

## 测试

项目包含使用 Playwright 编写的端到端 UI 测试。测试通过路由拦截 mock 所有后端 API 调用，因此无需 API 密钥或运行中的后端。

### 安装

```bash
# 安装测试依赖
uv sync --extra test

# 安装 Playwright 浏览器（一次性）
uv run playwright install chromium
```

### 运行测试

```bash
# 运行所有 UI 测试
uv run pytest tests/test_ui.py -v

# 运行指定测试
uv run pytest tests/test_ui.py::test_send_message -v

# 以可见浏览器运行（便于调试）
uv run pytest tests/test_ui.py -v --headed

# 以慢动作运行（便于可视化调试）
uv run pytest tests/test_ui.py -v --headed --slowmo 500
```

### 测试覆盖

| 测试 | 验证内容 |
|------|-----------------|
| `test_page_loads` | 页面标题、输入框、发送按钮和欢迎消息正常渲染 |
| `test_course_stats_load` | 侧边栏显示课程数量和标题 |
| `test_send_message` | 用户和助手消息出现在聊天中 |
| `test_loading_state` | 等待时显示加载动画并禁用输入 |
| `test_suggested_questions` | 点击建议会发送查询 |
| `test_sources_displayed` | 回答后的可折叠区域显示来源 |
| `test_error_handling` | API 失败时显示错误消息 |
| `test_enter_key_sends` | 回车键触发消息发送 |
| `test_empty_input_no_send` | 空输入无操作 |
| `test_session_id_persistence` | 会话 ID 在多次请求间保持 |
