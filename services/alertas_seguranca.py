import json
import os
import smtplib
import logging
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from flask import current_app, has_request_context, request
from sqlalchemy import true

from core.extensions import db
from models import LogAuditoria, Usuario
from services.auditoria_services import registrar_evento_seguro


def _env_bool(nome: str, padrao: bool) -> bool:
    bruto = os.getenv(nome, str(padrao))
    return str(bruto).strip().lower() in {'1', 'true', 'yes', 'sim', 'on'}


def _env_int(nome: str, padrao: int, minimo: int, maximo: int) -> int:
    bruto = os.getenv(nome, str(padrao)).strip()
    try:
        valor = int(bruto)
    except (TypeError, ValueError):
        return padrao
    return max(minimo, min(maximo, valor))

def _env_bool_opcional(nome: str) -> bool |None:
    bruto = os.getenv(nome)
    if bruto is None:
        return None
    return str(bruto).strip().lower() in {'1', 'true', 'yes', 'sim', 'on'}

def _ambiente_producao() -> bool:
    env = (os.getenv('APP_ENV') or  os.getenv('FLASK_ENV') or 'dev').strip().lower()
    return env in {'prod', 'production', 'producao'}

def _agora_utc_sem_tz() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _carregar_config() -> dict[str, Any]:
    acoes_superadmin_padrao = (
        'OUVIDORIA_EXPORTAR_CSV,REINDEXAR_TODOS_SUCESSO,USUARIO_CRIAR_ADMIN_SUCESSO,'
        'FUNCIONARIO_INATIVAR_SUCESSO,FUNCIONARIO_REATIVAR_SUCESSO,FUNCIONARIO_EDITAR_SUCESSO,'
        'FUNCIONARIO_CADASTRAR_SERVIDOR_SUCESSO,FUNCIONARIO_CADASTRAR_TERCEIRIZADO_SUCESSO'
    )
    acoes_superadmin_raw = os.getenv('ALERTA_SUPERADMIN_ACOES', acoes_superadmin_padrao)
    acoes_superadmin = {
        item.strip().upper()
        for item in acoes_superadmin_raw.split(',')
        if item.strip()
    }

    producao = _ambiente_producao()

    login_bloqueio_habilitado = _env_bool_opcional('ALERTA_LOGIN_BLOQUEIO_HABILITADO')
    if login_bloqueio_habilitado is None:
        login_bloqueio_habilitado = True

    login_bloquear_localhost = _env_bool_opcional('ALERTA_LOGIN_BLOQUEAR_LOCALHOST')
    if login_bloquear_localhost is None:
        login_bloquear_localhost = producao

    return {
        'habilitado': _env_bool('ALERTAS_HABILITADOS', True),
        'fuso': os.getenv('ALERTA_FUSO_HORARIO', 'America/Sao_Paulo').strip() or 'America/Sao_Paulo',
        'login_limite': _env_int('ALERTA_LOGIN_FALHAS_LIMITE', 5, 1, 1000),
        'login_janela_min': _env_int('ALERTA_LOGIN_FALHAS_JANELA_MIN', 5, 1, 1440),
        'login_cooldown_min': _env_int('ALERTA_LOGIN_FALHAS_COOLDOWN_MIN', 15, 1, 1440),
        'login_bloqueio_habilitado': login_bloqueio_habilitado,
        'login_bloquear_localhost': login_bloquear_localhost,
        'login_bloqueio_min': _env_int('ALERTA_LOGIN_BLOQUEIO_MIN', 15, 1, 1440),
        'export_limite': _env_int('ALERTA_EXPORTACAO_LIMITE', 3, 1, 1000),
        'export_janela_min': _env_int('ALERTA_EXPORTACAO_JANELA_MIN', 10, 1, 1440),
        'export_cooldown_min': _env_int('ALERTA_EXPORTACAO_COOLDOWN_MIN', 20, 1, 1440),
        'superadmin_hora_inicio': _env_int('ALERTA_SUPERADMIN_HORA_INICIO', 8, 0, 23),
        'superadmin_hora_fim': _env_int('ALERTA_SUPERADMIN_HORA_FIM', 18, 0, 23),
        'superadmin_cooldown_min': _env_int('ALERTA_SUPERADMIN_COOLDOWN_MIN', 30, 1, 1440),
        'superadmin_acoes': acoes_superadmin,
        'email_habilitado': _env_bool('ALERTA_EMAIL_HABILITADO', False),
        'email_smtp_host': os.getenv('ALERTA_EMAIL_SMTP_HOST', '').strip(),
        'email_smtp_port': _env_int('ALERTA_EMAIL_SMTP_PORT', 587, 1, 65535),
        'email_smtp_usuario': os.getenv('ALERTA_EMAIL_SMTP_USUARIO', '').strip(),
        'email_smtp_senha': os.getenv('ALERTA_EMAIL_SMTP_SENHA', ''),
        'email_remetente': os.getenv('ALERTA_EMAIL_REMETENTE', '').strip(),
        'email_destinatarios': [
            item.strip()
            for item in os.getenv('ALERTA_EMAIL_DESTINATARIOS', '').split(',')
            if item.strip()
        ],
        'email_usar_tls': _env_bool('ALERTA_EMAIL_USAR_TLS', True),
        'email_usar_ssl': _env_bool('ALERTA_EMAIL_USAR_SSL', False),
        'webhook_habilitado': _env_bool('ALERTA_WEBHOOK_HABILITADO', False),
        'webhook_url': os.getenv('ALERTA_WEBHOOK_URL', '').strip(),
        'webhook_timeout_sec': _env_int('ALERTA_WEBHOOK_TIMEOUT_SEC', 5, 1, 120),
    }


