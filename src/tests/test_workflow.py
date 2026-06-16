"""
测试：LangGraph 工作流

验证多步骤推理逻辑。
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.backend.workflows.recommend_graph import (
    understand_intent,
    search_books_node,
    analyze_preferences_node,
    generate_recommendation_node,
    route_after_analyze,
    RecommendState,
)


@pytest.mark.asyncio
async def test_understand_intent_search():
    """测试意图识别 - 搜索"""
    state: RecommendState = {
        "user_query": "搜索科幻小说",
        "user_id": "test_user",
        "conversation_id": "test_conv",
        "intent": "",
        "extracted_keywords": [],
        "extracted_subject": None,
        "search_query": "",
        "search_results": [],
        "search_total": 0,
        "user_preferences": None,
        "need_more_info": False,
        "final_recommendations": [],
        "reasoning": "",
        "assistant_message": "",
        "next_action": "",
        "iteration_count": 0,
    }
    result = await understand_intent(state)
    assert result["intent"] == "search"
    assert "extracted_keywords" in result


@pytest.mark.asyncio
async def test_understand_intent_recommend():
    """测试意图识别 - 推荐"""
    state = _make_state("推荐一些好看的悬疑小说")
    result = await understand_intent(state)
    assert result["intent"] == "recommend"
    assert result["extracted_subject"] == "thriller"


@pytest.mark.asyncio
async def test_understand_intent_chat():
    """测试意图识别 - 闲聊"""
    state = _make_state("你好啊")
    result = await understand_intent(state)
    assert result["intent"] == "chat"


@pytest.mark.asyncio
async def test_search_books_node():
    """测试搜索节点"""
    state = _make_state("The Hobbit")
    state["intent"] = "recommend"
    state["search_query"] = "The Hobbit"
    state["extracted_subject"] = "fantasy"

    result = await search_books_node(state)
    assert "search_results" in result
    assert "search_total" in result


@pytest.mark.asyncio
async def test_analyze_preferences_node_recommend():
    """测试偏好分析 - 推荐场景"""
    state = _make_state("科幻小说推荐")
    state["intent"] = "recommend"
    state["extracted_subject"] = "science_fiction"
    state["extracted_keywords"] = ["科幻", "小说", "推荐"]
    state["search_results"] = [{"title": "Test Book"}]

    result = await analyze_preferences_node(state)
    assert "need_more_info" in result
    assert "next_action" in result


@pytest.mark.asyncio
async def test_generate_recommendation_empty():
    """测试推荐生成 - 无结果"""
    state = _make_state("xyzabc123456")
    state["intent"] = "recommend"
    state["search_results"] = []

    result = await generate_recommendation_node(state)
    assert "assistant_message" in result
    assert len(result.get("final_recommendations", [])) == 0


def test_route_after_analyze_need_info():
    """测试路由 - 信息不足"""
    state = _make_state("test")
    state["need_more_info"] = True
    assert route_after_analyze(state) == "ask"


def test_route_after_analyze_recommend():
    """测试路由 - 可以推荐"""
    state = _make_state("test")
    state["need_more_info"] = False
    state["intent"] = "recommend"
    assert route_after_analyze(state) == "recommend"


def test_route_after_analyze_chat():
    """测试路由 - 闲聊"""
    state = _make_state("hello")
    state["need_more_info"] = False
    state["intent"] = "chat"
    assert route_after_analyze(state) == "respond"


# ── 辅助函数 ──

def _make_state(query: str) -> RecommendState:
    return {
        "user_query": query,
        "user_id": "test_user",
        "conversation_id": "test_conv",
        "intent": "",
        "extracted_keywords": [],
        "extracted_subject": None,
        "search_query": query,
        "search_results": [],
        "search_total": 0,
        "user_preferences": None,
        "need_more_info": False,
        "final_recommendations": [],
        "reasoning": "",
        "assistant_message": "",
        "next_action": "",
        "iteration_count": 0,
    }
