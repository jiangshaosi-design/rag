# 系统架构设计

## 整体架构

```
┌──────────────────────────────────────────────────┐
│                  Streamlit UI                     │
│  ┌──────────────┐  ┌──────────┐  ┌────────────┐ │
│  │ 对话面板      │  │ 侧边栏    │  │ 来源+图片   │ │
│  │ (聊天窗口)    │  │ (文档管理) │  │ (内嵌渲染)  │ │
│  └──────┬───────┘  └──────────┘  └──────▲─────┘ │
└─────────┼─────────────────────────────────┼──────┘
          │                                 │
┌─────────▼─────────────────────────────────┼──────┐
│              LangChain Agent                      │
│  ┌──────────────────────────────────────┐        │
│  │  ReAct Agent (DeepSeek V4 Pro)       │        │
│  │  ┌───────┐ ┌────────┐ ┌──────────┐  │        │
│  │  │Tool 1 │ │Tool 2  │ │Tool 3    │  │        │
│  │  │缓存   │ │知识库  │ │数据库    │  │        │
│  │  │查询   │ │检索    │ │查询      │  │        │
│  │  └───┬───┘ └───┬────┘ └────┬─────┘  │        │
│  │  ┌───────────────────────┐           │        │
│  │  │Tool 4: 文档管理       │           │        │
│  │  └───────────┬───────────┘           │        │
│  └──────┼───────┼────────────┼───────────┘        │
└─────────┼───────┼────────────┼────────────────────┘
          │       │            │
┌─────────▼──┐ ┌───▼────┐ ┌───▼──────────┐
│  FAISS     │ │ MySQL  │ │  File System │
│  向量检索  │ │ 元数据 │ │  文档 + 图片  │
│  + Embedding│ │  + 映射 │ │  data/       │
└────────────┘ └────────┘ └───────────────┘
```

## 数据流

### 文档入库流程
```
文档上传 → 保存到 data/uploads/
         → PDFLoader 调用 Docker MinerU 解析:
              ├─ 版面分析 (doclayout_yolo + 文字阅读顺序)
              ├─ 表格识别 → Markdown 表格
              └─ 图片提取 + 自动分类 (过滤 logo/装饰)
         → 图片 → 复制到 data/images/ → Qwen-VL 并行描述 (3线程)
         → 表格包裹 [TABLE_START]...[TABLE_END] (分块保护)
         → Splitter 混合分块:
              第一层: RecursiveCharacterTextSplitter (size=1000, overlap=100)
              第二层: 滑动窗口细分 (window=500, step=250)
         → Embedder 生成向量 (阿里云 text-embedding-v4, 10条/批)
         → FAISS + MySQL 双存储
         → MinerU 原始输出持久化到 data/mineru_output/doc_{id}/
```

### 问答流程
```
用户提问 → Agent 分析意图
         → 先查缓存: SQL 粗筛 + Embedding 精排(>0.85) → 命中则直接返回
         → 未命中: Embedding(问题) → FAISS.search(Top-K)
         → 从 MySQL 获取文本块完整内容
         → 组装 Prompt (System + Context + Question)
         → DeepSeek V4 Pro 生成回答
         → 检测来源中 [IMAGE:xxx]: 标签 → 追加到回答正文
         → 前端渲染: 文本 markdown + 图片内嵌
         → 返回回答 + 思考过程 + 来源列表
         → 写入 chat_history
```

## 模块职责

| 模块 | 职责 | 依赖 |
|------|------|------|
| config/settings.py | 全局配置管理 | .env |
| src/database/ | MySQL 连接和 CRUD | mysql-connector-python |
| src/knowledge_base/loader.py | PDF (MinerU Docker) / DOCX / Markdown 解析 | Docker, python-docx |
| src/knowledge_base/image_describer.py | Qwen-VL 图片描述 | dashscope |
| src/knowledge_base/splitter.py | 文本分块 + 表格保护 | langchain |
| src/knowledge_base/embedder.py | 向量化 (1024维) | dashscope |
| src/knowledge_base/vector_store.py | FAISS 操作 | faiss-cpu |
| src/knowledge_base/pipeline.py | 入库/删除全流程编排 | 以上全部 |
| src/agent/tools.py | Agent 工具定义 (4个) | langchain |
| src/agent/agent.py | Agent 组装与调用 | langchain, langchain-openai |
| src/evaluation/metrics.py | 四维评估指标 + LLM 自动出题 | langchain, dashscope |
| src/app.py | Streamlit UI | streamlit |
| src/api/server.py | FastAPI 服务（HTML 版后端） | fastapi, jinja2 |
| src/ui/ | HTML 版前端资源（模板 / CSS / JS） | — |
| Docker | MinerU 文档解析 (~43GB 镜像) | mineru:latest |
