# 02 - API 接口规格

## 基础信息

- 协议：HTTP/1.1
- 格式：JSON
- 流式响应：Server-Sent Events (SSE)
- 编码：UTF-8

## 接口列表

### POST /api/chat

发送消息给 AI Agent，获取流式推荐回复。

**Request:**
```json
{
  "message": "我想找一些科幻小说",
  "conversation_id": "conv_abc123",
  "user_id": "user_default"
}
```

**Response:** SSE 流
```
data: {"type": "thinking", "content": "正在分析你的需求..."}
data: {"type": "tool_call", "name": "book_search", "args": {"query": "science fiction"}}
data: {"type": "tool_result", "name": "book_search", "result": [...]}
data: {"type": "message", "content": "我为你找到以下几本科幻小说..."}
data: {"type": "recommendations", "books": [...]}
data: {"type": "done"}
```

**SSE 事件类型:**

| type | 描述 |
|------|------|
| `thinking` | AI 正在思考/处理 |
| `tool_call` | AI 调用了工具 |
| `tool_result` | 工具返回结果 |
| `message` | AI 文本回复（增量） |
| `recommendations` | 最终推荐书籍列表 |
| `error` | 错误信息 |
| `done` | 流结束 |

### POST /api/search

直接搜索书籍，不走 AI Agent。

**Request:**
```json
{
  "query": "三体",
  "limit": 10,
  "page": 1
}
```

**Response:**
```json
{
  "total": 25,
  "page": 1,
  "books": [
    {
      "title": "三体",
      "author": "刘慈欣",
      "cover_url": "https://covers.openlibrary.org/...",
      "publish_year": 2008,
      "subjects": ["Science Fiction"],
      "description": "...",
      "open_library_key": "/works/OL..."
    }
  ]
}
```

### GET /api/conversations

获取所有对话会话列表。

**Response:**
```json
{
  "conversations": [
    {
      "id": "conv_abc123",
      "title": "科幻小说推荐",
      "created_at": "2026-06-10T10:00:00Z",
      "message_count": 8
    }
  ]
}
```

### GET /api/conversations/{conversation_id}

获取特定对话的完整历史。

**Response:**
```json
{
  "id": "conv_abc123",
  "messages": [
    {"role": "user", "content": "我想找一些科幻小说", "timestamp": "..."},
    {"role": "assistant", "content": "我为你找到...", "timestamp": "..."}
  ]
}
```

### DELETE /api/conversations/{conversation_id}

删除指定对话。

**Response:**
```json
{
  "status": "deleted",
  "conversation_id": "conv_abc123"
}
```

## 错误响应格式

```json
{
  "error": {
    "code": "INVALID_REQUEST",
    "message": "请求参数无效",
    "detail": "'message' 字段不能为空"
  }
}
```

**错误码:**

| Code | HTTP Status | 描述 |
|------|-------------|------|
| `INVALID_REQUEST` | 400 | 请求参数无效 |
| `NOT_FOUND` | 404 | 资源不存在 |
| `LLM_ERROR` | 502 | LLM 调用失败 |
| `INTERNAL_ERROR` | 500 | 服务器内部错误 |
