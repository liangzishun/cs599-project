"""
推荐 Agent —— 理解用户意图、生成推荐

核心 Agent，负责：
1. 与用户对话交互
2. 调用工具搜索书籍
3. 分析偏好
4. 生成推荐结果
"""

import json
from typing import AsyncGenerator, Optional

from src.backend.agents.base_agent import BaseAgent, SYSTEM_PROMPT
from src.backend.models.schemas import Book, SearchResult, UserPreference
from src.backend.models.book import format_books_for_llm
from src.backend.tools.book_search import search_books, get_book_detail
from src.backend.tools.preference_analyzer import analyze_preferences, get_user_preferences
from src.backend.memory.conversation import get_conversation_memory
from src.backend.observability.tracer import get_tracer


class RecommendAgent:
    """
    推荐代理

    封装完整的推荐对话流程：
    - 初始化对话上下文
    - 调用 LLM 进行多轮推理
    - 处理工具调用
    - 生成推荐结果
    """

    def __init__(self):
        self.name = "recommend_agent"
        self._base_agent = BaseAgent(name=self.name)

    async def chat_stream(
        self,
        user_message: str,
        conversation_id: str,
        user_id: str = "user_default",
    ) -> AsyncGenerator[dict, None]:
        """
        流式对话入口

        每次用户发送消息时调用，处理完整的多轮 Agent 推理。

        Args:
            user_message: 用户输入
            conversation_id: 对话 ID
            user_id: 用户 ID

        Yields:
            dict: SSE 事件
        """
        tracer = get_tracer()
        tracer.request_start("chat_stream", {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "message_length": len(user_message),
        })

        memory = get_conversation_memory()

        # 添加用户消息到记忆
        memory.add_user_message(conversation_id, user_message)

        # 获取对话上下文
        context = memory.get_context_for_llm(conversation_id)

        # 获取用户历史偏好
        preferences = await get_user_preferences(user_id)
        preference_context = self._build_preference_context(preferences)

        # 构建消息列表（附带偏好上下文）
        enhanced_messages = list(context)
        if preference_context:
            # 在第一条消息前插入偏好信息
            enhanced_messages.insert(0, {
                "role": "user",
                "content": f"[系统信息：以下是根据历史记录分析的用户阅读偏好]\n{preference_context}",
            })

        # 调用 LLM 进行对话
        async for event in self._base_agent.chat_with_tools(
            messages=enhanced_messages,
            tool_handler=self._handle_tool_call,
            system_prompt=SYSTEM_PROMPT,
        ):
            yield event

            # 如果是最终消息，保存到对话记忆
            if event["type"] == "message":
                memory.add_assistant_message(conversation_id, event["content"])
            elif event["type"] == "error":
                memory.add_assistant_message(
                    conversation_id,
                    f"[错误] {event['content']}",
                )

        tracer.request_end("chat_stream", 200, 0)

    async def _handle_tool_call(self, tool_name: str, arguments: dict):
        """处理工具调用 —— 路由到对应的工具函数"""
        tracer = get_tracer()
        tracer.tool_start(f"handle_{tool_name}", arguments)

        try:
            if tool_name == "search_books":
                result = await search_books(
                    query=arguments.get("query", ""),
                    limit=arguments.get("limit", 10),
                    subject=arguments.get("subject"),
                    language=arguments.get("language"),
                )
                # 格式化为 LLM 可读文本
                return {
                    "success": True,
                    "total": result.total,
                    "books": format_books_for_llm(result.books),
                    "raw_books": [
                        {
                            "title": b.title,
                            "author": b.author,
                            "publish_year": b.publish_year,
                            "subjects": b.subjects,
                            "language": b.language,
                            "open_library_key": b.open_library_key,
                            "ratings_average": b.ratings_average,
                        }
                        for b in result.books
                    ],
                }

            elif tool_name == "get_book_detail":
                book = await get_book_detail(
                    open_library_key=arguments.get("open_library_key", "")
                )
                if book:
                    return {
                        "success": True,
                        "title": book.title,
                        "author": book.author,
                        "description": book.description,
                        "publish_year": book.publish_year,
                        "publisher": book.publisher,
                        "subjects": book.subjects,
                        "language": book.language,
                        "ratings_average": book.ratings_average,
                        "cover_url": book.cover_url,
                    }
                else:
                    return {"success": False, "error": "未找到该书详情"}

            elif tool_name == "analyze_preferences":
                result = await analyze_preferences(
                    user_id=arguments.get("user_id", "user_default"),
                    summary=arguments.get("summary", ""),
                    genres=arguments.get("genres"),
                    authors=arguments.get("authors"),
                    language_preference=arguments.get("language_preference"),
                )
                return result

            else:
                return {"success": False, "error": f"未知工具: {tool_name}"}

        except Exception as e:
            tracer.tool_error(f"handle_{tool_name}", str(e))
            return {"success": False, "error": str(e)}

    def _build_preference_context(self, preferences: Optional[UserPreference]) -> str:
        """将用户偏好格式化为上下文文本"""
        if preferences is None:
            return ""

        parts = ["用户阅读偏好记录："]
        if preferences.preferred_genres:
            parts.append(f"- 偏好题材: {', '.join(preferences.preferred_genres)}")
        if preferences.preferred_authors:
            parts.append(f"- 偏好作者: {', '.join(preferences.preferred_authors)}")
        if preferences.preferred_languages:
            parts.append(f"- 偏好语言: {', '.join(preferences.preferred_languages)}")
        if preferences.free_text_summary:
            parts.append(f"- 偏好总结: {preferences.free_text_summary}")

        return "\n".join(parts) if len(parts) > 1 else ""
