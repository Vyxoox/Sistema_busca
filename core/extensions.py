from flask import current_app, has_request_context, request
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


def _xff_confiavel() -> bool:
    if not has_request_context():
        return False
    return bool(current_app.config.get('TRUST_XFF', False))


def ip_origem_requisicao() -> str:
    """IP real do cliente, fonte unica para limiter, bloqueio e auditoria.

    TRUST_XFF=False (padrao; waitress exposto diretamente): usa apenas
    remote_addr, ignorando X-Forwarded-For forjavel pelo cliente.

    TRUST_XFF=True (atras de proxy reverso confiavel, ex.: IIS ARR/nginx):
    usa o ULTIMO hop do X-Forwarded-For — aquele adicionado pelo proxy da
    propria infraestrutura; as entradas anteriores sao controlaveis pelo
    cliente e por isso nao podem ser usadas.
    """
    if not has_request_context():
        return ''
    if _xff_confiavel():
        forwarded = request.headers.get('X-Forwarded-For', '')
        if forwarded:
            return _normalizar_ip(forwarded.split(',')[-1])
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
