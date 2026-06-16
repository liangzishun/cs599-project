"""
测试：工具层

验证 Open Library API 搜索和书籍详情获取。
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.backend.tools.book_search import search_books, get_book_detail
from src.backend.tools.preference_analyzer import analyze_preferences
from src.backend.models.schemas import Book, SearchResult
from src.backend.models.book import extract_subject_from_query, format_book_display


@pytest.mark.asyncio
async def test_search_books_basic():
    """测试基本书籍搜索"""
    result = await search_books("The Lord of the Rings", limit=5)
    assert isinstance(result, SearchResult)
    assert len(result.books) > 0
    assert result.query == "The Lord of the Rings"


@pytest.mark.asyncio
async def test_search_books_with_subject():
    """测试按题材过滤"""
    result = await search_books("dragon", subject="fantasy", limit=5)
    assert isinstance(result, SearchResult)
    # 不一定有结果，但不应报错


@pytest.mark.asyncio
async def test_search_books_chinese():
    """测试中文搜索"""
    result = await search_books("三体", limit=5)
    assert isinstance(result, SearchResult)
    # Open Library 可能找不到中文书，但不影响流程


@pytest.mark.asyncio
async def test_get_book_detail_invalid_key():
    """测试无效 key 的书籍详情"""
    result = await get_book_detail("/works/INVALID_KEY_12345")
    assert result is None


@pytest.mark.asyncio
async def test_search_empty_query():
    """测试空查询"""
    result = await search_books("", limit=5)
    assert isinstance(result, SearchResult)


def test_extract_subject_from_query():
    """测试从查询提取题材"""
    assert extract_subject_from_query("科幻小说推荐") == "science_fiction"
    assert extract_subject_from_query("历史书籍") == "history"
    assert extract_subject_from_query("随便看看") is None
    assert extract_subject_from_query("推理侦探小说") == "mystery"


def test_format_book_display():
    """测试书籍信息格式化"""
    book = Book(
        title="Test Book",
        author="Test Author",
        publish_year=2020,
        subjects=["Fiction", "Science"],
        language="eng",
        open_library_key="/works/OL123W",
    )
    display = format_book_display(book)
    assert "Test Book" in display
    assert "Test Author" in display
    assert "2020" in display


@pytest.mark.asyncio
async def test_analyze_preferences():
    """测试偏好分析"""
    result = await analyze_preferences(
        user_id="test_user",
        summary="喜欢硬科幻和推理小说",
        genres=["science_fiction", "mystery"],
        authors=["刘慈欣"],
        language_preference="chi",
    )
    assert result["status"] == "success"
    assert result["user_id"] == "test_user"
    assert "science_fiction" in result["analyzed_preferences"]["genres"]
