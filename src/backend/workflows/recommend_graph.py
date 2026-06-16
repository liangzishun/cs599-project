"""
LangGraph 推荐工作流 —— 多步骤推理引擎

工作流节点:
START -> understand_intent -> search_books -> analyze_preferences
                                                     |
                                             need_more_info?
                                            /              \\
                                       yes /                \\ no
                                          |                  |
                                   ask_clarification   generate_recommendation
                                          |                  |
                                   wait_user_input          END
                                          |
                                   understand_intent (loop)

采用 LangGraph StateGraph 实现状态管理，支持：
- 多步骤推理
- 条件路由
- 状态持久化
"""

from typing import TypedDict, Literal, Optional, Annotated
from datetime import datetime

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from src.backend.models.schemas import Book, Message, UserPreference
from src.backend.tools.book_search import search_books, get_book_detail
from src.backend.tools.preference_analyzer import analyze_preferences, get_user_preferences
from src.backend.models.book import format_books_for_llm, extract_subject_from_query
from src.backend.observability.tracer import get_tracer


# ──────────────────────────────────────────────
# 工作流状态定义
# ──────────────────────────────────────────────

class RecommendState(TypedDict):
    """推荐工作流的状态"""
    # 用户输入
    user_query: str
    user_id: str
    conversation_id: str

    # 意图分析
    intent: str                           # "search" | "recommend" | "chat" | "detail"
    extracted_keywords: list[str]         # 提取的关键词
    extracted_subject: Optional[str]      # 提取的题材

    # 搜索
    search_query: str                     # 搜索查询
    search_results: list[dict]            # 搜索结果（简化版 Book）
    search_total: int                     # 搜索结果总数

    # 偏好
    user_preferences: Optional[dict]      # 用户偏好
    need_more_info: bool                  # 是否需要追问

    # 推荐
    final_recommendations: list[dict]     # 最终推荐
    reasoning: str                        # 推荐理由
    assistant_message: str                # 给用户的回复

    # 控制
    next_action: str                      # 下一步动作
    iteration_count: int                  # 循环计数


# ──────────────────────────────────────────────
# 节点函数
# ──────────────────────────────────────────────

async def understand_intent(state: RecommendState) -> dict:
    """
    节点 1: 理解用户意图

    分析用户查询，提取关键信息：
    - 意图类型（搜索/推荐/聊天/详情）
    - 关键词
    - 题材偏好
    """
    tracer = get_tracer()
    tracer.tool_start("node:understand_intent", {"query": state["user_query"][:100]})

    query = state["user_query"]
    subject = extract_subject_from_query(query)

    # 简单的意图分类（可后续用 LLM 增强）
    intent = "recommend"
    if any(w in query for w in ["搜索", "找", "查找", "search", "有没有", "查询"]):
        intent = "search"
    elif any(w in query for w in ["详细", "详情", "介绍", "detail", "了解更多"]):
        intent = "detail"
    elif any(w in query for w in ["你好", "谢谢", "帮助", "hello", "hi", "thanks"]):
        intent = "chat"

    # 提取关键词
    keywords = query.replace("？", " ").replace("?", " ").replace("，", " ").split()
    keywords = [k.strip() for k in keywords if len(k.strip()) > 1]

    search_query = query
    if subject:
        search_query = subject.replace("_", " ")

    result = {
        "intent": intent,
        "extracted_keywords": keywords[:5],
        "extracted_subject": subject,
        "search_query": search_query,
        "iteration_count": state.get("iteration_count", 0) + 1,
        "need_more_info": False,
        "next_action": "search",
    }

    tracer.tool_end("node:understand_intent", f"intent={intent}, subject={subject}")
    return result


async def search_books_node(state: RecommendState) -> dict:
    """
    节点 2: 搜索书籍

    调用 SearchAgent 从 Open Library 获取书籍数据。
    """
    tracer = get_tracer()
    tracer.tool_start("node:search_books", {"query": state["search_query"]})

    search_query = state["search_query"]
    subject = state.get("extracted_subject")

    # 如果意图是聊天，跳过搜索
    if state["intent"] == "chat":
        tracer.tool_end("node:search_books", "skipped (chat intent)")
        return {
            "search_results": [],
            "search_total": 0,
            "next_action": "respond",
        }

    result = await search_books(
        query=search_query,
        limit=10,
        subject=subject,
    )

    books_dict = [
        {
            "title": b.title,
            "author": b.author,
            "publish_year": b.publish_year,
            "subjects": b.subjects[:5],
            "language": b.language,
            "open_library_key": b.open_library_key,
            "ratings_average": b.ratings_average,
            "cover_url": b.cover_url,
            "description": b.description[:200] if b.description else None,
        }
        for b in result.books
    ]

    tracer.tool_end("node:search_books", f"found {len(books_dict)} books")

    return {
        "search_results": books_dict,
        "search_total": result.total,
        "next_action": "analyze",
    }


