"""
logger.py
ESG 에이전트 로깅 미들웨어

툴 호출 이벤트(시작/종료/에러)와 전체 요청 시작/종료를 logs/agent.log에 기록.
"""

import logging
import os
import time
from typing import Any, Union
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

LOGS_DIR = "./logs"
LOG_FILE = os.path.join(LOGS_DIR, "agent.log")


def _setup_logger() -> logging.Logger:
    os.makedirs(LOGS_DIR, exist_ok=True)

    logger = logging.getLogger("esg_agent")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        )
        logger.addHandler(handler)

    return logger


logger = _setup_logger()


# 내부 동작 툴 - 로그에서 제외
_INTERNAL_TOOLS = {
    "sql_db_list_tables",
    "sql_db_schema",
    "sql_db_query",
    "sql_db_query_checker",
}


class LoggingCallbackHandler(BaseCallbackHandler):
    """LangChain 콜백 핸들러 - 툴 호출 이벤트 로깅"""

    def __init__(self):
        self._tool_start_times: dict[str, float] = {}
        self.tool_call_count: int = 0

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        tool_name = serialized.get("name", "unknown")
        self._tool_start_times[str(run_id)] = time.time()
        if tool_name in _INTERNAL_TOOLS:
            return
        self.tool_call_count += 1
        logger.info(f"TOOL_START | {tool_name} | input={input_str[:200]}")

    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        elapsed = time.time() - self._tool_start_times.pop(str(run_id), time.time())
        tool_name = kwargs.get("name", "")
        if tool_name in _INTERNAL_TOOLS:
            return
        output_str = str(output)[:200]
        logger.info(f"TOOL_END   | {elapsed:.2f}s | output={output_str}")

    def on_tool_error(
        self,
        error: Union[Exception, KeyboardInterrupt],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        elapsed = time.time() - self._tool_start_times.pop(str(run_id), time.time())
        tool_name = kwargs.get("name", "")
        if tool_name in _INTERNAL_TOOLS:
            return
        logger.error(f"TOOL_ERROR | {elapsed:.2f}s | error={str(error)}")


def log_request(message: str) -> None:
    """요청 시작 로깅"""
    preview = str(message)[:100]
    logger.info(f"REQUEST_START | {preview}")


def log_response(response: str, elapsed: float, tool_call_count: int) -> None:
    """요청 종료 로깅"""
    preview = response[:100] + "..." if len(response) > 100 else response
    logger.info(f"REQUEST_END   | {elapsed:.2f}s | 툴 호출 {tool_call_count}회 | output={preview}")
    logger.info("-" * 80)
