# 书灵 — AI Agent 书籍推荐系统

## 项目简介
基于 AI Agent 的智能书籍推荐平台。用户通过自然语言多轮对话描述阅读需求，AI 调用真实书籍数据库进行多步骤推理，提供个性化、有依据的书籍推荐。

## 方向
方向一：Agentic AI 原生开发

从零构建的 AI Agent 原生应用，采用 SDD（规格驱动开发）方法论，集成 Function Calling、向量记忆、LangGraph 多步推理、多智能体协作等核心技术要素，完成完整工程闭环。

## 技术栈
- AI IDE: VS Code
- LLM: OpenAI 兼容 API（SiliconFlow / DeepSeek / Xiaomi MIMO 等）
- 框架: LangGraph（多步推理状态机）
- 向量库: ChromaDB（嵌入式长期记忆）
- 后端: Python 3.11+ / FastAPI / Uvicorn
- 前端: 原生 HTML/CSS/JS（响应式布局）
- 可观测性: 结构化 JSON 日志 + Tracing ID
- 测试: pytest + pytest-asyncio
- 数据源: Open Library API（免费公开书籍数据）

## 目录结构
```
cs599-project/
├── docs/                            # 项目文档
│   └── CS599_大作业报告.pdf           # 最终提交的报告（PDF）
├── src/                             # 项目源代码
│   ├── spec/                        # SDD 规格文档
│   │   ├── 01-system-overview.md    # 系统概述与核心功能定义
│   │   ├── 02-api-spec.md           # REST API 接口规格（请求/响应/错误码）
│   │   ├── 03-data-models.md        # Pydantic 数据模型定义
│   │   └── 04-agent-behaviors.md    # Agent 行为规格与对话流程
│   ├── backend/
│   │   ├── main.py                  # FastAPI 应用入口，路由注册，SSE 流式
│   │   ├── config.py                # 环境变量配置（API_KEY / 模型 / ChromaDB）
│   │   ├── models/                  # 数据层
│   │   │   ├── schemas.py           # 核心实体：Book, Message, Conversation, UserPreference
│   │   │   └── book.py              # 书籍工具函数：格式化、题材提取
│   │   ├── agents/                  # 多智能体协作层
│   │   │   ├── base_agent.py        # LLM 调用基类（OpenAI 兼容 SDK + Function Calling）
│   │   │   ├── recommend_agent.py   # 推荐 Agent：意图理解、对话管理、结果整合
│   │   │   └── search_agent.py      # 搜索 Agent：调用 Open Library 获取真实书籍
│   │   ├── tools/                   # Function Calling 工具层
│   │   │   ├── book_search.py       # search_books / get_book_detail 工具实现
│   │   │   ├── book_detail.py       # 工具导出
│   │   │   └── preference_analyzer.py # analyze_preferences 偏好分析工具
│   │   ├── memory/                  # 记忆机制
│   │   │   ├── conversation.py      # 短期记忆：会话缓冲区（滑动窗口 + 自动摘要）
│   │   │   └── vector_store.py      # 长期记忆：ChromaDB 向量存储用户偏好
│   │   ├── workflows/               # LangGraph 状态机
│   │   │   └── recommend_graph.py   # 五节点推荐工作流（意图→搜索→分析→推荐/追问）
│   │   └── observability/           # 可观测性
│   │       └── tracer.py            # 请求追踪 + 工具调用计时 + JSON 结构化日志
│   ├── frontend/
│   │   ├── index.html               # 响应式主页面（侧边栏 + 聊天区 + 快捷提示）
│   │   ├── css/style.css            # 响应式样式（Desktop / Tablet / Mobile）
│   │   └── js/
│   │       ├── app.js               # 应用主逻辑：对话列表、侧边栏、模态弹窗
│   │       └── chat.js              # 聊天模块：SSE 流式接收、消息渲染、Markdown
│   ├── tests/
│   │   ├── test_tools.py            # 工具层测试（Open Library 搜索 / 偏好分析）
│   │   ├── test_workflow.py         # LangGraph 工作流测试（意图识别 / 条件路由）
│   │   └── test_api.py              # API 接口测试（健康检查 / 搜索 / 对话 CRUD）
│   ├── data/                        # 运行时数据（ChromaDB 持久化）
│   ├── requirements.txt             # Python 依赖清单
│   └── generate_report.py           # 报告生成脚本
├── .env.example                     # 环境变量模板
├── .gitignore                       # Git 忽略规则
├── LICENSE                          # 开源协议（MIT）
└── README.md
```

## 环境搭建

### 1. 依赖安装
```bash
# Python 3.11+ 推荐
python --version

# 克隆项目
cd BookRecommend

# 安装依赖
pip install -r src/requirements.txt
```

### 2. 环境变量配置
```bash
# 复制模板
cp .env.example .env

# 编辑 .env 文件，填写你的 API 配置（⚠️ 不硬编码 API Key）
# API_KEY=sk-your-key-here          # 你的 API Key
# API_BASE_URL=https://api.xxx.com/v1  # API 地址
# MODEL=your-model-name             # 模型名称

# .env 文件示例：
API_KEY=sk-your-api-key-here
API_BASE_URL=https://api.siliconflow.cn/v1
MODEL=deepseek-ai/DeepSeek-V3
```

### 3. 启动步骤
```bash
# 从项目根目录启动
python -m src.backend.main
```

服务启动后访问：
| 地址 | 说明 |
|------|------|
| http://localhost:8000 | 前端页面 |
| http://localhost:8000/docs | API 文档（Swagger） |
| http://localhost:8000/api/health | 健康检查 |

### 4. 运行测试
```bash
# 运行全部测试
pytest src/tests/ -v

# 分类运行
pytest src/tests/test_tools.py -v      # 工具层
pytest src/tests/test_workflow.py -v   # 工作流
pytest src/tests/test_api.py -v        # API 接口
```

## 项目状态
- [x] Proposal — SDD 规格文档完成
- [x] MVP — 多 Agent 协作 + LangGraph 工作流 + ChromaDB 记忆 + 响应式前端
- [ ] Final — 待持续优化
