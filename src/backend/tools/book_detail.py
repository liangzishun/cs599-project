"""
书籍详情工具 —— 对 search_books 结果的增强处理

提供与 Open Library API 交互的辅助函数。
"""

from src.backend.tools.book_search import search_books, get_book_detail, search_by_author, search_by_subject

# 重新导出，方便统一引用
__all__ = ["search_books", "get_book_detail", "search_by_author", "search_by_subject"]
