"""LangChain Agent 组装 — ReAct Agent + DeepSeek V4 Pro。"""

from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from config.settings import settings
from src.agent.tools import search_knowledge_base, query_database, manage_documents, check_history

_SYSTEM_PROMPT = """你是一个知识库问答助手。你可以使用工具检索本地知识库来回答用户问题。

## 工具说明
- check_history(question): 优先调用，查询历史对话缓存。如果命中相似问题则直接返回缓存答案
- search_knowledge_base(query): 检索知识库中的文档内容（check_history 未命中时使用）
- query_database(sql): 执行 SELECT 查询
- manage_documents(action): 管理文档，"list" 或 "delete:<id>"

## 规则
1. 收到问题后先调用 search_knowledge_base 检索，再根据结果回答
2. 一轮检索后如果信息足够就直接回答，不要反复检索
3. 如果知识库没有相关信息，直接告知用户
4. 如果检索结果包含 [IMAGE:xxx]: 标签说明有对应图片，在回答中简要说明"相关图片已附在下方"
5. 使用中文回答，简洁准确
6. 引用来源会自动展示在下方，回答正文中不要列出引用来源"""

_TOOLS = [check_history, search_knowledge_base, query_database, manage_documents]


def _create_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.DEEPSEEK_MODEL,
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
        temperature=0.3,
        timeout=settings.LLM_TIMEOUT,
        max_retries=settings.LLM_MAX_RETRIES,
    )


_agent = None


def get_agent():
    """获取或创建 Agent 单例。"""
    global _agent
    if _agent is None:
        llm = _create_llm()
        _agent = create_agent(
            model=llm,
            tools=_TOOLS,
            system_prompt=_SYSTEM_PROMPT,
        )
    return _agent


def invoke_agent(message: str, chat_history: list[dict] | None = None) -> dict:
    """执行 Agent 对话。

    Returns:
        {"response": str, "thinking": [...], "sources": [...]}
        thinking: [{"type": "thought", "content": "..."}, {"type": "action", "tool": "...", "args": {...}}, {"type": "observation", "content": "..."}]
        sources: [{"filename": "...", "chunk_index": N, "content": "..."}]
    """
    import re

    agent = get_agent()

    messages = []
    if chat_history:
        for msg in chat_history[-10:]:
            role = msg.get("role", "")
            if role in ("user", "assistant"):
                messages.append((role, msg["content"]))

    messages.append(("user", message))

    try:
        result = agent.invoke(
            {"messages": messages},
            config={"recursion_limit": settings.AGENT_MAX_ITERATIONS},
        )
    except Exception as e:
        error_msg = str(e)
        if "recursion" in error_msg.lower():
            error_msg = f"Agent 达到最大推理步数限制({settings.AGENT_MAX_ITERATIONS})，已中断。"
        return {"response": error_msg, "thinking": [], "sources": []}

    # ── 诊断日志 ──
    output_messages = result.get("messages", [])
    ai_msgs = [m for m in output_messages if getattr(m, "type", "") == "ai"]
    tool_msgs = [m for m in output_messages if getattr(m, "type", "") == "tool"]
    tc_count = sum(len(getattr(m, "tool_calls", None) or []) for m in ai_msgs)
    has_text_answer = any(getattr(m, "content", "") and not (getattr(m, "tool_calls", None) or [])
                          for m in ai_msgs)
    print(f"[AGENT DIAG] 总消息: {len(output_messages)}, AI消息: {len(ai_msgs)}, "
          f"工具调用: {tc_count}次, 工具返回: {len(tool_msgs)}次, "
          f"有文本答案: {has_text_answer}", flush=True)
    # 打印最后 3 条 AI 消息的类型
    for i, m in enumerate(ai_msgs[-3:]):
        content = getattr(m, "content", "") or ""
        tcs = getattr(m, "tool_calls", None) or []
        has_tc = len(tcs) > 0
        print(f"[AGENT DIAG] AI#{i}: content={len(content)}字, "
              f"tool_calls={len(tcs)}个, has_tool_calls={has_tc}", flush=True)

    output_messages = result.get("messages", [])
    response_text = ""
    thinking = []
    sources = []

    for msg in output_messages:
        msg_type = getattr(msg, "type", "")

        if msg_type == "ai":
            content = getattr(msg, "content", "") or ""
            tool_calls = getattr(msg, "tool_calls", None) or []

            # 如果 AI 消息有 tool_calls → 这是思考+行动
            if tool_calls and content:
                thinking.append({"type": "thought", "content": content[:200]})
            for tc in tool_calls:
                tc_name = tc.get("name", "unknown") if isinstance(tc, dict) else getattr(tc, "name", "unknown")
                tc_args = tc.get("args", {}) if isinstance(tc, dict) else getattr(tc, "args", {})
                thinking.append({"type": "action", "tool": tc_name, "args": tc_args})

            # 如果 AI 消息没有 tool_calls → 这是最终回答
            if not tool_calls and content:
                response_text = content

        elif msg_type == "tool":
            tool_name = getattr(msg, "name", "unknown")
            tool_content = getattr(msg, "content", "")

            # 显示工具返回的关键信息
            obs_preview = tool_content[:150] + ("..." if len(tool_content) > 150 else "")
            thinking.append({"type": "observation", "tool": tool_name, "content": obs_preview})

            # 从 search_knowledge_base 结果中提取来源
            if tool_name == "search_knowledge_base":
                for block in tool_content.split("\n---\n"):
                    block = block.strip()  # 去掉分隔符残留的 \n
                    if not block:
                        continue
                    m = re.search(r'\[来源:\s*(.+?)\s*\|\s*块(\d+)\]\s*\(相关度:\s*([\d.]+)\)', block)
                    if m:
                        # 第一行是来源头，之后是内容
                        body = block.split("\n", 1)
                        chunk_text = body[1].strip()[:300] if len(body) > 1 else ""
                        sources.append({
                            "filename": m.group(1).strip(),
                            "chunk_index": int(m.group(2)),
                            "score": float(m.group(3)),
                            "content": chunk_text,
                        })

    if not response_text:
        response_text = "未能获取有效回复，请重试。"

    return {"response": response_text, "thinking": thinking, "sources": sources}


def reset_agent() -> None:
    """重置 Agent（清空上下文）。"""
    global _agent
    _agent = None
