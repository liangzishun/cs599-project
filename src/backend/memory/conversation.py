"""
短期对话记忆管理

以会话 ID 为 key 的内存存储，管理对话历史和上下文窗口。
"""

from collections import deque
from datetime import datetime
from typing import Optional

from src.backend.models.schemas import (
    Conversation,
    ConversationListItem,
    Message,
    ToolCall,
    ToolResult,
)
from src.backend.observability.tracer import get_tracer


class ConversationMemory:
    """
    短期对话记忆

    特点：
    - 内存存储，重启后清空（长期记忆由 ChromaDB 负责）
    - 每个会话维护最近 N 轮对话
    - 支持滑动窗口，超过阈值自动摘要
    """

    def __init__(self, max_turns: int = 20, summary_threshold: int = 10):
        self._conversations: dict[str, Conversation] = {}
        self._max_turns = max_turns
        self._summary_threshold = summary_threshold

    def create_conversation(self, user_id: str = "user_default") -> Conversation:
        """创建新对话"""
        conv = Conversation(user_id=user_id)
        self._conversations[conv.id] = conv
        tracer = get_tracer()
        tracer.tool_start("create_conversation", {"id": conv.id, "user_id": user_id})
        tracer.tool_end("create_conversation", f"created {conv.id}")
        return conv

    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """获取指定对话"""
        return self._conversations.get(conversation_id)

    def get_or_create_conversation(
        self, conversation_id: Optional[str], user_id: str = "user_default"
    ) -> Conversation:
        """获取或创建对话"""
        if conversation_id and conversation_id in self._conversations:
            return self._conversations[conversation_id]
        return self.create_conversation(user_id)

    def add_message(self, conversation_id: str, message: Message) -> None:
        """添加消息到对话"""
        conv = self._conversations.get(conversation_id)
        if conv is None:
            return
        conv.add_message(message)

        # 检查是否需要压缩
        if len(conv.messages) > self._summary_threshold * 2:  # user + assistant
            self._maybe_summarize(conv)

    def add_user_message(self, conversation_id: str, content: str) -> Message:
        """添加用户消息"""
        message = Message(role="user", content=content)
        self.add_message(conversation_id, message)
        return message

    def add_assistant_message(
        self,
        conversation_id: str,
        content: str,
        tool_calls: Optional[list[ToolCall]] = None,
        tool_results: Optional[list[ToolResult]] = None,
    ) -> Message:
        """添加助手消息"""
        message = Message(
            role="assistant",
            content=content,
            tool_calls=tool_calls,
            tool_results=tool_results,
        )
        self.add_message(conversation_id, message)
        return message

    def get_messages(
        self, conversation_id: str, last_n: Optional[int] = None
    ) -> list[Message]:
        """获取对话消息，可选最近 N 条"""
        conv = self._conversations.get(conversation_id)
        if conv is None:
            return []
        messages = conv.messages
        if last_n and last_n < len(messages):
            return messages[-last_n:]
        return messages

    def get_context_for_llm(
        self, conversation_id: str, max_messages: int = 30
    ) -> list[dict]:
        """
        获取供 LLM 使用的对话上下文。

        返回 OpenAI/Anthropic 兼容的消息格式列表。
        """
        messages = self.get_messages(conversation_id, last_n=max_messages)
        context = []
        for msg in messages:
            context.append({"role": msg.role, "content": msg.content})
        return context

    def list_conversations(self) -> list[ConversationListItem]:
        """列出所有对话"""
        items = []
        for conv in self._conversations.values():
            items.append(ConversationListItem(
                id=conv.id,
                title=conv.title,
                created_at=conv.created_at,
                message_count=len(conv.messages),
            ))
        # 按创建时间倒序
        items.sort(key=lambda x: x.created_at, reverse=True)
        return items

    def delete_conversation(self, conversation_id: str) -> bool:
        """删除对话"""
        if conversation_id in self._conversations:
            del self._conversations[conversation_id]
            return True
        return False

    def _maybe_summarize(self, conv: Conversation) -> None:
        """当对话过长时进行压缩（保留最近的消息）"""
        # 简单策略：保留最近 N 轮对话
        keep_count = self._max_turns * 2  # user + assistant
        if len(conv.messages) > keep_count:
            # 保留前几条作为早期上下文，保留后几条作为近期上下文
            early = conv.messages[:2]  # 最早的用户问题
            recent = conv.messages[-keep_count:]
            conv.messages = early + recent


# 全局单例
_memory: Optional[ConversationMemory] = None


def get_conversation_memory() -> ConversationMemory:
    """获取全局对话记忆单例"""
    global _memory
    if _memory is None:
        _memory = ConversationMemory()
    return _memory
