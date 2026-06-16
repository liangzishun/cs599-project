"""
Pydantic 数据模型 —— 可执行规格

所有 API 请求/响应、内部状态的数据结构定义在此。
"""

from datetime import datetime
from typing import Literal, Optional, Any
from uuid import uuid4

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────
# 书籍相关
# ──────────────────────────────────────────────

class Book(BaseModel):
    """书籍信息"""
    title: str
    author: str = "Unknown"
    cover_url: Optional[str] = None
    publish_year: Optional[int] = None
    publisher: Optional[str] = None
    isbn: Optional[str] = None
    subjects: list[str] = Field(default_factory=list)
    description: Optional[str] = None
    language: Optional[str] = None
    open_library_key: str = ""
    ratings_average: Optional[float] = None
    ratings_count: Optional[int] = None


class SearchResult(BaseModel):
    """搜索结果"""
    query: str
    total: int = 0
    page: int = 1
    limit: int = 10
    books: list[Book] = Field(default_factory=list)


class RecommendationResult(BaseModel):
    """推荐结果"""
    books: list[Book] = Field(default_factory=list)
    reasoning: str = ""
    conversation_id: str = ""
    user_preferences_used: list[str] = Field(default_factory=list)


# ──────────────────────────────────────────────
# 消息 & 对话
# ──────────────────────────────────────────────

class ToolCall(BaseModel):
    """工具调用记录"""
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    """工具返回记录"""
    tool_call_id: str
    name: str
    result: Any = None
    error: Optional[str] = None


class Message(BaseModel):
    """对话消息"""
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)
    tool_calls: Optional[list[ToolCall]] = None
    tool_results: Optional[list[ToolResult]] = None


class Conversation(BaseModel):
    """对话会话"""
    id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str = "user_default"
    title: str = "新对话"
    messages: list[Message] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    def add_message(self, message: Message) -> None:
        self.messages.append(message)
        self.updated_at = datetime.now()
        # 自动用第一条用户消息作为标题
        if len(self.messages) == 1 and message.role == "user":
            self.title = message.content[:30] + ("..." if len(message.content) > 30 else "")


class ConversationListItem(BaseModel):
    """对话列表项"""
    id: str
    title: str
    created_at: datetime
    message_count: int


# ──────────────────────────────────────────────
# 用户偏好
# ──────────────────────────────────────────────

class UserPreference(BaseModel):
    """用户阅读偏好"""
    user_id: str = "user_default"
    preferred_genres: list[str] = Field(default_factory=list)
    preferred_authors: list[str] = Field(default_factory=list)
    preferred_languages: list[str] = Field(default_factory=list)
    reading_level: Optional[str] = None
    preferred_era: Optional[str] = None
    free_text_summary: str = ""
    last_updated: datetime = Field(default_factory=datetime.now)


# ──────────────────────────────────────────────
# API 请求 / 响应
# ──────────────────────────────────────────────

class ChatRequest(BaseModel):
    """对话请求"""
    message: str = Field(..., min_length=1, max_length=2000)
    conversation_id: Optional[str] = None
    user_id: str = "user_default"


class SearchRequest(BaseModel):
    """搜索请求"""
    query: str = Field(..., min_length=1, max_length=500)
    limit: int = Field(default=10, ge=1, le=50)
    page: int = Field(default=1, ge=1)


class ConversationListResponse(BaseModel):
    """对话列表响应"""
    conversations: list[ConversationListItem]


class ConversationDetailResponse(BaseModel):
    """对话详情响应"""
    id: str
    messages: list[Message]


class ErrorResponse(BaseModel):
    """错误响应"""
    error: dict[str, str]
