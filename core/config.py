import os


def _engine_options(database_uri: str | None) -> dict:
    options = {
        "pool_pre_ping": True,
        "pool_recycle": 1800,
        "connect_args": {
            "timeout": 10
        }
    }

    if database_uri and not database_uri.lower().startswith("sqlite"):
        options.update({
            "pool_size": 10,
            "max_overflow": 20,
        })

    return options


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY")

    if not SECRET_KEY:
        raise RuntimeError(
            "SECRET_KEY não definida. Configure no ambiente."
        )

    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")

    SQLALCHEMY_ENGINE_OPTIONS = _engine_options(SQLALCHEMY_DATABASE_URI)

    if not SQLALCHEMY_DATABASE_URI:
        raise RuntimeError(
            "DATABASE_URL não configurada."
        )

    APP_ENV = os.getenv(
        "APP_ENV",
        "development"
    )
    DEBUG = APP_ENV == "development"
    IS_PRODUCTION = APP_ENV == "production"

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = IS_PRODUCTION

    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = IS_PRODUCTION

    PREFERRED_URL_SCHEME = "https"

    MAX_CONTENT_LENGTH = 5 * 1024 * 1024


    SMTP_HOST = os.getenv("SMTP_HOST")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))

    SMTP_USER = os.getenv("SMTP_USER")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

    SMTP_USE_TLS = os.getenv(
        "SMTP_USE_TLS",
        "true"
    ).lower() == "true"

    SMTP_USE_SSL = os.getenv(
        "SMTP_USE_SSL",
        "false"
    ).lower() == "true"

    SMTP_TIMEOUT = int(os.getenv("SMTP_TIMEOUT", "10"))
