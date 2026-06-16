"""
BookRecommend 配置管理

通过环境变量和 .env 文件加载配置。
支持 OpenAI 兼容 API（如 SiliconFlow、DeepSeek 等）。
"""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv(override=True)


@dataclass
class Config:
    """应用全局配置"""

    # ── LLM API ──
    api_key: str = field(
        default_factory=lambda: os.getenv(
            "API_KEY",
            os.getenv("ANTHROPIC_API_KEY", os.getenv("OPENAI_API_KEY", ""))
        )
    )
    api_base_url: str = field(
        default_factory=lambda: os.getenv(
            "API_BASE_URL",
            os.getenv("OPENAI_BASE_URL", "https://api.siliconflow.cn/v1")
        )
    )
    model: str = field(
        default_factory=lambda: os.getenv(
            "MODEL",
            os.getenv("ANTHROPIC_MODEL", os.getenv("OPENAI_MODEL", "gpt-4o"))
        )
    )

    # ── ChromaDB ──
    chroma_persist_dir: str = field(
        default_factory=lambda: os.getenv("CHROMA_PERSIST_DIR", "./src/data/chroma")
    )

    # ── 服务 ──
    host: str = field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))
    debug: bool = field(default_factory=lambda: os.getenv("DEBUG", "true").lower() == "true")

    # ── 对话 ──
    max_conversation_turns: int = 20
    conversation_summary_threshold: int = 10

    # ── Open Library ──
    open_library_base_url: str = "https://openlibrary.org"
    open_library_covers_url: str = "https://covers.openlibrary.org"

    # ── 默认用户 ──
    default_user_id: str = "user_default"

    def validate(self) -> bool:
        """验证必要配置"""
        if not self.api_key:
            raise ValueError(
                "API_KEY 未设置！请在 .env 文件中配置 API_KEY。\n"
                "例如: API_KEY=sk-..."
            )
        return True


# 全局单例
_config: Config | None = None


def get_config(validate: bool = False) -> Config:
    """获取全局配置单例"""
    global _config
    if _config is None:
        _config = Config()
    if validate:
        _config.validate()
    return _config
