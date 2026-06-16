"""
书籍搜索工具 —— 调用 Open Library API

提供：search_books, get_book_detail, search_by_author, search_by_subject
"""

from typing import Optional
import httpx

from src.backend.config import get_config
from src.backend.models.schemas import Book, SearchResult
from src.backend.observability.tracer import get_tracer


async def search_books(
    query: str,
    limit: int = 10,
    subject: Optional[str] = None,
    language: Optional[str] = None,
    page: int = 1,
) -> SearchResult:
    """
    搜索书籍，支持书名、作者、关键词搜索。

    Args:
        query: 搜索关键词
        limit: 返回结果数量限制
        subject: 按题材过滤
        language: 按语言过滤
        page: 页码

    Returns:
        SearchResult 包含匹配的书籍列表
    """
    tracer = get_tracer()
    tracer.tool_start("search_books", {"query": query, "limit": limit, "subject": subject})

    config = get_config()
    base_url = config.open_library_base_url

    # 构建搜索查询
    search_query = query
    search_params: dict[str, str | int] = {
        "q": search_query,
        "limit": limit,
        "offset": (page - 1) * limit,
        "fields": "key,title,author_name,first_publish_year,publisher,isbn,subject,language,cover_edition_key,ratings_average,ratings_count",
    }

    # 添加题材过滤
    if subject:
        search_params["subject"] = subject

    # 添加语言过滤
    if language:
        search_params["language"] = language

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(f"{base_url}/search.json", params=search_params)
            response.raise_for_status()
            data = response.json()

        books: list[Book] = []
        for doc in data.get("docs", []):
            book = _parse_open_library_doc(doc, config)
            if book.title:  # 至少需要书名
                books.append(book)

        result = SearchResult(
            query=query,
            total=data.get("numFound", len(books)),
            page=page,
            limit=limit,
            books=books,
        )

        tracer.tool_end("search_books", f"found {len(books)} books out of {result.total}")
        return result

    except httpx.HTTPError as e:
        tracer.tool_error("search_books", str(e))
        return SearchResult(query=query)
    except Exception as e:
        tracer.tool_error("search_books", str(e))
        return SearchResult(query=query)


async def get_book_detail(open_library_key: str) -> Optional[Book]:
    """
    获取指定书籍的详细信息。

    Args:
        open_library_key: Open Library 工作 ID，如 '/works/OL1234567W'

    Returns:
        Book 对象或 None
    """
    tracer = get_tracer()
    tracer.tool_start("get_book_detail", {"key": open_library_key})

    config = get_config()
    base_url = config.open_library_base_url

    # 确保 key 格式正确
    key = open_library_key.strip("/")
    if not key.startswith("works/"):
        key = f"works/{key}"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(f"{base_url}/{key}.json")
            response.raise_for_status()
            data = response.json()

        book = Book(
            title=data.get("title", "Unknown"),
            author="Unknown",  # 需要从 authors 获取
            open_library_key=f"/{key}",
            description=_extract_description(data),
            subjects=data.get("subjects", []),
            publish_year=data.get("first_publish_date", None),
        )

        # 获取作者信息
        if "authors" in data:
            authors = []
            for author_ref in data["authors"]:
                author_key = author_ref.get("author", {}).get("key", "")
                if author_key:
                    author_name = await _get_author_name(author_key, client, base_url)
                    if author_name:
                        authors.append(author_name)
            if authors:
                book.author = ", ".join(authors)

        # 获取封面
        if "covers" in data and data["covers"]:
            cover_id = data["covers"][0]
            book.cover_url = f"{config.open_library_covers_url}/b/id/{cover_id}-M.jpg"

        tracer.tool_end("get_book_detail", f"fetched: {book.title}")
        return book

    except httpx.HTTPError as e:
        tracer.tool_error("get_book_detail", str(e))
        return None
    except Exception as e:
        tracer.tool_error("get_book_detail", str(e))
        return None


async def search_by_author(author_name: str, limit: int = 10) -> SearchResult:
    """按作者搜索书籍"""
    return await search_books(f"author:{author_name}", limit=limit)


async def search_by_subject(subject: str, limit: int = 10) -> SearchResult:
    """按题材搜索书籍"""
    return await search_books(f"subject:{subject}", limit=limit, subject=subject)


# ──────────────────────────────────────────────
# 内部辅助函数
# ──────────────────────────────────────────────

def _parse_open_library_doc(doc: dict, config) -> Book:
    """将 Open Library 搜索结果的 doc 转为 Book 对象"""
    cover_url = None
    if doc.get("cover_edition_key"):
        cover_url = f"{config.open_library_covers_url}/b/olid/{doc['cover_edition_key']}-M.jpg"
    elif doc.get("cover_i"):
        cover_url = f"{config.open_library_covers_url}/b/id/{doc['cover_i']}-M.jpg"

    authors = doc.get("author_name", ["Unknown"])
    author_str = ", ".join(authors) if isinstance(authors, list) else str(authors)

    subjects = doc.get("subject", [])
    if isinstance(subjects, str):
        subjects = [subjects]

    # 处理语言字段
    languages = doc.get("language", [])
    language = languages[0] if languages else None

    # 处理 ISBN
    isbn = None
    isbn_list = doc.get("isbn", [])
    if isbn_list:
        isbn = isbn_list[0] if isinstance(isbn_list, list) else str(isbn_list)

    return Book(
        title=doc.get("title", "Unknown"),
        author=author_str,
        cover_url=cover_url,
        publish_year=doc.get("first_publish_year"),
        publisher=doc.get("publisher", [None])[0] if doc.get("publisher") else None,
        isbn=isbn,
        subjects=subjects[:10],
        language=language,
        open_library_key=doc.get("key", ""),
        ratings_average=doc.get("ratings_average"),
        ratings_count=doc.get("ratings_count"),
    )


def _extract_description(data: dict) -> Optional[str]:
    """从 Open Library 作品数据中提取描述"""
    desc = data.get("description", None)
    if isinstance(desc, dict):
        return desc.get("value", str(desc))
    if isinstance(desc, str):
        return desc
    return None


async def _get_author_name(
    author_key: str, client: httpx.AsyncClient, base_url: str
) -> Optional[str]:
    """获取作者名称"""
    try:
        response = await client.get(f"{base_url}{author_key}.json")
        response.raise_for_status()
        data = response.json()
        return data.get("name", None)
    except Exception:
        return None
