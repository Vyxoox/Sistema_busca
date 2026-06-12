import os


def _engine_options(database_uri: str | None) -> dict:
    options = {
        "pool_pre_ping": True,
        "pool_recycle": 1800,
        "connect_args": {
            "timeout": 10
        }
    }

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

    ALERTAS_HABILITADOS = os.getenv("ALERTAS_HABILITADOS", "true").lower() == "true"
    ALERTA_FUSO_HORARIO = os.getenv("ALERTA_FUSO_HORARIO", "America/Sao_Paulo").strip()

    ALERTA_LOGIN_FALHAS_LIMITE = int(os.getenv("ALERTA_LOGIN_FALHAS_LIMITE", "5"))
    ALERTA_LOGIN_FALHAS_JANELA_MIN = int(os.getenv("ALERTA_LOGIN_FALHAS_JANELA_MIN", "5"))
    ALERTA_LOGIN_FALHAS_COOLDOWN_MIN = int(os.getenv("ALERTA_LOGIN_FALHAS_COOLDOWN_MIN", "15"))
    ALERTA_LOGIN_BLOQUEIO_HABILITADO = os.getenv("ALERTA_LOGIN_BLOQUEIO_HABILITADO", "true").lower() == "true"
    ALERTA_LOGIN_BLOQUEAR_LOCALHOST = os.getenv("ALERTA_LOGIN_BLOQUEAR_LOCALHOST", str(IS_PRODUCTION)).lower() == "true"
    ALERTA_LOGIN_BLOQUEIO_MIN = int(os.getenv("ALERTA_LOGIN_BLOQUEIO_MIN", "15"))

    ALERTA_EXPORTACAO_LIMITE = int(os.getenv('ALERTA_EXPORTACAO_LIMITE', '3'))
    ALERTA_EXPORTACAO_JANELA_MIN = int(os.getenv('ALERTA_EXPORTACAO_JANELA_MIN', '10'))
    ALERTA_EXPORTACAO_COOLDOWN_MIN = int(os.getenv('ALERTA_EXPORTACAO_COOLDOWN_MIN', '20'))

    ALERTA_SUPERADMIN_HORA_INICIO = int(os.getenv('ALERTA_SUPERADMIN_HORA_INICIO', '8'))
    ALERTA_SUPERADMIN_HORA_FIM = int(os.getenv('ALERTA_SUPERADMIN_HORA_FIM', '18'))
    ALERTA_SUPERADMIN_COOLDOWN_MIN = int(os.getenv('ALERTA_SUPERADMIN_COOLDOWN_MIN', '30'))

    _acoes_superadmin_padrao = (
        'OUVIDORIA_EXPORTAR_CSV,REINDEXAR_TODOS_SUCESSO,USUARIO_CRIAR_ADMIN_SUCESSO,'
        'FUNCIONARIO_INATIVAR_SUCESSO,FUNCIONARIO_REATIVAR_SUCESSO,FUNCIONARIO_EDITAR_SUCESSO,'
        'FUNCIONARIO_CADASTRAR_SERVIDOR_SUCESSO,FUNCIONARIO_CADASTRAR_TERCEIRIZADO_SUCESSO'
    )
    ALERTA_SUPERADMIN_ACOES = {
        item.strip().upper()
        for item in os.getenv('ALERTA_SUPERADMIN_ACOES', _acoes_superadmin_padrao).split(',')
        if item.strip()
    }

    ALERTA_EMAIL_HABILITADO = os.getenv('ALERTA_EMAIL_HABILITADO', 'false').lower() == 'true'
    ALERTA_EMAIL_SMTP_HOST = os.getenv('ALERTA_EMAIL_SMTP_HOST', '').strip()
    ALERTA_EMAIL_SMTP_PORT = int(os.getenv('ALERTA_EMAIL_SMTP_PORT', '587'))
    ALERTA_EMAIL_SMTP_USUARIO = os.getenv('ALERTA_EMAIL_SMTP_USUARIO', '').strip()
    ALERTA_EMAIL_SMTP_SENHA = os.getenv('ALERTA_EMAIL_SMTP_SENHA', '')
    ALERTA_EMAIL_REMETENTE = os.getenv('ALERTA_EMAIL_REMETENTE', '').strip()
    ALERTA_EMAIL_DESTINATARIOS = [
        item.strip()
        for item in os.getenv('ALERTA_EMAIL_DESTINATARIOS', '').split(',')
        if item.strip()
    ]
    ALERTA_EMAIL_USAR_TLS = os.getenv('ALERTA_EMAIL_USAR_TLS', 'true').lower() == 'true'
    ALERTA_EMAIL_USAR_SSL = os.getenv('ALERTA_EMAIL_USAR_SSL', 'false').lower() == 'true'

    ALERTA_WEBHOOK_HABILITADO = os.getenv('ALERTA_WEBHOOK_HABILITADO', 'false').lower() == 'true'
    ALERTA_WEBHOOK_URL = os.getenv('ALERTA_WEBHOOK_URL', '').strip()
    ALERTA_WEBHOOK_TIMEOUT_SEC = int(os.getenv('ALERTA_WEBHOOK_TIMEOUT_SEC', '5'))

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