def _fuso_horario(nome_fuso: str) -> ZoneInfo:
    try:
        return ZoneInfo(nome_fuso)
    except Exception:
        return ZoneInfo('America/Sao_Paulo')


def _timestamp_local_iso(valor_utc: datetime | None, nome_fuso: str) -> str:
    if not valor_utc:
        return ''
    fuso = _fuso_horario(nome_fuso)
    dt = valor_utc.replace(tzinfo=UTC).astimezone(fuso)
    return dt.isoformat()


def _normalizar_ip(valor: str | None) -> str:
    texto = str(valor or '').strip()
    if not texto:
        return ''
    if ',' in texto:
        texto = texto.split(',')[0].strip()
    return texto[:45]


def _ip_localhost(ip: str) -> bool:
    return ip in {'127.0.0.1', '::1'}


def ip_origem_requisicao() -> str:
    if not has_request_context():
        return ''
    forwarded = request.headers.get('X-Forwarded-For', '')
    if forwarded:
        return _normalizar_ip(forwarded)
    return _normalizar_ip(request.remote_addr)


def _extrair_bloqueio_ate_utc(detalhes: str | None) -> datetime | None:
    if not detalhes:
        return None
    try:
        dados = json.loads(detalhes)
    except (TypeError, ValueError):
        return None
    if not isinstance(dados, dict):
        return None
    bruto = dados.get('bloqueio_ate_utc')
    if not bruto:
        return None
    try:
        dt = datetime.fromisoformat(str(bruto))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo:
        return dt.astimezone(UTC).replace(tzinfo=None)
    return dt


def _obter_evento_estado_bloqueio_mais_recente(ip: str) -> LogAuditoria | None:
    if not ip:
        return None
    return (
        LogAuditoria.query
        .filter(LogAuditoria.acao.in_(('SEC_BLOQUEIO_IP_LOGIN','SEC_DESBLOQUEIO_IP_LOGIN_MANUAL')))
        .filter(LogAuditoria.detalhes.contains(f'"ip_alvo": "{ip}"'))
        .order_by(LogAuditoria.id.desc())
        .first()
    )


def obter_bloqueio_ip_login(ip: str | None) -> tuple[bool, datetime | None]:
    ip_norm = _normalizar_ip(ip)
    if not ip_norm:
        return False, None

    if _ip_localhost(ip_norm):
        config = _carregar_config()
        if not config['login_bloquear_localhost']:
            return False, None

    evento = _obter_evento_estado_bloqueio_mais_recente(ip_norm)
    if not evento:
        return False, None
    if evento.acao == 'SEC_DESBLOQUEIO_IP_LOGIN_MANUAL':
        return False, evento.criado_em
    return True, evento.criado_em


