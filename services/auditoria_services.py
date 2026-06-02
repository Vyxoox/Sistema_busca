import json
import re
from typing import Any

from flask import current_app, has_app_context, has_request_context, request, g, session
from flask_login import current_user
from datetime import UTC, datetime
from uuid import uuid4

from core.extensions import db
from models import LogAuditoria

MAX_DETALHES = 8000

CHAVES_SENSIVEIS_CONTEM = (
    'senha', 'password', 'token', 'secret', 'authorization', 'cookie', 'chave'
)

CHAVES_SENSIVEIS_EXATAS = {
    'cpf', 'cpf_informado', 'pis_pasep',
    'telefone', 'telefone_pessoal',
    'email_pessoal', 'email_institucional',
}

CHAVES_CONTEXTO_AUDITORIA = {
    'request_id',
    'correlation_id',
    'session_id',
    'timestamp_utc',
}

RE_CPF = re.compile(r'\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b')
RE_EMAIL = re.compile(r'(?i)\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b')
RE_TELEFONE = re.compile(r'(?<!\d)(?:\+?55[\s-]?)?(?:\(?\d{2}\)?[\s-]?)?(?:9\d{4}|\d{4})[-\s]\d{4}(?!\d)')
RE_CORRELATION_ID = re.compile(r'\b[a-f0-9]{32}\b')

def _texto_seguro(valor: Any, limite: int) -> str | None:
    if valor is None:
        return None
    texto = str(valor).strip()
    if not texto:
        return None
    return texto[:limite]


def _ip_origem() -> str | None:
    forwarded = request.headers.get('X-Forwarded-For', '')
    if forwarded:
        return _texto_seguro(forwarded.split(',')[0], 45)
    return _texto_seguro(request.remote_addr, 45)


def _serializar_detalhes(detalhes: dict[str, Any] | None) -> str | None:
    if not detalhes:
        return None
    limpos = _mascarar_sensiveis(detalhes)
    bruto = json.dumps(limpos, ensure_ascii=False, default=str)
    return bruto[:MAX_DETALHES]


def _chave_sensivel(chave: Any) -> bool:
    if chave is None:
        return False
    chave_lower = str(chave).strip().lower()
    if chave_lower in CHAVES_SENSIVEIS_EXATAS:
        return True
    return any(palavra in chave_lower for palavra in CHAVES_SENSIVEIS_CONTEM)

def _mascarar_texto_sensiveis(texto: str) -> str:
    # Se o texto for um correlation_id/request_id (32 hex), não aplicar mascaramento de telefone nele.
    if RE_CORRELATION_ID.fullmatch(texto):
        return texto

    mascarado = RE_CPF.sub('[cpf_mascarado]', texto)
    mascarado = RE_EMAIL.sub('[email_mascarado]', mascarado)
    mascarado = RE_TELEFONE.sub('[telefone_mascarado]', mascarado)
    return mascarado

def _mascarar_sensiveis(valor: Any, chave: Any | None = None) -> Any:
    chave_norm = str(chave).strip().lower() if chave is not None else ''

    if chave_norm in CHAVES_CONTEXTO_AUDITORIA:
        return valor
    if _chave_sensivel(chave):
        return '****'

    if isinstance(valor, dict):
        return {str(k): _mascarar_sensiveis(v, k) for k, v in valor.items()}

    if isinstance(valor, list):
        return [_mascarar_sensiveis(item, chave) for item in valor]

    if isinstance(valor, tuple):
        return [_mascarar_sensiveis(item, chave) for item in valor]

    if isinstance(valor, str):
        return _mascarar_texto_sensiveis(valor)

    return valor

def _agora_utc_iso() ->str:
    return datetime.now(UTC).isoformat()

def _obter_request_id() -> str | None:
    if not has_request_context():
        return None

    request_id = getattr(g, 'audit_request_id', None)
    if request_id:
        return _texto_seguro(request_id, 80)

    header_id=(
        request.headers.get('X-Request-ID') or
        request.headers.get('X-Correlation-ID') or
        ''
    ).strip()

    request_id = _texto_seguro(header_id, 80) or uuid4().hex
    g.audit_request_id = request_id
    return request_id

