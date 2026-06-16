"""
偏好分析工具 —— 分析用户阅读偏好

提供 analyze_preferences 函数，供 LLM function calling 调用，
将分析结果存入 ChromaDB 长期记忆。
"""

from typing import Optional

from src.backend.models.schemas import UserPreference
from src.backend.observability.tracer import get_tracer


async def analyze_preferences(
    user_id: str,
    summary: str = "",
    genres: Optional[list[str]] = None,
    authors: Optional[list[str]] = None,
    language_preference: Optional[str] = None,
) -> dict:
    """
    分析用户在对话中体现的阅读偏好，存入长期记忆。

    此函数被设计为可供 LLM Function Calling 调用的工具。

    Args:
        user_id: 用户标识
        summary: 用户偏好的自然语言总结（必填）
        genres: 用户感兴趣的题材
        authors: 用户提到的作者
        language_preference: 语言偏好

    Returns:
        包含分析结果的字典
    """
    tracer = get_tracer()
    tracer.tool_start("analyze_preferences", {
        "user_id": user_id,
        "genres": genres,
        "authors": authors,
        "language": language_preference,
    })

    # 构建偏好对象
    preference = UserPreference(
        user_id=user_id,
        preferred_genres=genres or [],
        preferred_authors=authors or [],
        preferred_languages=[language_preference] if language_preference else [],
        free_text_summary=summary,
    )

    # 存储到向量数据库（延迟导入避免循环依赖）
    try:
        from src.backend.memory.vector_store import get_vector_store
        vector_store = get_vector_store()
        vector_store.store_preference(preference)
        tracer.tool_end("analyze_preferences", "stored successfully")
    except Exception as e:
        tracer.tool_error("analyze_preferences", str(e))

    return {
        "status": "success",
        "user_id": user_id,
        "analyzed_preferences": {
            "genres": preference.preferred_genres,
            "authors": preference.preferred_authors,
            "languages": preference.preferred_languages,
            "summary": summary,
        },
    }


async def get_user_preferences(user_id: str) -> Optional[UserPreference]:
    """从向量数据库检索用户偏好"""
    try:
        from src.backend.memory.vector_store import get_vector_store
        vector_store = get_vector_store()
        return vector_store.get_preferences(user_id)
    except Exception:
        return None
