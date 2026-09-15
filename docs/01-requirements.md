# 需求规格说明

## 项目概述
构建一套基于 LangChain 的 RAG（检索增强生成）智能体问答系统。用户通过 Streamlit Web 界面与系统交互，智能体自动识别用户意图，调用相应工具完成知识检索、数据库查询或文档管理任务，并生成带来源标注的回答。

## 核心场景

### 场景 1：本地私有知识库构建
- 用户通过界面上传文档（PDF / DOCX / Markdown）
- 系统自动解析文档内容、分块、生成 Embedding、存入 FAISS 向量库
- 同时将文档元数据和文本块信息存入 MySQL
- 支持文档列表查看和删除
- 上传显示分步进度条

### 场景 2：知识检索增强问答
- 用户以自然语言提问
- Agent 自动判断是否需要检索知识库
- 如需检索：将问题向量化 → FAISS 相似度搜索 → 获取 Top-K 文本块
- 将检索到的上下文注入 System Prompt，LLM 基于上下文生成回答
- 回复中包含来源引用标记（如 `[来源: 文档名]`）

### 场景 3：知识块回显
- 回答下方展示引用来源列表
- 点击来源可展开查看具体文本块内容
- 显示文档名和文本块序号

## 技术要求
- Python 3.10+
- LLM: DeepSeek V4 Pro API
- Embedding: 阿里云 text-embedding-v4 API
- 视觉模型: 阿里云 Qwen-VL (图片描述)
- 向量库: FAISS (IndexIDMap + IndexFlatIP)
- 关系库: MySQL
- UI: Streamlit（推荐）/ FastAPI + 原生 HTML/CSS/JS

## 文档类型支持
| 类型 | 解析方式 | 内容提取 |
|------|---------|---------|
| PDF | Docker MinerU | 文本（阅读顺序还原）+ 表格 (Markdown) + 图片 → Qwen-VL 描述 |
| DOCX | python-docx | 段落 + 表格 (Markdown)；不提取图片 |
| Markdown | 直接读取 | 纯文本 |

## 非功能需求
- 敏感配置（API Key、数据库密码）通过 .env 管理，不提交版本控制
- 系统需在 Windows 环境下可运行
- 上传文件存储在本地 data/uploads/
- FAISS 索引持久化到 data/faiss_index/
- API 调用有超时/重试/最大步数限制，防止异常消耗