def verificar_ip_bloqueado_login(ip: str | None) -> tuple[bool, int]:
    bloqueado, _ = obter_bloqueio_ip_login(ip)
    return (True, 0) if bloqueado else (False, 0)


def _em_cooldown(acao_alerta: str, cooldown_min: int, alvo: str) -> bool:
    inicio_janela = _agora_utc_sem_tz() - timedelta(minutes=cooldown_min)
    return (
        LogAuditoria.query
        .filter(LogAuditoria.acao == acao_alerta)
        .filter(LogAuditoria.criado_em >= inicio_janela)
        .filter(LogAuditoria.detalhes.contains(f'"alvo": "{alvo}"'))
        .first()
        is not None
    )


def _enviar_email_alerta(config: dict[str, Any], assunto: str, corpo: str) -> tuple[bool, str | None]:
    if not config['email_habilitado']:
        return False, None

    if not config['email_smtp_host'] or not config['email_remetente'] or not config['email_destinatarios']:
        return False, 'configuracao_email_incompleta'

    msg = EmailMessage()
    msg['Subject'] = assunto
    msg['From'] = config['email_remetente']
    msg['To'] = ', '.join(config['email_destinatarios'])
    msg.set_content(corpo)

    try:
        if config['email_usar_ssl']:
            cliente = smtplib.SMTP_SSL(config['email_smtp_host'], config['email_smtp_port'], timeout=15)
        else:
            cliente = smtplib.SMTP(config['email_smtp_host'], config['email_smtp_port'], timeout=15)

        with cliente as smtp:
            if config['email_usar_tls'] and not config['email_usar_ssl']:
                smtp.starttls()
            if config['email_smtp_usuario']:
                smtp.login(config['email_smtp_usuario'], config['email_smtp_senha'])
            smtp.send_message(msg)
    except Exception as exc:
        return False, str(exc)

    return True, None


def _enviar_webhook_alerta(config: dict[str, Any], payload: dict[str, Any]) -> tuple[bool, str | None]:
    if not config['webhook_habilitado']:
        return False, None

    if not config['webhook_url']:
        return False, 'webhook_url_nao_configurada'

    dados = json.dumps(payload, ensure_ascii=False, default=str).encode('utf-8')
    req = Request(
        config['webhook_url'],
        data=dados,
        method='POST',
        headers={'Content-Type': 'application/json'},
    )

    try:
        with urlopen(req, timeout=config['webhook_timeout_sec']) as resposta:
            status = getattr(resposta, 'status', 200)
            if int(status) >= 400:
                return False, f'http_status_{status}'
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        return False, str(exc)

    return True, None


def _registrar_alerta(
    acao_alerta: str,
    evento_origem: LogAuditoria,
    detalhes_alerta: dict[str, Any],
    config: dict[str, Any],
) -> None:
    assunto = f'[ALERTA SEGURANCA] {acao_alerta}'
    corpo = json.dumps(detalhes_alerta, ensure_ascii=False, indent=2, default=str)
    email_ok, erro_email = _enviar_email_alerta(config, assunto, corpo)
    webhook_ok, erro_webhook = _enviar_webhook_alerta(config, detalhes_alerta)

    if not email_ok and config['email_habilitado']:
        logging.error(f"[ALERTA TECNICO] Falha ao enviar email: {erro_email}")

    if not webhook_ok and config['webhook_habilitado']:
        logging.error(f"[ALERTA TECNICO] Falha ao enviar webhook: {erro_webhook}")

    registrar_evento_seguro(
        acao_alerta,
        categoria='alerta',
        status='sucesso',
        recurso='seguranca',
        recurso_id=str(evento_origem.id),
        detalhes={
            **detalhes_alerta,
            'canal_email': config['email_habilitado'],
            'canal_webhook': config['webhook_habilitado'],
            'email_enviado': email_ok,
            'webhook_enviado': webhook_ok,
            'erro_email': erro_email,
            'erro_webhook': erro_webhook,
        },
        processar_alertas=False,
    )


