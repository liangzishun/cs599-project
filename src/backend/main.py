"""
BookRecommend - FastAPI 应用入口

AI Agent 书籍推荐系统后端服务。
"""

import json
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from src.backend.config import get_config
from src.backend.models.schemas import (
    ChatRequest,
    SearchRequest,
    ConversationListResponse,
    ConversationDetailResponse,
    ErrorResponse,
)
from src.backend.memory.conversation import get_conversation_memory
from src.backend.agents.recommend_agent import RecommendAgent
from src.backend.tools.book_search import search_books as search_books_tool
from src.backend.workflows.recommend_graph import run_recommend_workflow
from src.backend.observability.tracer import get_tracer, setup_logging

# ──────────────────────────────────────────────
# 应用初始化
# ──────────────────────────────────────────────

# 设置日志
setup_logging()

config = get_config(validate=False)

app = FastAPI(
    title="BookRecommend - AI 书籍推荐系统",
    description="基于 AI Agent 的智能书籍推荐平台",
    version="1.0.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 前端静态文件
frontend_dir = Path(__file__).parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

# Agent 单例
recommend_agent: Optional[RecommendAgent] = None


def get_recommend_agent() -> RecommendAgent:
    """延迟初始化推荐 Agent"""
    global recommend_agent
    if recommend_agent is None:
        recommend_agent = RecommendAgent()
    return recommend_agent


# ──────────────────────────────────────────────
# API 路由
# ──────────────────────────────────────────────

@app.get("/")
async def root():
    """返回前端页面"""
    index_path = frontend_dir / "index.html"
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text(encoding="utf-8"))
    return HTMLResponse(
        content="<h1>BookRecommend</h1><p>前端页面尚未构建。请访问 <a href='/docs'>/docs</a> 查看 API 文档。</p>"
    )


@app.post("/api/chat")
async def api_chat(request: ChatRequest):
    """
    对话接口 —— SSE 流式响应

    用户发送消息，AI Agent 回复推荐结果。
    支持多轮对话（通过 conversation_id 关联）。
    """
    tracer = get_tracer()
    t_start = time.time()

    memory = get_conversation_memory()
    agent = get_recommend_agent()

    # 获取或创建对话
    conv = memory.get_or_create_conversation(
        request.conversation_id, request.user_id
    )

    async def event_stream():
        try:
            async for event in agent.chat_stream(
                user_message=request.message,
                conversation_id=conv.id,
                user_id=request.user_id,
            ):
                # 在 SSE data 中包含 conversation_id
                event["conversation_id"] = conv.id
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

            duration_ms = (time.time() - t_start) * 1000
            tracer.request_end("/api/chat", 200, duration_ms)

        except Exception as e:
            error_event = {
                "type": "error",
                "content": f"服务器错误: {str(e)}",
                "conversation_id": conv.id,
            }
            yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 nginx 缓冲
        },
    )


@app.post("/api/search")
async def api_search(request: SearchRequest):
    """
    直接搜索书籍 —— 不走 AI Agent

    快速获取 Open Library 的书籍搜索结果。
    """
    tracer = get_tracer()
    t_start = time.time()

    result = await search_books_tool(
        query=request.query,
        limit=request.limit,
        page=request.page,
    )

    duration_ms = (time.time() - t_start) * 1000
    tracer.request_end("/api/search", 200, duration_ms)

    return {
        "total": result.total,
        "page": result.page,
        "limit": result.limit,
        "books": [
            {
                "title": b.title,
                "author": b.author,
                "cover_url": b.cover_url,
                "publish_year": b.publish_year,
                "publisher": b.publisher,
                "isbn": b.isbn,
                "subjects": b.subjects,
                "description": b.description,
                "language": b.language,
                "open_library_key": b.open_library_key,
                "ratings_average": b.ratings_average,
                "ratings_count": b.ratings_count,
            }
            for b in result.books
        ],
    }


@app.get("/api/conversations")
async def api_list_conversations():
    """获取所有对话列表"""
    memory = get_conversation_memory()
    conversations = memory.list_conversations()
    return {"conversations": [c.model_dump() for c in conversations]}


@app.get("/api/conversations/{conversation_id}")
async def api_get_conversation(conversation_id: str):
    """获取特定对话的完整历史"""
    memory = get_conversation_memory()
    conv = memory.get_conversation(conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="对话不存在")
    return {
        "id": conv.id,
        "title": conv.title,
        "messages": [m.model_dump(mode="json") for m in conv.messages],
        "created_at": conv.created_at.isoformat(),
        "updated_at": conv.updated_at.isoformat(),
    }


@app.delete("/api/conversations/{conversation_id}")
async def api_delete_conversation(conversation_id: str):
    """删除指定对话"""
    memory = get_conversation_memory()
    success = memory.delete_conversation(conversation_id)
    if not success:
        raise HTTPException(status_code=404, detail="对话不存在")
    return {"status": "deleted", "conversation_id": conversation_id}


@app.post("/api/workflow/recommend")
async def api_workflow_recommend(request: ChatRequest):
    """
    LangGraph 工作流推荐 —— 非 LLM 的规则化推荐

    使用 LangGraph 状态机进行多步骤推理推荐。
    这是 Agent 推荐的补充方案，更快速且不需要 LLM 调用。
    """
    result = await run_recommend_workflow(
        user_query=request.message,
        conversation_id=request.conversation_id or "temp",
        user_id=request.user_id,
    )
    return result


# ──────────────────────────────────────────────
# 健康检查
# ──────────────────────────────────────────────

@app.get("/api/health")
async def health_check():
    """健康检查接口"""
    return {
        "status": "ok",
        "service": "BookRecommend",
        "version": "1.0.0",
        "model": config.model,
    }


# ──────────────────────────────────────────────
# 异常处理
# ──────────────────────────────────────────────

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "HTTP_ERROR", "message": exc.detail}},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "服务器内部错误",
                "detail": str(exc),
            }
        },
    )


# ──────────────────────────────────────────────
# 启动
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    config = get_config(validate=True)
    uvicorn.run(
        "src.backend.main:app",
        host=config.host,
        port=config.port,
        reload=config.debug,
        log_level="info",
    )
