# 03 - 数据模型定义

## 核心实体

### Book（书籍）

```python
class Book(BaseModel):
    title: str                          # 书名
    author: str                         # 作者
    cover_url: Optional[str]            # 封面图片 URL
    publish_year: Optional[int]         # 出版年份
    publisher: Optional[str]            # 出版社
    isbn: Optional[str]                 # ISBN
    subjects: list[str]                 # 主题/分类
    description: Optional[str]          # 简介
    language: Optional[str]             # 语言
    open_library_key: str               # Open Library 唯一标识
    ratings_average: Optional[float]    # 平均评分
    ratings_count: Optional[int]        # 评分数量
```

### Message（消息）

```python
class Message(BaseModel):
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    timestamp: datetime
    tool_calls: Optional[list[ToolCall]]
    tool_results: Optional[list[ToolResult]]
```

### Conversation（对话）

```python
class Conversation(BaseModel):
    id: str                             # UUID
    user_id: str                        # 用户标识
    title: str                          # 对话标题
    messages: list[Message]             # 消息列表
    created_at: datetime
    updated_at: datetime
```

### UserPreference（用户偏好）

```python
class UserPreference(BaseModel):
    user_id: str
    preferred_genres: list[str]         # 偏好题材
    preferred_authors: list[str]        # 偏好作者
    preferred_languages: list[str]      # 偏好语言
    reading_level: Optional[str]        # 阅读水平
    preferred_era: Optional[str]        # 偏好年代
    embedding_vector: Optional[list[float]]  # 向量表示
    last_updated: datetime
```

### SearchResult（搜索结果）

```python
class SearchResult(BaseModel):
    query: str
    total: int
    page: int
    limit: int
    books: list[Book]
```

### RecommendationResult（推荐结果）

```python
class RecommendationResult(BaseModel):
    books: list[Book]
    reasoning: str                      # 推荐理由
    conversation_id: str
    user_preferences_used: list[str]    # 使用的偏好维度
```

## Agent 状态模型（LangGraph State）

```python
class AgentState(TypedDict):
    messages: list[Message]             # 对话历史
    user_query: str                     # 当前用户查询
    intent: str                         # 识别的意图
    search_results: list[Book]          # 搜索结果
    user_preferences: UserPreference    # 用户偏好
    need_more_info: bool                # 是否需要更多信息
    final_recommendations: list[Book]   # 最终推荐
    reasoning: str                      # 推荐推理过程
    next_action: str                    # 下一步动作
```