async def analyze_preferences_node(state: RecommendState) -> dict:
    """
    节点 3: 分析用户偏好

    检查是否有足够信息进行推荐：
    - 搜索结果是否为空
    - 用户偏好是否明确
    - 是否需要追问
    """
    tracer = get_tracer()
    tracer.tool_start("node:analyze_preferences", {})

    search_results = state.get("search_results", [])
    intent = state["intent"]
    iteration = state.get("iteration_count", 1)

    # 如果搜索结果为空或太少，可能需要追问
    if intent == "recommend" and len(search_results) == 0:
        tracer.tool_end("node:analyze_preferences", "no results, need more info")
        return {
            "need_more_info": True,
            "next_action": "ask",
        }

    # 如果是推荐意图但信息太少，第一次迭代时追问
    if intent == "recommend" and iteration <= 1 and len(state["extracted_keywords"]) < 2:
        tracer.tool_end("node:analyze_preferences", "insufficient info, need more info")
        return {
            "need_more_info": True,
            "next_action": "ask",
        }

    # 如果意图是聊天，直接回复
    if intent == "chat":
        tracer.tool_end("node:analyze_preferences", "chat intent, respond directly")
        return {
            "need_more_info": False,
            "next_action": "respond",
        }

    # 尝试保存偏好
    if state.get("extracted_subject") or state.get("extracted_keywords"):
        await analyze_preferences(
            user_id=state["user_id"],
            summary=f"用户查询: {state['user_query']}",
            genres=[state["extracted_subject"]] if state.get("extracted_subject") else None,
        )

    tracer.tool_end("node:analyze_preferences", "preferences analyzed")
    return {
        "need_more_info": False,
        "next_action": "recommend",
    }


async def generate_recommendation_node(state: RecommendState) -> dict:
    """
    节点 4: 生成推荐

    基于搜索结果和用户偏好生成最终推荐。
    """
    tracer = get_tracer()
    tracer.tool_start("node:generate_recommendation", {})

    search_results = state.get("search_results", [])
    intent = state["intent"]
    query = state["user_query"]

    # 构建推荐理由
    if intent == "chat":
        message = (
            "你好！我是书灵，你的专业书籍推荐助手。\n"
            "我可以帮你：\n"
            "- 📚 搜索特定类型的书籍（如科幻、历史、推理等）\n"
            "- 🔍 查找特定作者或书名的书籍\n"
            "- 💡 根据你的偏好推荐书籍\n"
            "- 📖 查看书籍详细信息\n\n"
            "请告诉我你想找什么样的书，或者你最近在读什么？"
        )
        return {
            "final_recommendations": [],
            "reasoning": "用户问候",
            "assistant_message": message,
            "next_action": "done",
        }

    if len(search_results) == 0:
        message = (
            f'很抱歉，我暂时没有找到与"{query}"相关的书籍。\n'
            "你可以尝试：\n"
            "- 使用更通用的关键词\n"
            "- 告诉我你喜欢的题材类型\n"
            "- 分享你最近读过的好书，我来找类似的\n\n"
            "有什么我还可以帮你的吗？"
        )
        return {
            "final_recommendations": [],
            "reasoning": "未找到结果",
            "assistant_message": message,
            "next_action": "done",
        }

    # 格式化搜索结果
    books_text = format_books_for_llm(
        [
            Book(
                title=b["title"],
                author=b.get("author", "Unknown"),
                publish_year=b.get("publish_year"),
                subjects=b.get("subjects", []),
                language=b.get("language"),
                open_library_key=b.get("open_library_key", ""),
                ratings_average=b.get("ratings_average"),
                cover_url=b.get("cover_url"),
                description=b.get("description"),
            )
            for b in search_results[:5]
        ]
    )

    message = (
        f'根据你的需求，我找到了以下与"{query}"相关的书籍：\n\n'
        f"{books_text}\n\n"
        f"有没有你感兴趣的书？我可以帮你查看详细信息，或者根据你的偏好调整推荐。"
    )

    tracer.tool_end("node:generate_recommendation", f"generated for {len(search_results)} books")

    return {
        "final_recommendations": search_results[:5],
        "reasoning": f"基于用户查询 '{query}' 检索到 {len(search_results)} 本书",
        "assistant_message": message,
        "next_action": "done",
    }


async def ask_clarification_node(state: RecommendState) -> dict:
    """
    节点 5: 追问澄清

    当信息不足时，生成友好的追问。
    """
    tracer = get_tracer()
    tracer.tool_start("node:ask_clarification", {})

    query = state["user_query"]
    message = (
        f'了解！不过为了给你更精准的推荐，我还想多了解一点：\n\n'
        f'你提到的「{query[:30]}」，有没有特别偏好的方向呢？\n\n'
        f'比如：\n'
        f'- 📌 偏好什么题材？（科幻、奇幻、推理、历史、文学...）\n'
        f'- 📌 喜欢什么语言的书？（中文、英文...）\n'
        f'- 📌 之前读过哪些类似的书让你印象深刻？\n\n'
        f'或者直接告诉我更多细节，我会帮你找到最合适的书！'
    )

    tracer.tool_end("node:ask_clarification", "clarification asked")

    return {
        "assistant_message": message,
        "next_action": "wait_user",
    }


