import logging
import os
from logging.handlers import TimedRotatingFileHandler
from typing import Optional

_DEFAULT_LOG_DIR = "logs"


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _safe_getenv_int(name: str, default: int) -> int:
    raw = (os.getenv(name, "") or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default

class SafeExtraFormatter(logging.Formatter):

    def format(self, record):

        defaults = {
            "category": "-",
            "request_id": "-",
            "method": "-",
            "path": "-",
            "status_code": "-",
            "duration_ms": "-",
            "user": "-",
            "ip": "-"
        }

        for campo, valor in defaults.items():
            if not hasattr(record, campo):
                setattr(record, campo, valor)

        return super().format(record)

def _build_formatter() -> logging.Formatter:

    fmt = (
        "ts=%(asctime)s "
        "level=%(levelname)s "
        "logger=%(name)s "
        "category=%(category)s "
        "request_id=%(request_id)s "
        "method=%(method)s "
        "path=%(path)s "
        "status_code=%(status_code)s "
        "duration_ms=%(duration_ms)s "
        "user=%(user)s "
        "ip=%(ip)s "
        "message=%(message)s"
    )

    return SafeExtraFormatter(
        fmt=fmt,
        datefmt="%Y-%m-%dT%H:%M:%S"
    )


def _handler_timed_rotating(
    *,
    log_dir: str,
    filename: str,
    when: str = "midnight",
    backup_count: int,
) -> TimedRotatingFileHandler:
    _ensure_dir(log_dir)
    file_path = os.path.join(log_dir, filename)

    # encoding explícito para Windows
    handler = TimedRotatingFileHandler(
        file_path,
        when=when,
        backupCount=backup_count,
        encoding="utf-8",
        utc=True,
    )
    return handler


def setup_logging(app, *, log_dir: Optional[str] = None) -> None:
    """
    Configura logging com rotação e separação por categoria em arquivos:
    - app.log (Aplicação/Observabilidade)
    - security.log (Segurança)
    - audit.log (Auditoria)
    - errors.log (Erros)
    """
    log_dir = log_dir or os.getenv("LOG_DIR", _DEFAULT_LOG_DIR)
    backup_count = _safe_getenv_int("LOG_BACKUP_COUNT", 14)
    level_name = (os.getenv("LOG_LEVEL", "INFO") or "INFO").upper().strip()
    base_level = getattr(logging, level_name, logging.INFO)

    formatter = _build_formatter()

    # Reset handlers do Flask (evita duplicar em reload/dev)
    app.logger.handlers.clear()
    app.logger.propagate = False
    app.logger.setLevel(base_level)

    def _make_logger(logger_name: str) -> logging.Logger:
        logger = logging.getLogger(logger_name)
        logger.setLevel(base_level)
        logger.propagate = False
        logger.handlers.clear()
        return logger

    # Application/Observability
    app_logger = _make_logger("observabilidade")
    app_handler = _handler_timed_rotating(
        log_dir=log_dir,
        filename="app.log",
        backup_count=backup_count,
    )
    app_handler.setLevel(base_level)
    app_handler.setFormatter(formatter)
    app_logger.addHandler(app_handler)

    #Flask-Logger
    app.logger.addHandler(app_handler)
    app.logger.setLevel(base_level)

    # Security (seguranca/alerta/etc.)
    sec_logger = _make_logger("seguranca")
    sec_handler = _handler_timed_rotating(
        log_dir=log_dir,
        filename="security.log",
        backup_count=backup_count,
    )
    sec_handler.setLevel(base_level)
    sec_handler.setFormatter(formatter)
    sec_logger.addHandler(sec_handler)

    # Audit (auditoria / logs_auditoria)
    audit_logger = _make_logger("auditoria")
    audit_handler = _handler_timed_rotating(
        log_dir=log_dir,
        filename="audit.log",
        backup_count=backup_count,
    )
    audit_handler.setLevel(base_level)
    audit_handler.setFormatter(formatter)
    audit_logger.addHandler(audit_handler)

    # Errors
    err_logger = _make_logger("erros")
    err_level = getattr(logging, (os.getenv("ERROR_LOG_LEVEL", "ERROR") or "ERROR").upper(), logging.ERROR)
    err_handler = _handler_timed_rotating(
        log_dir=log_dir,
        filename="errors.log",
        backup_count=backup_count,
    )
    err_handler.setLevel(err_level)
    err_handler.setFormatter(formatter)
    err_logger.addHandler(err_handler)

    # garante que handlers não falhem por campos extras ausentes
    # (usamos LoggerAdapter na prática no código, mas deixamos fallback)
    return
