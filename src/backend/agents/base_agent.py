"""
Agent 基类 —— 封装 LLM API 调用（OpenAI 兼容接口）

支持 OpenAI / SiliconFlow / DeepSeek 等兼容 API。
提供 Function Calling、流式响应、错误重试。
"""

import json
from typing import AsyncGenerator, Optional

from openai import AsyncOpenAI

from src.backend.config import get_config
from src.backend.observability.tracer import get_tracer

# ──────────────────────────────────────────────
# 工具定义（OpenAI Function Calling 格式）
# ──────────────────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_books",
            "description": "搜索书籍，支持书名、作者、关键词搜索。返回匹配的真实书籍列表，包含书名、作者、出版年份、简介等信息。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词，可以是书名、作者名、或题材关键词",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回结果数量限制，默认10，最大20",
                        "default": 10,
                    },
                    "subject": {
                        "type": "string",
                        "description": "按题材过滤，如 'science_fiction', 'fantasy', 'history', 'mystery'",
                    },
                    "language": {
                        "type": "string",
                        "description": "按语言过滤，如 'chi' 表示中文, 'eng' 表示英文",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_book_detail",
            "description": "获取指定书籍的详细信息，包括详细简介、评分、出版信息、封面等。在用户询问某本书的详细情况时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "open_library_key": {
                        "type": "string",
                        "description": "Open Library 的工作 ID，如 '/works/OL1234567W'",
                    }
                },
                "required": ["open_library_key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_preferences",
            "description": "分析并保存用户在对话中体现的阅读偏好。在理解用户需求后调用此工具保存偏好信息到长期记忆。",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "用户标识",
                    },
                    "summary": {
                        "type": "string",
                        "description": "对用户阅读偏好的自然语言总结",
                    },
                    "genres": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "用户感兴趣的题材列表",
                    },
                    "authors": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "用户提到的作者列表",
                    },
                    "language_preference": {
                        "type": "string",
                        "description": "用户的语言偏好",
                    },
                },
                "required": ["user_id", "summary"],
            },
        },
    },
]

SYSTEM_PROMPT = """你是一个专业的书籍推荐助手，名叫「书灵」。你的目标是帮助用户找到他们真正想读的书。

## 你的能力
- 搜索真实书籍数据（通过工具调用 Open Library API）
- 分析用户的阅读偏好
- 提供个性化书籍推荐
- 用中文与用户交流（除非用户使用英文）

## 工作方式
1. 首先理解用户的阅读需求和偏好
2. 如果用户的信息不足以进行有效推荐，主动提问澄清
3. 使用 search_books 工具搜索匹配的书籍
4. 如果用户对某本书感兴趣，使用 get_book_detail 获取详细信息
5. 在对话结尾，使用 analyze_preferences 保存用户的阅读偏好
6. 给出推荐时要说明推荐理由

## 推荐原则
- 推荐 3-5 本书为宜，不要一次性列出太多
- 每本书简要说明推荐理由
- 注意书籍的多样性（如果用户没有明确偏好某个特定类型）
- 优先推荐评分较高的书籍
- 尊重用户的反馈，如果用户不喜欢某类书，不要再推荐

## 交流风格
- 友好、热情、专业
- 像一位懂书的朋友在和你聊天
- 适当提问以了解用户偏好
- 不要假装知道不存在的书籍，只推荐搜索到的真实书籍
"""


class BaseAgent:
    """Agent 基类 —— 封装与 OpenAI 兼容 API 的交互"""

    def __init__(self, name: str = "base"):
        self.name = name
        config = get_config()
        self._client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.api_base_url,
        )
        self._model = config.model

    async def chat_with_tools(
        self,
        messages: list[dict],
        tool_handler,
        system_prompt: Optional[str] = None,
        max_turns: int = 5,
    ) -> AsyncGenerator[dict, None]:
        """
        发送消息给 LLM 并处理工具调用（支持流式事件）。

        Args:
            messages: 对话消息列表 [{"role": "user", "content": "..."}]
            tool_handler: 工具调用处理函数 async (tool_name, arguments) -> result
            system_prompt: 系统提示词
            max_turns: 最大工具调用循环次数

        Yields:
            dict: 事件流 {"type": "thinking"|"tool_call"|"tool_result"|"message"|"done"|"error"}
        """
        tracer = get_tracer()
        tracer.llm_call_start(self._model, len(messages))

        try:
            # 构建完整消息列表（含 system prompt）
            full_messages = []
            if system_prompt or SYSTEM_PROMPT:
                full_messages.append({
                    "role": "system",
                    "content": system_prompt or SYSTEM_PROMPT,
                })
            full_messages.extend(messages)

            turn = 0

            while turn < max_turns:
                turn += 1

                yield {"type": "thinking", "content": "书灵正在思考..."}

                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=full_messages,
                    tools=TOOL_DEFINITIONS,
                    tool_choice="auto",
                    max_tokens=2000,
                    temperature=0.7,
                )

                choice = response.choices[0]
                msg = choice.message

                # 检查是否有工具调用
                if msg.tool_calls:
                    # 将 assistant 消息加入上下文
                    full_messages.append({
                        "role": "assistant",
                        "content": msg.content or "",
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                },
                            }
                            for tc in msg.tool_calls
                        ],
                    })

                    for tc in msg.tool_calls:
                        tool_name = tc.function.name
                        try:
                            tool_args = json.loads(tc.function.arguments)
                        except json.JSONDecodeError:
                            tool_args = {}

                        yield {
                            "type": "tool_call",
                            "name": tool_name,
                            "args": tool_args,
                            "id": tc.id,
                        }

                        # 执行工具
                        try:
                            result = await tool_handler(tool_name, tool_args)
                            yield {
                                "type": "tool_result",
                                "name": tool_name,
                                "result": result,
                                "id": tc.id,
                            }
                        except Exception as e:
                            result = {"error": str(e)}
                            yield {
                                "type": "tool_result",
                                "name": tool_name,
                                "result": result,
                                "id": tc.id,
                                "error": str(e),
                            }

                        # 将工具结果加入上下文
                        full_messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps(result, ensure_ascii=False),
                        })

                    yield {"type": "thinking", "content": "正在分析搜索结果..."}

                else:
                    # 没有工具调用，返回最终文本
                    text = msg.content or ""
                    tokens = response.usage.total_tokens if response.usage else 0
                    tracer.llm_call_end(self._model, tokens)

                    yield {"type": "message", "content": text}
                    yield {"type": "done"}
                    return

            # 超过最大轮次
            yield {"type": "message", "content": "抱歉，搜索过程需要更多时间。请尝试提供更具体的需求。"}
            yield {"type": "done"}

        except Exception as e:
            error_msg = str(e)
            tracer.tool_error(f"llm_{self.name}", error_msg)

            # 提供更友好的错误信息
            if "authentication" in error_msg.lower() or "401" in error_msg:
                error_msg = "API 认证失败，请检查 API Key 是否正确配置。"
            elif "rate" in error_msg.lower() or "429" in error_msg:
                error_msg = "请求过于频繁，请稍后再试。"
            elif "timeout" in error_msg.lower():
                error_msg = "请求超时，请检查网络连接后重试。"

            yield {"type": "error", "content": f"处理请求时出错: {error_msg}"}
            yield {"type": "done"}