def _registrar_bloqueio_ip_login(
    evento_origem: LogAuditoria,
    ip_origem: str,
    ocorrencias: int,
    config: dict[str, Any],
) -> None:
    if not config['login_bloqueio_habilitado']:
        return

    ip_norm = _normalizar_ip(ip_origem)
    if not ip_norm:
        return

    if not config['login_bloquear_localhost'] and _ip_localhost(ip_norm):
        return

    bloqueado, _ = obter_bloqueio_ip_login(ip_norm)
    if bloqueado:
        return

    registrar_evento_seguro(
        'SEC_BLOQUEIO_IP_LOGIN',
        categoria='seguranca',
        status='sucesso',
        recurso='autenticacao',
        recurso_id=ip_norm,
        detalhes={
            'ip_alvo': ip_norm,
            'regra': 'bloqueio_temporario_por_brute_force',
            'tipo_bloqueio': 'ate_desbloqueio_superadmin',
            'ocorrencias': ocorrencias,
            'limite': config['login_limite'],
            'janela_min': config['login_janela_min'],
            'evento_origem_id': evento_origem.id,
            'evento_origem_acao': evento_origem.acao,
            'evento_origem_data_local': _timestamp_local_iso(evento_origem.criado_em, config['fuso']),
        },
        processar_alertas=False,
    )

def desbloquear_ip_login_superadmin(ip: str |None, motivo: str = '') -> tuple[bool, str]:
    ip_norm = _normalizar_ip(ip)
    if not ip_norm:
        return False, 'ip_invalido'
    bloqueado, _ = obter_bloqueio_ip_login(ip_norm)
    if not bloqueado:
        return False, 'IP não está bloqueado'
    registrar_evento_seguro(
        'SEC_DESBLOQUEIO_IP_LOGIN_MANUAL',
        categoria='seguranca',
        status='sucesso',
        recurso='autenticacao',
        recurso_id=ip_norm,
        detalhes={'ip_alvo': ip_norm, 'regra': 'desbloqueio_superadmin', 'motivo': (motivo or 'desbloqueio_manual_superadmin')[:200]},
        processar_alertas=False,
    )
    return True, 'IP desbloqueado com sucesso'

def _valor_login_informado(detalhes_brutos: dict[str, Any]) -> str:
    valor = str(detalhes_brutos.get('login_informado') or '').strip()
    return valor


def _avaliar_brute_force_login(
    evento: LogAuditoria,
    detalhes_brutos: dict[str, Any],
    config: dict[str, Any],
) -> None:
    if evento.acao != 'AUTH_LOGIN_FALHA':
        return

    login_informado = _valor_login_informado(detalhes_brutos)
    ip_origem = _normalizar_ip(evento.ip_origem)
    if not login_informado and not ip_origem:
        return

    inicio_janela = _agora_utc_sem_tz() - timedelta(minutes=config['login_janela_min'])
    consulta = (
        LogAuditoria.query
        .filter(LogAuditoria.acao == 'AUTH_LOGIN_FALHA')
        .filter(LogAuditoria.status == 'falha')
        .filter(LogAuditoria.criado_em >= inicio_janela)
    )

    if ip_origem:
        consulta = consulta.filter(LogAuditoria.ip_origem == ip_origem)
        alvo = f'ip:{ip_origem}'
    else:
        consulta = consulta.filter(LogAuditoria.detalhes.contains(f'"login_informado": "{login_informado}"'))
        alvo = f'login:{login_informado}'

    ocorrencias = consulta.count()
    if ocorrencias < config['login_limite']:
        return

    if ip_origem:
        _registrar_bloqueio_ip_login(evento, ip_origem, ocorrencias, config)

    if _em_cooldown('SEC_ALERTA_BRUTE_FORCE_LOGIN', config['login_cooldown_min'], alvo):
        return

    _registrar_alerta(
        'SEC_ALERTA_BRUTE_FORCE_LOGIN',
        evento,
        {
            'regra': 'brute_force_login',
            'severidade': 'alta',
            'alvo': alvo,
            'alvo_login': login_informado,
            'alvo_ip': ip_origem,
            'ocorrencias': ocorrencias,
            'limite': config['login_limite'],
            'janela_min': config['login_janela_min'],
            'evento_origem_id': evento.id,
            'evento_origem_acao': evento.acao,
            'evento_origem_data_local': _timestamp_local_iso(evento.criado_em, config['fuso']),
        },
        config,
    )


def _fora_do_horario_permitido(hora: int, inicio: int, fim: int) -> bool:
    if inicio == fim:
        return False
    if inicio < fim:
        return not (inicio <= hora < fim)
    return not (hora >= inicio or hora < fim)


