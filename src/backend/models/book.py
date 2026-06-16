"""
书籍相关工具函数
"""

import re
from typing import Optional

from src.backend.models.schemas import Book


def format_book_display(book: Book) -> str:
    """格式化书籍信息用于展示"""
    parts = [f"**《{book.title}》**"]

    if book.author and book.author != "Unknown":
        parts.append(f"作者: {book.author}")

    if book.publish_year:
        parts.append(f"出版年份: {book.publish_year}")

    if book.publisher:
        parts.append(f"出版社: {book.publisher}")

    if book.subjects:
        subjects_str = ", ".join(book.subjects[:5])
        parts.append(f"分类: {subjects_str}")

    if book.language:
        lang_map = {
            "chi": "中文", "eng": "英文", "jpn": "日文",
            "fre": "法文", "ger": "德文", "spa": "西班牙文"
        }
        lang_display = lang_map.get(book.language, book.language)
        parts.append(f"语言: {lang_display}")

    if book.ratings_average:
        parts.append(f"评分: {book.ratings_average:.1f}/5")

    if book.description:
        desc = _truncate_text(book.description, 200)
        parts.append(f"简介: {desc}")

    return " | ".join(parts)


def format_books_for_llm(books: list[Book], max_books: int = 10) -> str:
    """将书籍列表格式化为 LLM 可读文本"""
    if not books:
        return "未找到匹配的书籍。"

    lines = []
    for i, book in enumerate(books[:max_books], 1):
        lines.append(format_book_display(book))
        lines.append("")  # 空行分隔

    return "\n".join(lines)


def extract_subject_from_query(query: str) -> Optional[str]:
    """从查询中提取可能的题材关键词"""
    subject_map = {
        "科幻": "science_fiction",
        "科学幻想": "science_fiction",
        "玄幻": "fantasy",
        "奇幻": "fantasy",
        "魔法": "fantasy",
        "历史": "history",
        "历史小说": "historical_fiction",
        "推理": "mystery",
        "侦探": "mystery",
        "悬疑": "thriller",
        "恐怖": "horror",
        "爱情": "romance",
        "言情": "romance",
        "传记": "biography",
        "自传": "biography",
        "诗歌": "poetry",
        "诗": "poetry",
        "哲学": "philosophy",
        "心理": "psychology",
        "科学": "science",
        "科普": "science",
        "经济": "economics",
        "商业": "business",
        "编程": "programming",
        "计算机": "computer_science",
        "小说": "fiction",
        "文学": "literature",
    }
    for cn_name, en_name in subject_map.items():
        if cn_name in query:
            return en_name
    return None


def _truncate_text(text: str, max_length: int) -> str:
    """截断文本并添加省略号"""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3].rstrip() + "..."
