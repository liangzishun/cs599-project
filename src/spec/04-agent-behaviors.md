# 04 - Agent 行为规格

## Agent 体系

系统包含两个协作 Agent：

### RecommendAgent（推荐代理）

**职责：** 理解用户意图、分析阅读偏好、生成个性化推荐

**能力：**
- 解析用户自然语言输入
- 判断用户意图（搜索 / 推荐 / 闲聊）
- 分析对话中体现的阅读偏好
- 整合搜索结果生成推荐
- 当信息不足时生成追问
- 为推荐提供合理解释

**触发条件：**
- 用户发送任何聊天消息
- LangGraph 工作流节点调用

**行为约束：**
- 始终以友好、专业的态度交流
- 推荐时提供具体理由
- 不确定时主动询问而非猜测
- 支持中文和英文

### SearchAgent（搜索代理）

**职责：** 调用书籍搜索工具，获取真实书籍数据

**能力：**
- 调用 Open Library API 进行关键词搜索
- 按不同维度过滤（作者、题材、年份、语言）
- 获取书籍详细信息
- 对搜索结果排序和去重

**工具列表：**
1. `search_books` - 关键词搜索书籍
2. `get_book_detail` - 获取单本书详情
3. `search_by_author` - 按作者搜索
4. `search_by_subject` - 按题材搜索

## 工具定义（Function Calling）

系统向 Anthropic Claude API 注册以下工具：

### tool: search_books
```json
{
  "name": "search_books",
  "description": "搜索书籍，支持书名、作者、关键词搜索。返回匹配的书籍列表。",
  "parameters": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "搜索关键词"
      },
      "limit": {
        "type": "integer",
        "description": "返回结果数量限制，默认10",
        "default": 10
      },
      "subject": {
        "type": "string",
        "description": "按题材过滤，如 'science_fiction', 'fantasy', 'history'"
      },
      "language": {
        "type": "string",
        "description": "按语言过滤，如 'chi', 'eng'"
      }
    },
    "required": ["query"]
  }
}
```

### tool: get_book_detail
```json
{
  "name": "get_book_detail",
  "description": "获取指定书籍的详细信息，包括简介、评分、出版信息等。",
  "parameters": {
    "type": "object",
    "properties": {
      "open_library_key": {
        "type": "string",
        "description": "Open Library 的工作 ID，如 '/works/OL1234567W'"
      }
    },
    "required": ["open_library_key"]
  }
}
```

### tool: analyze_preferences
```json
{
  "name": "analyze_preferences",
  "description": "分析用户在对话中体现的阅读偏好，存入长期记忆。",
  "parameters": {
    "type": "object",
    "properties": {
      "user_id": {
        "type": "string",
        "description": "用户标识"
      },
      "genres": {
        "type": "array",
        "items": {"type": "string"},
        "description": "用户感兴趣的题材"
      },
      "authors": {
        "type": "array",
        "items": {"type": "string"},
        "description": "用户提到的作者"
      },
      "language_preference": {
        "type": "string",
        "description": "语言偏好"
      },
      "summary": {
        "type": "string",
        "description": "对用户偏好的自然语言总结"
      }
    },
    "required": ["user_id", "summary"]
  }
}
```

## 对话流程规范

### 正常推荐流程
```
用户: "帮我推荐一些科幻小说"
  ↓
Agent: 识别意图为"推荐"，题材为"科幻"
  ↓
Agent: 调用 search_books(query="science fiction", subject="science_fiction")
  ↓
Agent: [收到书单] 分析并筛选
  ↓
Agent: "根据你的需求，我推荐以下几本科幻小说：《三体》- 刘慈欣的硬科幻巨作..."
  ↓
Agent: 调用 analyze_preferences 保存偏好
```

### 信息不足流程
```
用户: "推荐一些书"
  ↓
Agent: 识别意图为"推荐"，但信息不足
  ↓
Agent: "当然！为了给你更精准的推荐，能告诉我你喜欢什么类型的书吗？比如科幻、文学、历史..."
  ↓
用户: "历史的吧"
  ↓
Agent: 继续搜索推荐
```

### 多轮记忆流程
```
用户: "之前推荐的《三体》类似的书还有吗？"
  ↓
Agent: 从对话记忆中检索之前推荐过《三体》
  ↓
Agent: 从 ChromaDB 检索用户偏好
  ↓
Agent: 搜索相似书籍并推荐
```
