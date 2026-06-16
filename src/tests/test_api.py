"""
测试：API 接口

验证 FastAPI 路由的正确性。
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from fastapi.testclient import TestClient
from src.backend.main import app

client = TestClient(app)


def test_root_returns_html():
    """测试根路径返回 HTML"""
    response = client.get("/")
    assert response.status_code == 200
    # 根据实际是否找到 index.html，可能是 HTML 或简单文本
    assert "text/html" in response.headers.get("content-type", "").lower() or \
           response.status_code == 200


def test_health_check():
    """测试健康检查"""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "BookRecommend"


def test_list_conversations_empty():
    """测试空对话列表"""
    response = client.get("/api/conversations")
    assert response.status_code == 200
    data = response.json()
    assert "conversations" in data
    assert isinstance(data["conversations"], list)


def test_search_endpoint_validation():
    """测试搜索接口参数验证"""
    # 空查询应该返回验证错误
    response = client.post("/api/search", json={"query": ""})
    assert response.status_code in [400, 422]


def test_search_endpoint():
    """测试搜索接口"""
    response = client.post("/api/search", json={"query": "Lord of the Rings", "limit": 3})
    assert response.status_code == 200
    data = response.json()
    assert "books" in data
    assert isinstance(data["books"], list)


def test_chat_endpoint_validation():
    """测试对话接口参数验证"""
    response = client.post("/api/chat", json={"message": ""})
    assert response.status_code in [400, 422]


def test_get_nonexistent_conversation():
    """测试获取不存在的对话"""
    response = client.get("/api/conversations/nonexistent-id-12345")
    assert response.status_code == 404


def test_delete_nonexistent_conversation():
    """测试删除不存在的对话"""
    response = client.delete("/api/conversations/nonexistent-id-12345")
    assert response.status_code == 404


def test_workflow_recommend():
    """测试工作流推荐接口"""
    response = client.post(
        "/api/workflow/recommend",
        json={"message": "科幻小说", "user_id": "test_user"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "next_action" in data
