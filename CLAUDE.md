# CLAUDE.md — RAG 智能体问答系统

## 项目概述
基于 LangChain 的 RAG 智能体问答系统。DeepSeek V4 Pro 做 LLM，阿里云 text-embedding-v4 做向量化，FAISS + MySQL 双存储，Docker MinerU 做 PDF 版面解析，Streamlit 做前端界面。

## 标准文档路径

| 文档 | 路径 | 说明 |
|------|------|------|
| 需求规格 | [docs/01-requirements.md](docs/01-requirements.md) | 功能需求和技术要求 |
| 系统架构 | [docs/02-architecture.md](docs/02-architecture.md) | 模块划分和数据流 |
| 接口规范 | [docs/03-api-spec.md](docs/03-api-spec.md) | Agent 工具定义和 Prompt 模板 |
| 数据库设计 | [docs/04-database-design.md](docs/04-database-design.md) | 表结构和 FAISS 映射规则 |
| 开发规范 | [docs/05-dev-standards.md](docs/05-dev-standards.md) | 代码风格和开发流程 |
| 文件结构梳理 | [docs/06-文件结构梳理.md](docs/06-文件结构梳理.md) | 逐文件职责与分层依赖 |
| 系统流程梳理 | [docs/07-系统流程梳理.md](docs/07-系统流程梳理.md) | 四条主流程的函数级调用链 |

## 启动方式

### 前置条件
1. Docker Desktop 已启动（PDF 解析依赖 MinerU Docker 镜像）
2. MySQL 服务已启动
3. conda 环境 `myenv` 已激活

### Streamlit 版（推荐）

```bash
conda activate myenv
streamlit run src/app.py --server.port 8501
```
访问 `http://localhost:8501`

### HTML 版（FastAPI + 原生前端）

```bash
conda activate myenv
python -m uvicorn src.api.server:app --host 0.0.0.0 --port 8000 --reload
```
访问 `http://localhost:8000`（落地页）/ `http://localhost:8000/app`（运行页）

### MinerU 模型源（国内）
每次启动终端时设置：
```bash
set MINERU_MODEL_SOURCE=modelscope
```

## 工作指引

### 修改 Streamlit UI 前必读
样式修改顺序：Streamlit 主题配置（`.streamlit/config.toml`）→ Streamlit 原生参数 → 最后才用 CSS 补做不到的部分。不要用 HTML 思维写 Streamlit 页面。

### 代码原则
- 每层模块职责边界清晰，不引入不必要的跨层依赖
- 所有配置从 `config/settings.py` 统一获取，不硬编码
- 敏感信息（API Key、密码）只能从 `.env` 读取，不可出现在代码中
- 新功能先跑通再优化，不过早抽象
- 只写必要的注释，代码命名自解释

### 验证要求
- 修改后启动 Streamlit 确认无报错: `streamlit run src/app.py --server.port 8501`
- 浏览器打开 http://localhost:8501 验证页面
- 上传测试文档并提问，确认完整流程正常

### 技术栈
- Python 3.10+ | LangChain 1.3+ | Streamlit 1.28+
- MySQL (mysql-connector-python) | FAISS (faiss-cpu)
- DeepSeek V4 Pro (langchain-openai) | 阿里云 Embedding + Qwen-VL (dashscope)
- PDF 解析: Docker MinerU (版面分析 + 表格 + 图片)
- DOCX: python-docx（段落 + 表格）；Markdown: 直接读取
- Docker: mineru:latest 镜像 (~43GB)


