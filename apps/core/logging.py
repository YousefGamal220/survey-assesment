from __future__ import annotations

from pythonjsonlogger.json import JsonFormatter

from apps.core.middleware import current_request_id


class JsonRequestFormatter(JsonFormatter):
    """JSON log formatter that injects the current request id when available."""

    def add_fields(self, log_record, record, message_dict) -> None:
        super().add_fields(log_record, record, message_dict)
        rid = current_request_id()
        if rid:
            log_record["request_id"] = rid
        log_record.setdefault("level", record.levelname)
        log_record.setdefault("logger", record.name)
