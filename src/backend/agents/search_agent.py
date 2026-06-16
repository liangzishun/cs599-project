"""
搜索 Agent —— 执行书籍搜索任务

负责调用 Open Library API 工具，搜索书籍数据。
可以作为独立 Agent 使用，也可以被 LangGraph 工作流调用。
"""

from typing import Optional

from src.backend.agents.base_agent import BaseAgent
from src.backend.models.schemas import Book, SearchResult
from src.backend.tools.book_search import search_books, get_book_detail, search_by_subject
from src.backend.observability.tracer import get_tracer


class SearchAgent:
    """
    搜索代理

    职责：
    - 解析搜索需求
    - 调用 Open Library API
    - 整理和过滤搜索结果
    """

    def __init__(self):
        self.name = "search_agent"

    async def search(
        self,
        query: str,
        limit: int = 10,
        subject: Optional[str] = None,
        language: Optional[str] = None,
    ) -> SearchResult:
        """
        执行书籍搜索

        Args:
            query: 搜索关键词
            limit: 返回数量限制
            subject: 题材过滤
            language: 语言过滤

        Returns:
            SearchResult 包含书籍列表
        """
        tracer = get_tracer()
        tracer.tool_start("search_agent.search", {
            "query": query, "limit": limit, "subject": subject, "language": language
        })

        result = await search_books(
            query=query,
            limit=limit,
            subject=subject,
            language=language,
        )

        tracer.tool_end("search_agent.search", f"found {len(result.books)} books")
        return result

    async def search_by_genre(self, genre: str, limit: int = 10) -> SearchResult:
        """按题材搜索"""
        return await search_by_subject(genre, limit=limit)

    async def get_detail(self, open_library_key: str) -> Optional[Book]:
        """获取书籍详情"""
        return await get_book_detail(open_library_key)

    async def execute_plan(self, search_plan: dict) -> SearchResult:
        """
        执行搜索计划（从 RecommendAgent 生成的计划中提取参数）

        Args:
            search_plan: 搜索计划 {"query": "...", "limit": ..., "subject": "..."}

        Returns:
            SearchResult
        """
        query = search_plan.get("query", "")
        limit = search_plan.get("limit", 10)
        subject = search_plan.get("subject")
        language = search_plan.get("language")

        return await self.search(
            query=query,
            limit=limit,
            subject=subject,
            language=language,
        )
