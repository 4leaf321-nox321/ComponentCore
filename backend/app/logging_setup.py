"""로그 — 콘솔과 파일 양쪽에. 콘솔만으로는 창을 닫는 순간 증거가 사라진다."""

from __future__ import annotations

import logging
import sys
from logging.handlers import TimedRotatingFileHandler

from app.config import Settings
from app.shared.request_context import get_request_id

_FORMAT = "%(asctime)s %(levelname)-7s [%(request_id)s] %(name)s: %(message)s"


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


def setup_logging(settings: Settings) -> None:
    settings.log_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG if settings.app_env == "development" else logging.INFO)
    root.handlers.clear()

    formatter = logging.Formatter(_FORMAT)
    id_filter = _RequestIdFilter()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    console.addFilter(id_filter)
    root.addHandler(console)

    file_handler = TimedRotatingFileHandler(
        settings.log_dir / "app.log",
        when="midnight",
        backupCount=settings.log_retention_days,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(id_filter)
    root.addHandler(file_handler)

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True

    # OCP(OpenCascade) 바인딩이 DEBUG 로 많이 말한다 — 우리 로그를 덮지 않게 한다.
    logging.getLogger("OCP").setLevel(logging.WARNING)
    logging.getLogger("build123d").setLevel(logging.INFO)