async def respond_chat_node(state: RecommendState) -> dict:
    """聊天意图的响应节点"""
    message = (
        "你好！我是书灵 📚\n\n"
        "我可以帮你搜索和推荐各种书籍。你可以：\n"
        "- 告诉我你想找什么类型的书\n"
        "- 描述你喜欢的阅读风格\n"
        "- 询问某本书的详细信息\n\n"
        "你现在想找什么样的书呢？"
    )
    return {
        "assistant_message": message,
        "next_action": "done",
    }


# ──────────────────────────────────────────────
# 路由函数
# ──────────────────────────────────────────────

def route_after_analyze(state: RecommendState) -> Literal["ask", "recommend", "respond"]:
    """分析后的路由判断"""
    if state.get("need_more_info", False):
        return "ask"
    if state.get("intent") == "chat":
        return "respond"
    return "recommend"


def route_after_recommend(state: RecommendState) -> Literal["__end__"]:
    """推荐后的路由（始终结束）"""
    return END


def route_after_ask(state: RecommendState) -> Literal["__end__"]:
    """追问后的路由（等待用户输入，结束本轮）"""
    return END


# ──────────────────────────────────────────────
# 工作流构建
# ──────────────────────────────────────────────

def build_recommend_graph() -> StateGraph:
    """
    构建 LangGraph 推荐工作流。

    返回编译后的 StateGraph，可作为独立引擎运行，
    也可嵌入 FastAPI 应用。
    """
    # 创建状态图
    workflow = StateGraph(RecommendState)

    # 添加节点
    workflow.add_node("understand_intent", understand_intent)
    workflow.add_node("search_books", search_books_node)
    workflow.add_node("analyze_preferences", analyze_preferences_node)
    workflow.add_node("generate_recommendation", generate_recommendation_node)
    workflow.add_node("ask_clarification", ask_clarification_node)
    workflow.add_node("respond_chat", respond_chat_node)

    # 添加边
    workflow.set_entry_point("understand_intent")

    # understand_intent → search_books
    workflow.add_edge("understand_intent", "search_books")

    # search_books → analyze_preferences
    workflow.add_edge("search_books", "analyze_preferences")

    # analyze_preferences → 条件路由
    workflow.add_conditional_edges(
        "analyze_preferences",
        route_after_analyze,
        {
            "ask": "ask_clarification",
            "recommend": "generate_recommendation",
            "respond": "respond_chat",
        },
    )

    # 终端节点 → END
    workflow.add_edge("generate_recommendation", END)
    workflow.add_edge("ask_clarification", END)
    workflow.add_edge("respond_chat", END)

    # 编译（使用内存检查点）
    memory = MemorySaver()
    compiled = workflow.compile(checkpointer=memory)

    return compiled


# 全局单例
_graph: Optional[StateGraph] = None


def get_recommend_graph() -> StateGraph:
    """获取全局工作流单例"""
    global _graph
    if _graph is None:
        _graph = build_recommend_graph()
    return _graph


# ──────────────────────────────────────────────
# 便捷执行函数
# ──────────────────────────────────────────────

async def run_recommend_workflow(
    user_query: str,
    conversation_id: str,
    user_id: str = "user_default",
) -> dict:
    """
    执行推荐工作流。

    这是一个独立的入口，不使用 Agent 的 LLM 对话功能，
    而是通过预定义的状态机逻辑进行书籍搜索和推荐。

    Args:
        user_query: 用户查询
        conversation_id: 对话 ID
        user_id: 用户 ID

    Returns:
        dict: 包含 assistant_message 和 recommendations 的结果
    """
    graph = get_recommend_graph()

    initial_state: RecommendState = {
        "user_query": user_query,
        "user_id": user_id,
        "conversation_id": conversation_id,
        "intent": "",
        "extracted_keywords": [],
        "extracted_subject": None,
        "search_query": user_query,
        "search_results": [],
        "search_total": 0,
        "user_preferences": None,
        "need_more_info": False,
        "final_recommendations": [],
        "reasoning": "",
        "assistant_message": "",
        "next_action": "start",
        "iteration_count": 0,
    }

    config = {"configurable": {"thread_id": conversation_id}}

    result = await graph.ainvoke(initial_state, config)

    return {
        "message": result.get("assistant_message", ""),
        "recommendations": result.get("final_recommendations", []),
        "reasoning": result.get("reasoning", ""),
        "next_action": result.get("next_action", "done"),
        "need_more_info": result.get("need_more_info", False),
    }
