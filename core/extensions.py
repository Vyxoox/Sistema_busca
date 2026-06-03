from flask import has_request_context, request
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf import CSRFProtect
from flask_migrate import Migrate
from flask_limiter import Limiter


def _normalizar_ip(valor: str | None) -> str:
    texto = str(valor or '').strip()
    if not texto:
        return ''
    if ',' in texto:
        texto = texto.split(',')[0].strip()
    return texto[:45]


def ip_origem_requisicao() -> str:
    if not has_request_context():
        return ''
    forwarded = request.headers.get('X-Forwarded-For', '')
    if forwarded:
        return _normalizar_ip(forwarded)
    return _normalizar_ip(request.remote_addr)


db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
migrate = Migrate()

limiter = Limiter(
    key_func=ip_origem_requisicao,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)
