"""Structured-ish logging: every line carries the request ID (set by middleware in main.py)."""
import logging
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def setup_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s")
    for handler in logging.getLogger().handlers:
        handler.addFilter(RequestIdFilter())
    for noisy in ("httpx", "chromadb", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)  # keep URLs/internal noise out of logs