def _avaliar_superadmin_fora_horario(evento: LogAuditoria, config: dict[str, Any]) -> None:
    if evento.status != 'sucesso':
        return
    if not evento.usuario_id:
        return
    if evento.acao.startswith('HTTP_'):
        return
    if evento.acao.upper() not in config['superadmin_acoes']:
        return

    usuario = db.session.get(Usuario, int(evento.usuario_id))
    if not usuario or not getattr(usuario, 'is_superadmin', False):
        return

    horario_local = evento.criado_em.replace(tzinfo=UTC).astimezone(_fuso_horario(config['fuso']))
    if not _fora_do_horario_permitido(
        horario_local.hour,
        config['superadmin_hora_inicio'],
        config['superadmin_hora_fim'],
    ):
        return

    alvo = f'superadmin:{evento.usuario_login or usuario.login}|acao:{evento.acao}'
    if _em_cooldown('SEC_ALERTA_SUPERADMIN_FORA_HORARIO', config['superadmin_cooldown_min'], alvo):
        return

    _registrar_alerta(
        'SEC_ALERTA_SUPERADMIN_FORA_HORARIO',
        evento,
        {
            'regra': 'superadmin_fora_horario',
            'severidade': 'media',
            'alvo': alvo,
            'usuario_alvo': evento.usuario_login or usuario.login,
            'evento_origem_id': evento.id,
            'evento_origem_acao': evento.acao,
            'horario_evento_local': horario_local.strftime('%Y-%m-%d %H:%M:%S'),
            'faixa_horario_permitida': f"{config['superadmin_hora_inicio']:02d}:00-{config['superadmin_hora_fim']:02d}:00",
        },
        config,
    )


def _avaliar_exportacao_massiva(evento: LogAuditoria, config: dict[str, Any]) -> None:
    if evento.acao != 'OUVIDORIA_EXPORTAR_CSV' or evento.status != 'sucesso':
        return

    inicio_janela = _agora_utc_sem_tz() - timedelta(minutes=config['export_janela_min'])
    consulta = (
        LogAuditoria.query
        .filter(LogAuditoria.acao == 'OUVIDORIA_EXPORTAR_CSV')
        .filter(LogAuditoria.status == 'sucesso')
        .filter(LogAuditoria.criado_em >= inicio_janela)
    )

    if evento.usuario_id:
        consulta = consulta.filter(LogAuditoria.usuario_id == evento.usuario_id)
        alvo = f'usuario_id:{evento.usuario_id}'
    elif evento.usuario_login:
        consulta = consulta.filter(LogAuditoria.usuario_login == evento.usuario_login)
        alvo = f'usuario_login:{evento.usuario_login}'
    else:
        consulta = consulta.filter(LogAuditoria.ip_origem == evento.ip_origem)
        alvo = f'ip:{evento.ip_origem or "-"}'

    ocorrencias = consulta.count()
    if ocorrencias < config['export_limite']:
        return

    if _em_cooldown('SEC_ALERTA_EXPORTACAO_MASSIVA', config['export_cooldown_min'], alvo):
        return

    _registrar_alerta(
        'SEC_ALERTA_EXPORTACAO_MASSIVA',
        evento,
        {
            'regra': 'exportacao_massiva_logs',
            'severidade': 'alta',
            'alvo': alvo,
            'ocorrencias': ocorrencias,
            'limite': config['export_limite'],
            'janela_min': config['export_janela_min'],
            'evento_origem_id': evento.id,
            'evento_origem_acao': evento.acao,
            'evento_origem_data_local': _timestamp_local_iso(evento.criado_em, config['fuso']),
        },
        config,
    )


def avaliar_alertas_evento(evento: LogAuditoria, detalhes_brutos: dict[str, Any]) -> None:
    if evento.acao.startswith('SEC_ALERTA_'):
        return

    config = _carregar_config()
    if not config['habilitado']:
        return

    try:
        _avaliar_brute_force_login(evento, detalhes_brutos or {}, config)
        _avaliar_superadmin_fora_horario(evento, config)
        _avaliar_exportacao_massiva(evento, config)
    except Exception:
        current_app.logger.exception('Falha ao avaliar regras de alerta de seguranca')