def _obter_session_id() -> str | None:
    if not has_request_context():
        return None

    session_id = getattr(g, 'audit_session_id', None)
    if not session_id:
        session_id = session.get('audit_session_id')

    if not session_id:
        session_id = uuid4().hex
        session['audit_session_id'] = session_id

    g.audit_session_id = session_id
    return _texto_seguro(session_id, 80)

def _mesclar_detalhes_com_contexto(detalhes: dict[str, Any] | None) -> dict[str, Any] | None:
    base = dict(detalhes or {})
    request_id = _obter_request_id()
    session_id = _obter_session_id()

    contexto = {
        'request_id': request_id,
        'correlation_id': request_id,
        'session_id': session_id,
        'timestamp_utc': _agora_utc_iso(),
    }

    for chave, valor in contexto.items():
        if valor is not None and chave not in base:
            base[chave] = valor

    return base or None

def _normalizar_valor_diff(valor: Any) -> Any:
    if valor is None:
        return None
    if hasattr(valor, 'isoformat'):
        return valor.isoformat()
    if isinstance(valor, dict):
        return {str(k): _normalizar_valor_diff(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_normalizar_valor_diff(item) for item in valor]

    texto = str(valor).strip()
    return  texto if texto else None

def gerar_diff_antes_depois(
    antes: dict[str, Any],
    depois: dict[str, Any],
    campos: list[str] | tuple[str,...] | None = None,
) ->list[dict[str, Any]]:
    chaves = list(campos) if campos is not None else sorted(set(antes.keys()) | set(depois.keys()))
    alteracoes : list[dict[str, Any]] = []

    for campo in chaves:
        valor_antes = _normalizar_valor_diff(antes.get(campo))
        valor_depois = _normalizar_valor_diff(depois.get(campo))
        if valor_antes != valor_depois:
            alteracoes.append({
                'campo': str(campo),
                'antes': valor_antes,
                'depois': valor_depois,
            })

    return alteracoes

def registrar_evento(
    acao: str,
    *,
    categoria: str = 'seguranca',
    status: str = 'sucesso',
    recurso: str | None = None,
    recurso_id: str | None = None,
    detalhes: dict[str, Any] | None = None,
    processar_alertas: bool = True,
) -> LogAuditoria:
    usuario_id = None
    usuario_login = None

    if getattr(current_user, 'is_authenticated', False):
        usuario_id = getattr(current_user, 'id', None)
        usuario_login = _texto_seguro(getattr(current_user, 'login', None), 80)

    detalhes_com_contexto = _mesclar_detalhes_com_contexto(detalhes)
    evento = LogAuditoria(
        usuario_id=usuario_id,
        usuario_login=usuario_login,
        acao=_texto_seguro(acao, 120) or 'ACAO_NAO_INFORMADA',
        categoria=_texto_seguro(categoria, 50) or 'seguranca',
        status=_texto_seguro(status, 20) or 'sucesso',
        recurso=_texto_seguro(recurso, 80),
        recurso_id=_texto_seguro(recurso_id, 80),
        metodo_http=(request.method if has_request_context() else None),
        rota=(request.path if has_request_context() else None),
        ip_origem=(_ip_origem() if has_request_context() else None),
        user_agent=(_texto_seguro(request.user_agent.string, 255) if has_request_context() else None),
        detalhes=_serializar_detalhes(detalhes_com_contexto),
    )

    db.session.add(evento)
    db.session.commit()

    if processar_alertas and has_app_context():
        try:
            from services.alertas_seguranca import avaliar_alertas_evento
            avaliar_alertas_evento(evento, detalhes_com_contexto or {})
        except Exception:
            current_app.logger.exception('Falha ao processar alertas de seguranca para o evento: %s', acao)

    return evento


def registrar_evento_seguro(acao: str, **kwargs: Any) -> None:
    try:
        registrar_evento(acao, **kwargs)
    except Exception:
        db.session.rollback()
        if has_app_context():
            current_app.logger.exception('Falha ao registrar evento de auditoria: %s', acao)
            current_app.logger.critical("FALHA CRÍTICA NA AUDITORIA")
