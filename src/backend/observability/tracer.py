"""
可观测性追踪器

提供结构化日志、请求追踪、性能计时功能。
"""

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4


# ──────────────────────────────────────────────
# 结构化日志
# ──────────────────────────────────────────────

class JsonFormatter(logging.Formatter):
    """JSON 格式日志输出"""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "trace_id"):
            log_entry["trace_id"] = record.trace_id
        if hasattr(record, "extra_data"):
            log_entry["extra"] = record.extra_data
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False)


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """配置应用日志"""
    logger = logging.getLogger("bookrecommend")
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)

    return logger


# ──────────────────────────────────────────────
# 追踪器
# ──────────────────────────────────────────────

class Tracer:
    """请求和工具调用追踪器"""

    def __init__(self, trace_id: Optional[str] = None):
        self.trace_id = trace_id or str(uuid4())[:8]
        self.logger = logging.getLogger("bookrecommend.tracer")
        self._timers: dict[str, float] = {}

    def request_start(self, endpoint: str, params: dict[str, Any]) -> None:
        """记录请求开始"""
        self.logger.info(
            f"[{self.trace_id}] REQUEST START: {endpoint}",
            extra={"trace_id": self.trace_id, "endpoint": endpoint, "params": params},
        )

    def request_end(self, endpoint: str, status: int, duration_ms: float) -> None:
        """记录请求结束"""
        self.logger.info(
            f"[{self.trace_id}] REQUEST END: {endpoint} status={status} duration={duration_ms:.1f}ms",
            extra={"trace_id": self.trace_id, "endpoint": endpoint, "status": status, "duration_ms": duration_ms},
        )

    def tool_start(self, tool_name: str, args: dict[str, Any]) -> None:
        """记录工具调用开始"""
        self._timers[tool_name] = time.time()
        self.logger.debug(
            f"[{self.trace_id}] TOOL START: {tool_name} args={args}",
            extra={"trace_id": self.trace_id, "tool": tool_name, "args": args},
        )

    def tool_end(self, tool_name: str, result_summary: str) -> None:
        """记录工具调用结束"""
        elapsed = time.time() - self._timers.pop(tool_name, time.time())
        self.logger.info(
            f"[{self.trace_id}] TOOL END: {tool_name} duration={elapsed*1000:.1f}ms result={result_summary}",
            extra={"trace_id": self.trace_id, "tool": tool_name, "duration_ms": elapsed * 1000, "result": result_summary},
        )

    def tool_error(self, tool_name: str, error: str) -> None:
        """记录工具调用错误"""
        self.logger.error(
            f"[{self.trace_id}] TOOL ERROR: {tool_name} error={error}",
            extra={"trace_id": self.trace_id, "tool": tool_name, "error": error},
        )

    def llm_call_start(self, model: str, message_count: int) -> None:
        """记录 LLM 调用开始"""
        self._timers["llm"] = time.time()
        self.logger.info(
            f"[{self.trace_id}] LLM START: model={model} messages={message_count}",
            extra={"trace_id": self.trace_id, "model": model, "messages": message_count},
        )

    def llm_call_end(self, model: str, tokens_used: int) -> None:
        """记录 LLM 调用结束"""
        elapsed = time.time() - self._timers.pop("llm", time.time())
        self.logger.info(
            f"[{self.trace_id}] LLM END: model={model} tokens={tokens_used} duration={elapsed*1000:.1f}ms",
            extra={"trace_id": self.trace_id, "model": model, "tokens": tokens_used, "duration_ms": elapsed * 1000},
        )


# 全局 tracer 工厂
_tracer: Optional[Tracer] = None


def get_tracer(trace_id: Optional[str] = None) -> Tracer:
    """获取或创建 tracer 实例"""
    global _tracer
    if trace_id:
        _tracer = Tracer(trace_id)
    if _tracer is None:
        _tracer = Tracer()
    return _tracer
