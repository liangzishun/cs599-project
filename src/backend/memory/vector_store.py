"""
ChromaDB 向量存储 —— 长期记忆

存储用户阅读偏好的向量表示，支持语义检索。
"""

import json
import os
from datetime import datetime
from typing import Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

from src.backend.config import get_config
from src.backend.models.schemas import UserPreference
from src.backend.observability.tracer import get_tracer


class VectorStore:
    """
    ChromaDB 向量存储封装

    Collection 设计：
    - user_preferences: 用户阅读偏好（向量+元数据）
    - conversation_summaries: 对话摘要（可选，未来扩展）
    """

    def __init__(self, persist_dir: str):
        self._persist_dir = persist_dir
        os.makedirs(persist_dir, exist_ok=True)

        self._client = chromadb.PersistentClient(
            path=persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._preferences_collection = self._client.get_or_create_collection(
            name="user_preferences",
            metadata={"description": "用户阅读偏好向量存储"},
        )

    # ──────────────────────────────────────────────
    # 偏好存储
    # ──────────────────────────────────────────────

    def store_preference(self, preference: UserPreference) -> str:
        """存储用户偏好到向量数据库"""
        tracer = get_tracer()

        # 构建用于 embedding 的文本
        embedding_text = _build_preference_text(preference)
        if not embedding_text.strip():
            return ""

        # 生成唯一 ID
        pref_id = f"pref_{preference.user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"

        # 构建元数据
        metadata = {
            "user_id": preference.user_id,
            "genres": json.dumps(preference.preferred_genres),
            "authors": json.dumps(preference.preferred_authors),
            "languages": json.dumps(preference.preferred_languages),
            "summary": preference.free_text_summary,
            "timestamp": preference.last_updated.isoformat(),
        }

        try:
            self._preferences_collection.add(
                ids=[pref_id],
                documents=[embedding_text],
                metadatas=[metadata],
            )
            tracer.tool_end("store_preference", f"stored {pref_id}")
            return pref_id
        except Exception as e:
            tracer.tool_error("store_preference", str(e))
            raise

    def get_preferences(self, user_id: str, top_k: int = 3) -> Optional[UserPreference]:
        """检索用户最新的偏好"""
        tracer = get_tracer()

        try:
            results = self._preferences_collection.get(
                where={"user_id": user_id},
                include=["documents", "metadatas"],
            )

            if not results or not results["ids"]:
                return None

            # 使用最新的偏好记录
            latest_idx = 0
            latest_ts = ""
            for i, meta in enumerate(results["metadatas"]):
                ts = meta.get("timestamp", "")
                if ts > latest_ts:
                    latest_ts = ts
                    latest_idx = i

            meta = results["metadatas"][latest_idx]

            return UserPreference(
                user_id=user_id,
                preferred_genres=json.loads(meta.get("genres", "[]")),
                preferred_authors=json.loads(meta.get("authors", "[]")),
                preferred_languages=json.loads(meta.get("languages", "[]")),
                free_text_summary=meta.get("summary", ""),
            )

        except Exception as e:
            tracer.tool_error("get_preferences", str(e))
            return None

    def search_similar_preferences(
        self, query_text: str, user_id: Optional[str] = None, top_k: int = 3
    ) -> list[dict]:
        """搜索与查询语义相似的偏好记录"""
        where_filter = {"user_id": user_id} if user_id else None

        try:
            results = self._preferences_collection.query(
                query_texts=[query_text],
                n_results=top_k,
                where=where_filter,
                include=["documents", "metadatas", "distances"],
            )

            items = []
            if results and results["ids"] and results["ids"][0]:
                for i, pref_id in enumerate(results["ids"][0]):
                    items.append({
                        "id": pref_id,
                        "document": results["documents"][0][i] if results["documents"] else "",
                        "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                        "distance": results["distances"][0][i] if results["distances"] else 0,
                    })

            return items

        except Exception as e:
            get_tracer().tool_error("search_preferences", str(e))
            return []

    def get_preference_history(self, user_id: str, limit: int = 10) -> list[dict]:
        """获取用户偏好历史"""
        try:
            results = self._preferences_collection.get(
                where={"user_id": user_id},
                include=["documents", "metadatas"],
            )

            if not results or not results["ids"]:
                return []

            items = []
            for i, pref_id in enumerate(results["ids"]):
                items.append({
                    "id": pref_id,
                    "document": results["documents"][i] if results["documents"] else "",
                    "metadata": results["metadatas"][i] if results["metadatas"] else {},
                })

            # 按时间戳降序
            items.sort(key=lambda x: x["metadata"].get("timestamp", ""), reverse=True)
            return items[:limit]

        except Exception:
            return []


# ──────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────

def _build_preference_text(preference: UserPreference) -> str:
    """构建用于向量化的偏好文本"""
    parts = []

    if preference.preferred_genres:
        parts.append(f"偏好题材: {', '.join(preference.preferred_genres)}")

    if preference.preferred_authors:
        parts.append(f"偏好作者: {', '.join(preference.preferred_authors)}")

    if preference.preferred_languages:
        parts.append(f"偏好语言: {', '.join(preference.preferred_languages)}")

    if preference.reading_level:
        parts.append(f"阅读水平: {preference.reading_level}")

    if preference.preferred_era:
        parts.append(f"偏好年代: {preference.preferred_era}")

    if preference.free_text_summary:
        parts.append(f"综合描述: {preference.free_text_summary}")

    return "。".join(parts)


# 全局单例
_store: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    """获取全局向量存储单例"""
    global _store
    if _store is None:
        config = get_config()
        _store = VectorStore(persist_dir=config.chroma_persist_dir)
    return _store
