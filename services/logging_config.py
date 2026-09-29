import json
import logging
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    EXTRA_FIELDS = (
        "duration_ms",
        "error_type",
        "event",
        "method",
        "path",
        "provider",
        "status",
    )

    def format(self, record):
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "service": "marketv",
            "message": record.getMessage(),
        }

        for field in self.EXTRA_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value

        return json.dumps(payload, separators=(",", ":"))


def configure_logging(app, level_name="INFO"):
    level = getattr(logging, str(level_name).upper(), logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    app.logger.handlers.clear()
    app.logger.addHandler(handler)
    app.logger.setLevel(level)
    app.logger.propagate = False
