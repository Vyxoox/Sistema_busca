import json
import csv
import io
import os
from datetime import datetime, time, UTC
from zoneinfo import ZoneInfo
from sqlalchemy import func, or_

import xlsxwriter
from flask import Blueprint, render_template, request, send_file, url_for, flash, redirect, current_app
from flask_login import login_required, current_user

from core import db
from core.audit_policy import audit_event
from core.authz import superadmin_required
from models import LogAuditoria
from services.auditoria_services import registrar_evento_seguro
from services.alertas_seguranca import desbloquear_ip_login_superadmin, obter_bloqueio_ip_login

ouvidoria_bp = Blueprint('ouvidoria', __name__)
FUSO_LOCAL = ZoneInfo('America/Sao_Paulo')

# Teto de linhas nas exportacoes de logs (CSV e XLSX) — protege o
# servidor de exports gigantes e mantem os dois formatos equivalentes.
LIMITE_EXPORTACAO_LOGS = 5000

ACOES_DESCRICAO = {
    'AUTH_LOGIN_SUCESSO': 'Login realizado',
    'AUTH_LOGIN_FALHA': 'Falha de login',
    'AUTH_LOGOUT': 'Logout',
    'SEC_DESBLOQUEIO_IP_LOGIN_MANUAL':'Desbloqueio manual de IP',
    'AUTH_ACESSO_NAO_AUTENTICADO': 'Tentativa de acesso sem autenticação',
    'AUTH_SUPERADMIN_NAO_AUTENTICADO': 'Tentativa de acesso superadmin sem autenticação',
    'AUTH_SUPERADMIN_NEGADO': 'Tentativa de acesso superadmin negada',
    'AUTH_LOGIN_BLOQUEADO_IP': 'Login bloqueado por IP temporariamente',
    'SEC_ALERTA_BRUTE_FORCE_LOGIN': 'Alerta de brute force de login',
    'SEC_ALERTA_SUPERADMIN_FORA_HORARIO': 'Alerta de uso de superadmin fora de horário',
    'SEC_ALERTA_EXPORTACAO_MASSIVA': 'Alerta de exportação massiva',
    'SEC_BLOQUEIO_IP_LOGIN': 'Bloqueio temporário de IP por brute force',
    'RELATORIO_EXPORTAR_XLSX': 'Exportação de relatório Excel',
    'OUVIDORIA_VISUALIZAR_LOGS': 'Visualização de logs de ouvidoria',
    'OUVIDORIA_VISUALIZAR_LOG_DETALHE': 'Visualização detalhada de log de ouvidoria',
    'OUVIDORIA_EXPORTAR_CSV': 'Exportação de logs em CSV',
    'OUVIDORIA_EXPORTAR_XLSX': 'Exportação de logs em Excel',
    'USUARIOS_LISTAR': 'Listagem de administradores',
    'USUARIO_CRIAR_ADMIN_SUCESSO': 'Criação de administrador',
    'USUARIO_CRIAR_ADMIN_FALHA': 'Falha ao criar administrador',
    'FUNCIONARIO_INATIVAR_NEGADO': 'Tentativa de inativação sem permissão',
    'FUNCIONARIO_INATIVAR_SUCESSO': 'Inativação de funcionário',
    'FUNCIONARIO_REATIVAR_NEGADO': 'Tentativa de reativação sem permissão',
    'FUNCIONARIO_REATIVAR_SUCESSO': 'Reativação de funcionário',
    'FUNCIONARIO_CADASTRAR_SERVIDOR_NEGADO': 'Tentativa de cadastro de servidor sem permissão',
    'FUNCIONARIO_CADASTRAR_SERVIDOR_FALHA': 'Falha no cadastro de servidor',
    'FUNCIONARIO_CADASTRAR_SERVIDOR_SUCESSO': 'Cadastro de servidor',
    'FUNCIONARIO_CADASTRAR_TERCEIRIZADO_NEGADO': 'Tentativa de cadastro de terceirizado sem permissão',
    'FUNCIONARIO_CADASTRAR_TERCEIRIZADO_FALHA': 'Falha no cadastro de terceirizado',
    'FUNCIONARIO_CADASTRAR_TERCEIRIZADO_SUCESSO': 'Cadastro de terceirizado',
    'FUNCIONARIO_EDITAR_NEGADO': 'Tentativa de edição sem permissão',
    'FUNCIONARIO_EDITAR_FALHA': 'Falha na edição de funcionário',
    'FUNCIONARIO_EDITAR_SUCESSO': 'Edição de funcionário',
    'FUNCIONARIO_REMOVER_FOTO_NEGADO': 'Tentativa de remoção de foto sem permissão',
    'FUNCIONARIO_REMOVER_FOTO_SUCESSO': 'Remoção de foto',
    'FUNCIONARIO_REMOVER_FOTO_SEM_ARQUIVO': 'Remoção de foto sem arquivo',
    'FUNCIONARIO_REMOVER_FOTO_FALHA': 'Falha ao remover foto',
    'BUSCA_REALIZADA': 'Busca de funcionários',
    'BUSCA_COLUNAS_ATUALIZADAS': 'Atualização de colunas da busca',
    'REINDEXAR_NEGADO': 'Tentativa de reindexação sem permissão',
    'REINDEXAR_TODOS_SUCESSO': 'Reindexação completa',
    'REINDEXAR_TODOS_FALHA': 'Falha na reindexação',
    'FUNCIONARIO_VISUALIZAR': 'Visualização de funcionário',
    'USUARIO_RESET_SENHA_SUCESSO': 'Reset de senha de administrador',
    'USUARIO_RESET_SENHA_FALHA':'Falha no reset de senha de administrador',
    'USUARIO_EDITAR_ACESSO_SUCESSO': 'Edicao de acesso de administrador',
    'USUARIO_EDITAR_ACESSO_FALHA': 'Falha na edicao de acesso de administrador',
}

CAMPOS_DESCRICAO = {
    'page': 'Página',
    'filtros': 'Filtros',
    'usuario': 'Usuário',
    'acao': 'Ação',
    'status': 'Status',
    'data_inicio': 'Data inicial',
    'data_fim': 'Data final',
    'q': 'Busca',
    'vinculo': 'Vínculo',
    'rota_solicitada': 'Rota solicitada',
    'total_resultados': 'Total de resultados',
    'total_linhas': 'Total de linhas',
    'login_informado': 'Login informado',
    'perfil_informado': 'Perfil informado',
    'motivo': 'Motivo',
    'error': 'Erro',
    'total_usuarios': 'Total de usuários',
    'total_colunas': 'Total de colunas',
    'colunas': 'Colunas',
    'funcionario_nome': 'Funcionário',
    'funcionario_vinculo': 'Vínculo do funcionário',
    'situacao': 'Situação',
    'foto_removida': 'Foto removida',
    'nome_informado': 'Nome informado',
    'cpf_informado': 'CPF informado',
    'cpf': 'CPF',
    'matricula': 'Matrícula',
    'coordenadoria': 'Coordenadoria',
    'empresa_contratada': 'Empresa contratada',
    'numero_contrato': 'Número do contrato',
    'tem_foto': 'Tem foto',
    'total_alteracoes': 'Total de alterações',
    'alteracoes': 'Alterações',
    'endpoint': 'Endpoint',
    'status_code': 'Status HTTP',
    'duracao_ms': 'Duração (ms)',
    'query_params': 'Parâmetros de query',
    'form_data': 'Dados de formulário',
    'payload_json': 'Payload JSON',
    'arquivos': 'Arquivos',
    'regra': 'Regra',
    'severidade': 'Severidade',
    'alvo': 'Alvo',
    'alvo_login': 'Login alvo',
    'alvo_ip': 'IP alvo',
    'ip_alvo': 'IP alvo',
    'segundos_restantes_bloqueio': 'Segundos restantes de bloqueio',
    'bloqueio_min': 'Bloqueio (minutos)',
    'bloqueio_ate_utc': 'Bloqueio até (UTC)',
    'usuario_alvo': 'Usuário alvo',
    'evento_origem_id': 'ID do evento de origem',
    'evento_origem_acao': 'Ação do evento de origem',
    'evento_origem_data_local': 'Data/hora local do evento de origem',
    'horario_evento_local': 'Horário local do evento',
    'faixa_horario_permitida': 'Faixa de horário permitida',
    'canal_email': 'Canal email habilitado',
    'canal_webhook': 'Canal webhook habilitado',
    'email_enviado': 'Email enviado',
    'webhook_enviado': 'Webhook enviado',
    'erro_email': 'Erro de email',
    'erro_webhook': 'Erro de webhook',
    'request_id': 'Request ID',
    'correlation_id': 'Correlation ID',
    'session_id': 'Session ID',
    'timestamp_utc': 'Timestamp UTC',
    'campo': 'Campo',
    'antes': 'Antes',
    'depois': 'Depois',
}


def _parse_data(valor: str | None):
    if not valor:
        return None
    try:
        return datetime.strptime(valor, '%Y-%m-%d').date()
    except ValueError:
        return None

def _ip_alvo_do_evento(recurso_id: str | None, detalhes: str | None) -> str:
    ip = str(recurso_id or '').strip()
    if ip:
        return ip
    try:
        obj = json.loads(detalhes or '{}')
    except (TypeError, ValueError):
        return ''
    if isinstance(obj, dict):
        return str(obj.get('ip_alvo') or '').strip()
    return ''

def _ips_bloqueados_atualmente(limite_eventos: int = 5000) -> list[str]:
    eventos = (
        LogAuditoria.query
        .with_entities(LogAuditoria.acao, LogAuditoria.recurso_id, LogAuditoria.detalhes)
        .filter(LogAuditoria.acao.in_(('SEC_BLOQUEIO_IP_LOGIN', 'SEC_DESBLOQUEIO_IP_LOGIN_MANUAL')))
        .order_by(LogAuditoria.criado_em.desc())
        .limit(limite_eventos)
        .all()
    )

    estado_por_ip: dict[str, bool] = {}
    for acao, recurso_id, detalhes in eventos:
        ip = _ip_alvo_do_evento(recurso_id, detalhes)
        if not ip or ip in estado_por_ip:
            continue
        estado_por_ip[ip] = (acao == 'SEC_BLOQUEIO_IP_LOGIN')

    return sorted([ip for ip, bloqueado in estado_por_ip.items() if bloqueado])

def _consulta_logs(ips_bloqueados_conhecidos: list[str] | None = None):
    consulta = LogAuditoria.query

    q = (request.args.get('q') or '').strip()
    usuario = (request.args.get('usuario') or '').strip()
    acao = (request.args.get('acao') or '').strip()
    status = (request.args.get('status') or '').strip().lower()
    data_inicio = _parse_data(request.args.get('data_inicio'))
    data_fim = _parse_data(request.args.get('data_fim'))
    somente_bloqueados = (request.args.get('somente_bloqueados') or '').strip().lower() in {'true', '1', 'on', 'sim', 'yes'}
    ip_bloqueado= (request.args.get('ip_bloqueado') or '').strip()
    tipo_evento = (request.args.get('tipo_evento') or '').strip().lower()

    if q:
        termo_like = f"%{q.lower()}%"
        condicoes = [
            func.lower(func.coalesce(LogAuditoria.usuario_login, '')).like(termo_like),
            func.lower(func.coalesce(LogAuditoria.acao, '')).like(termo_like),
            func.lower(func.coalesce(LogAuditoria.categoria, '')).like(termo_like),
            func.lower(func.coalesce(LogAuditoria.status, '')).like(termo_like),
            func.lower(func.coalesce(LogAuditoria.recurso, '')).like(termo_like),
            func.lower(func.coalesce(LogAuditoria.recurso_id, '')).like(termo_like),
            func.lower(func.coalesce(LogAuditoria.metodo_http, '')).like(termo_like),
            func.lower(func.coalesce(LogAuditoria.rota, '')).like(termo_like),
            func.lower(func.coalesce(LogAuditoria.ip_origem, '')).like(termo_like),
            func.lower(func.coalesce(LogAuditoria.detalhes, '')).like(termo_like),
        ]
        if q.isdigit():
            condicoes.append(LogAuditoria.id == int(q))
        consulta = consulta.filter(or_(*condicoes))

    if usuario:
        consulta = consulta.filter(func.lower(LogAuditoria.usuario_login).like(f'%{usuario.lower()}%'))
    if acao:
        consulta = consulta.filter(LogAuditoria.acao == acao)

    if status in {'sucesso', 'falha'}:
        consulta = consulta.filter(LogAuditoria.status == status)

    if data_inicio:
        inicio_local = datetime.combine(data_inicio, time.min).replace(tzinfo=FUSO_LOCAL)
        inicio_utc = inicio_local.astimezone(UTC).replace(tzinfo=None)
        consulta = consulta.filter(LogAuditoria.criado_em >= inicio_utc)

    if data_fim:
        fim_local = datetime.combine(data_fim, time.max).replace(tzinfo=FUSO_LOCAL)
        fim_utc = fim_local.astimezone(UTC).replace(tzinfo=None)
        consulta = consulta.filter(LogAuditoria.criado_em <= fim_utc)

    if somente_bloqueados:
        ips_bloqueados = (
            ips_bloqueados_conhecidos
            if ips_bloqueados_conhecidos is not None
            else _ips_bloqueados_atualmente()
        )
        if ips_bloqueados:
            consulta = consulta.filter(LogAuditoria.recurso_id.in_(ips_bloqueados))
        else:
            consulta = consulta.filter(LogAuditoria.id == -1)

    if ip_bloqueado:
        consulta = consulta.filter(
            or_(
                LogAuditoria.recurso_id == ip_bloqueado,
                LogAuditoria.ip_origem == ip_bloqueado,
                LogAuditoria.detalhes.contains(f'"ip_alvo": "{ip_bloqueado}"')
            )
        )

    if tipo_evento == 'alerta':
        consulta = consulta.filter(
            (LogAuditoria.categoria == 'alerta') |
            (LogAuditoria.acao.like('SEC_ALERTA_%'))
        )
    elif tipo_evento == 'falha':
        consulta = consulta.filter(LogAuditoria.status == 'falha').filter(
            ~(LogAuditoria.categoria == 'alerta') &
            ~(LogAuditoria.acao.like('SEC_ALERTA_%'))
        )
    elif tipo_evento == 'operacao':
        consulta = consulta.filter(LogAuditoria.status != 'falha').filter(
            ~(LogAuditoria.categoria == 'alerta') &
            ~(LogAuditoria.acao.like('SEC_ALERTA_%'))
        )

    filtros = {
        'q': q,
        'usuario': usuario,
        'acao': acao,
        'status': status,
        'data_inicio': request.args.get('data_inicio', ''),
        'data_fim': request.args.get('data_fim', ''),
        'somente_bloqueados': '1' if somente_bloqueados else '',
        'ip_bloqueado': ip_bloqueado,
        'tipo_evento': tipo_evento,
    }
    return consulta, filtros

def _filtros_ativos(filtros: dict[str, str]) ->  list[str]:
    ativos: list[str] = []
    if (filtros.get('q') or '').strip():
        ativos.append(f'Busca Geral: "{filtros["q"]}"')
    if (filtros.get('usuario') or '').strip():
        ativos.append(f'Usuários: "{filtros["usuario"]}"')
    if (filtros.get('acao') or '').strip():
        ativos.append(f'Ação: "{formatar_acao(filtros["acao"])}"')
    if (filtros.get('status') or '').strip():
        ativos.append(f'Status: "{filtros["status"]}"')
    if (filtros.get('data_inicio') or '').strip():
        ativos.append(f'Data de início: "{filtros["data_inicio"]}"')
    if (filtros.get('data_fim') or '').strip():
        ativos.append(f'Data Final: "{filtros["data_fim"]}"')
    if (filtros.get('somente_bloqueados') or '').strip():
        ativos.append('Somente IPs bloqueados agora')
    if (filtros.get('ip_bloqueado') or '').strip():
        ativos.append(f'IP bloqueado: "{filtros["ip_bloqueado"]}"')
    if (filtros.get('tipo_evento') or '').strip():
        ativos.append(f'Tipo de evento: "{filtros["tipo_evento"]}"')
    return ativos


def _descricao_campo(chave: str) -> str:
    if chave in CAMPOS_DESCRICAO:
        return CAMPOS_DESCRICAO[chave]
    return chave.replace('_', ' ').capitalize()


def formatar_acao(acao: str | None) -> str:
    if not acao:
        return '-'
    if acao in ACOES_DESCRICAO:
        return ACOES_DESCRICAO[acao]
    return str(acao).replace('_', ' ').title()


def formatar_detalhes(detalhes: str | None) -> str:
    if not detalhes:
        return '-'

    try:
        valor = json.loads(detalhes)
    except (TypeError, ValueError):
        return str(detalhes)

    if not isinstance(valor, dict):
        return str(valor)

    partes: list[str] = []
    for chave, conteudo in valor.items():
        rotulo = _descricao_campo(str(chave))

        if chave == 'alteracoes' and isinstance(conteudo, list):
            total = sum(
                1 for item in conteudo
                if isinstance(item, dict) and str(item.get('campo') or '').strip()
            )
            partes.append(f"{rotulo}: {total} campo(s) alterado(s)" if total else f"{rotulo}: -")
            continue

        if isinstance(conteudo, dict):
            internos = []
            for k, v in conteudo.items():
                texto_v = str(v).strip()
                if texto_v:
                    internos.append(f"{_descricao_campo(str(k))}: {texto_v}")
            partes.append(f"{rotulo}: {', '.join(internos) if internos else 'sem filtros'}")
            continue

        if isinstance(conteudo, list):
            itens = [str(item).strip() for item in conteudo if str(item).strip()]
            partes.append(f"{rotulo}: {', '.join(itens) if itens else '-'}")
            continue

        texto = str(conteudo).strip()
        if texto:
            partes.append(f"{rotulo}: {texto}")

    return ' | '.join(partes) if partes else '-'


def _utc_para_local(valor: datetime | None) -> datetime | None:
    if not valor:
        return None
    dt = valor
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(FUSO_LOCAL)


def formatar_datahora_local(valor: datetime | None, formato: str = '%d/%m/%Y %H:%M:%S') -> str:
    convertido = _utc_para_local(valor)
    if not convertido:
        return ''
    return convertido.strftime(formato)


def tipo_evento(log: LogAuditoria) -> str:
    acao = (log.acao or '').upper()
    if acao.startswith('SEC_ALERTA_') or log.categoria == 'alerta':
        return 'alerta'
    if log.status == 'falha':
        return 'falha'
    return 'operacao'


def resumo_curto_detalhes(detalhes: str | None, limite: int = 120) -> str:
    resumo = formatar_detalhes(detalhes)
    if not resumo or resumo == '-':
        return '-'
    if len(resumo) <= limite:
        return resumo
    return f'{resumo[:limite - 3]}...'


def parse_detalhes_para_objeto(detalhes: str | None):
    if not detalhes:
        return None
    try:
        return json.loads(detalhes)
    except (TypeError, ValueError):
        return detalhes


def formatar_json_pretty(valor) -> str:
    if valor is None:
        return ''
    if isinstance(valor, str):
        return valor
    try:
        return json.dumps(valor, ensure_ascii=False, indent=2, default=str)
    except (TypeError, ValueError):
        return str(valor)

def _valor_para_texto(valor) -> str:
    if valor is None:
        return '-'
    if isinstance(valor, str):
        txt = valor.strip()
        return txt if txt else '-'
    if isinstance(valor,(dict, list, tuple)):
        return formatar_json_pretty(valor)
    return str(valor)

def extrair_alteracoes_struct(detalhes_obj) -> list[dict[str, str]]:
    if not isinstance(detalhes_obj, dict):
        return []

    bruto = detalhes_obj.get('alteracoes')
    if not isinstance(bruto, list):
        return []

    linhas: list[dict[str, str]] = []
    for item in bruto:
        if not isinstance(item, dict):
            continue
        campo_raw = str(item.get('campo') or '').strip()
        if not campo_raw:
            continue
        linhas.append({
            'campo': _descricao_campo(campo_raw),
            'antes': _valor_para_texto(item.get('antes')),
            'depois': _valor_para_texto(item.get('depois')),
        })
    return linhas

def detalhes_em_linhas(detalhes_obj) -> list[tuple[str, str]]:
    if not isinstance(detalhes_obj, dict):
        return []

    linhas: list[tuple[str, str]] = []
    for chave, valor in detalhes_obj.items():
        rotulo = _descricao_campo(str(chave))
        if chave == 'alteracoes':
            continue
        if isinstance(valor, (dict, list, tuple)):
            valor_txt = formatar_json_pretty(valor)
        else:
            valor_txt = str(valor).strip() if valor is not None else ''
        linhas.append((rotulo, valor_txt or '-'))
    return linhas


def _retorno_logs_seguro(valor: str | None) -> str:
    retorno = (valor or '').strip()
    if retorno.startswith('/ouvidoria/logs'):
        return retorno
    return ''


# Mitigacao de CSV/Excel formula injection (OWASP): celulas que comecam com
# estes caracteres sao interpretadas como formula pelo Excel/LibreOffice.
_PREFIXES_FORMULA_CSV = ('=', '+', '-', '@', '\t', '\r')


def _celula_csv_segura(valor) -> str:
    texto = '' if valor is None else str(valor)
    if texto.startswith(_PREFIXES_FORMULA_CSV):
        return f"'{texto}"
    return texto


@ouvidoria_bp.route('/ouvidoria/logs')
@login_required
@superadmin_required
@audit_event()
def logs_ouvidoria():
    page = max(request.args.get('page', 1, type=int), 1)
    per_page = min(max(request.args.get('per_page', 50, type=int), 10), 200)

    ips_bloqueados_ativos = _ips_bloqueados_atualmente()
    total_ips_bloqueados = len(ips_bloqueados_ativos)
    consulta, filtros = _consulta_logs(ips_bloqueados_conhecidos=ips_bloqueados_ativos)

    total = consulta.count()
    total_pages = max((total + per_page - 1) // per_page, 1)

    if page > total_pages:
        page = total_pages

    logs = (
        consulta.order_by(LogAuditoria.criado_em.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    totais_status = dict(
        consulta
        .with_entities(LogAuditoria.status, func.count(LogAuditoria.id))
        .group_by(LogAuditoria.status)
        .all()
    )
    total_sucesso = int(totais_status.get('sucesso', 0))
    total_falha = int(totais_status.get('falha', 0))
    total_alerta = int(
        consulta
        .filter(
            (LogAuditoria.categoria == 'alerta')
            | (LogAuditoria.acao.like('SEC_ALERTA_%'))
        )
        .count()
    )

    acoes_disponiveis = [
        linha[0]
        for linha in (
            LogAuditoria.query
            .with_entities(LogAuditoria.acao)
            .distinct()
            .order_by(LogAuditoria.acao.asc())
            .all()
        )
        if linha[0]
    ]

    registrar_evento_seguro(
        'OUVIDORIA_VISUALIZAR_LOGS',
        categoria='ouvidoria',
        recurso='logs_auditoria',
        detalhes={'page': page, 'filtros': filtros},
    )

    retorno = request.full_path.rstrip('?')
    if not retorno:
        retorno = request.path

    return render_template(
        'ouvidoria_logs.html',
        logs=logs,
        filtros=filtros,
        page=page,
        per_page=per_page,
        total=total,
        total_pages=total_pages,
        acoes_disponiveis=acoes_disponiveis,
        formatar_acao=formatar_acao,
        formatar_detalhes=formatar_detalhes,
        formatar_datahora_local=formatar_datahora_local,
        resumo_curto_detalhes=resumo_curto_detalhes,
        tipo_evento=tipo_evento,
        total_sucesso=total_sucesso,
        total_falha=total_falha,
        total_alerta=total_alerta,
        retorno=retorno,
        ips_bloqueados_ativos=ips_bloqueados_ativos,
        total_ips_bloqueados=total_ips_bloqueados,
        filtros_ativos = _filtros_ativos(filtros),
    )


@ouvidoria_bp.route('/ouvidoria/logs/<int:log_id>')
@login_required
@superadmin_required
@audit_event()
def detalhe_log_ouvidoria(log_id: int):
    log = db.get_or_404(LogAuditoria, log_id)
    retorno = _retorno_logs_seguro(request.args.get('retorno')) or url_for('ouvidoria.logs_ouvidoria')
    detalhes_obj = parse_detalhes_para_objeto(log.detalhes)
    ip_alvo = ''
    if isinstance(detalhes_obj, dict):
        ip_alvo = str(detalhes_obj.get('ip_alvo') or '').strip()
    if not ip_alvo:
        ip_alvo = str(log.recurso_id or '').strip()

    bloqueio_ativo = False
    if ip_alvo:
        bloqueio_ativo, _ = obter_bloqueio_ip_login(ip_alvo)

    registrar_evento_seguro(
        'OUVIDORIA_VISUALIZAR_LOG_DETALHE',
        categoria='ouvidoria',
        recurso='logs_auditoria',
        recurso_id=str(log.id),
        detalhes={'log_id': log.id},
    )

    return render_template(
        'ouvidoria_log_detalhe.html',
        log=log,
        retorno=retorno,
        detalhes_obj=detalhes_obj,
        detalhes_linhas=detalhes_em_linhas(detalhes_obj),
        detalhes_pretty=formatar_json_pretty(detalhes_obj),
        formatar_acao=formatar_acao,
        formatar_detalhes=formatar_detalhes,
        formatar_datahora_local=formatar_datahora_local,
        tipo_evento=tipo_evento,
        alteracoes_struct=extrair_alteracoes_struct(detalhes_obj),
        ip_alvo=ip_alvo,
        bloqueio_ativo=bloqueio_ativo,
    )


@ouvidoria_bp.route('/ouvidoria/logs/exportar.csv')
@login_required
@superadmin_required
@audit_event()
def exportar_logs_csv():
    consulta, filtros = _consulta_logs()
    logs = consulta.order_by(LogAuditoria.criado_em.desc()).limit(LIMITE_EXPORTACAO_LOGS).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=';')
    writer.writerow([
        'data_hora',
        'usuario',
        'acao',
        'categoria',
        'status',
        'recurso',
        'recurso_id',
        'ip',
        'rota',
        'detalhes',
    ])

    for log in logs:
        writer.writerow([
            _celula_csv_segura(formatar_datahora_local(log.criado_em)),
            _celula_csv_segura(log.usuario_login or ''),
            _celula_csv_segura(log.acao or ''),
            _celula_csv_segura(log.categoria or ''),
            _celula_csv_segura(log.status or ''),
            _celula_csv_segura(log.recurso or ''),
            _celula_csv_segura(log.recurso_id or ''),
            _celula_csv_segura(log.ip_origem or ''),
            _celula_csv_segura(log.rota or ''),
            _celula_csv_segura(log.detalhes or ''),
        ])

    registrar_evento_seguro(
        'OUVIDORIA_EXPORTAR_CSV',
        categoria='ouvidoria',
        recurso='logs_auditoria',
        detalhes={'filtros': filtros, 'total_linhas': len(logs)},
    )

    conteudo = buffer.getvalue().encode('utf-8-sig')
    arquivo = io.BytesIO(conteudo)
    arquivo.seek(0)

    return send_file(
        arquivo,
        as_attachment=True,
        download_name=f'logs_ouvidoria_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv',
        mimetype='text/csv',
    )


# ============================================================
# Exportacao XLSX dos logs — mesmo visual do relatorio de
# funcionarios (routes/planilha.py): titulo com metadados,
# zebra, data/hora como celula real, status colorido e coluna
# de detalhes legivel. O CSV continua disponivel para uso
# automatizado (mesmos dados, mesmos filtros).
# ============================================================

# Paleta espelhada de routes/planilha.py (identidade visual unica
# dos relatorios exportados; se mudar la, mude aqui tambem).
COR_CABECALHO_LOGS = '#2F5597'
COR_ZEBRA_LOGS = '#F5F7FA'
COR_SUBTITULO_LOGS = '#7F7F7F'
COR_STATUS_SUCESSO = '#006100'
COR_STATUS_FALHA = '#9C0006'

# (atributo do LogAuditoria, rotulo, largura minima, largura maxima)
COLUNAS_LOGS_XLSX = [
    ('id', 'ID', 6, 10),
    ('criado_em', 'DATA/HORA', 17, 18),
    ('usuario_login', 'USUÁRIO', 12, 20),
    ('acao', 'AÇÃO', 14, 40),
    ('categoria', 'CATEGORIA', 12, 16),
    ('status', 'STATUS', 10, 12),
    ('recurso', 'RECURSO', 14, 26),
    ('recurso_id', 'ID DO RECURSO', 12, 16),
    ('ip_origem', 'IP DE ORIGEM', 13, 16),
    ('rota', 'ROTA', 14, 30),
    ('detalhes', 'DETALHES', 80, 100),
]

COLUNAS_CENTRALIZADAS_LOGS = {
    'ID', 'DATA/HORA', 'USUÁRIO', 'CATEGORIA', 'STATUS',
    'ID DO RECURSO', 'IP DE ORIGEM',
}


def _valor_texto_log(log, campo):
    if campo == 'detalhes':
        return formatar_json_pretty(parse_detalhes_para_objeto(getattr(log, 'detalhes', None)))
    valor = getattr(log, campo, None)
    if valor is None:
        return ''
    return str(valor).strip()


def _largura_coluna_log(logs, campo, minima, maxima):
    if campo == 'criado_em':
        # celula de data/hora: exibicao fixa em dd/mm/aaaa hh:mm
        return minima
    maior = 0
    for log in logs:
        maior = max(maior, len(_valor_texto_log(log, campo)))
    return min(max(maior + 2, minima), maxima)


def _escrever_logs_xlsx(ws, workbook, logs, meta):
    """Escreve a planilha de logs (titulo, metadados e tabela).

    Funcao pura de apresentacao (sem request/current_app), no mesmo
    esquema do _escrever_relatorio_xlsx do relatorio de funcionarios.
    """
    total_colunas = len(COLUNAS_LOGS_XLSX)
    linha_titulo = 0
    linha_meta = 1
    linha_cabecalho = 3
    primeira_linha_dados = 4

    titulo_fmt = workbook.add_format({
        'font_name': 'Calibri', 'font_size': 16, 'bold': True,
        'font_color': COR_CABECALHO_LOGS, 'valign': 'vcenter',
    })
    meta_fmt = workbook.add_format({
        'font_name': 'Calibri', 'font_size': 9, 'italic': True,
        'font_color': COR_SUBTITULO_LOGS, 'valign': 'vcenter',
        'bottom': 1, 'bottom_color': COR_CABECALHO_LOGS,
    })
    cabecalho_fmt = workbook.add_format({
        'font_name': 'Calibri', 'font_size': 10, 'bold': True,
        'bg_color': COR_CABECALHO_LOGS, 'font_color': 'white',
        'align': 'center', 'valign': 'vcenter', 'text_wrap': True,
        'border': 1,
    })

    base_celula = {
        'font_name': 'Calibri', 'font_size': 9,
        'border': 1, 'text_wrap': True, 'valign': 'vcenter',
    }

    def _formato(centralizada, zebra, data=False):
        conf = dict(base_celula)
        conf['align'] = 'center' if centralizada else 'left'
        if zebra:
            conf['bg_color'] = COR_ZEBRA_LOGS
        if data:
            conf['num_format'] = 'dd/mm/yyyy hh:mm'
        return workbook.add_format(conf)

    formatos = {}
    for centralizada in (False, True):
        for zebra in (False, True):
            formatos[(centralizada, zebra)] = _formato(centralizada, zebra)
            formatos[(centralizada, zebra, 'data')] = _formato(centralizada, zebra, data=True)

    cache_status = {}

    def _formato_status(valor, zebra):
        cor = COR_STATUS_SUCESSO if valor == 'sucesso' else COR_STATUS_FALHA
        chave = (cor, zebra)
        if chave not in cache_status:
            conf = dict(base_celula)
            conf.update({'align': 'center', 'bold': True, 'font_color': cor})
            if zebra:
                conf['bg_color'] = COR_ZEBRA_LOGS
            cache_status[chave] = workbook.add_format(conf)
        return cache_status[chave]

    # ---------------- titulo e metadados ----------------
    partes = [f"Emitido em {meta['emitido_em']}"]
    if meta.get('usuario'):
        partes.append(f"por {meta['usuario']}")
    filtros = [str(item) for item in (meta.get('filtros') or [])]
    resumo_filtros = ' · '.join(filtros) if filtros else 'nenhum (todos os registros)'
    partes.append(f'Filtros: {resumo_filtros}')
    total_filtro = int(meta.get('total_filtro') or 0)
    total_linhas = int(meta.get('total_linhas') or len(logs))
    if total_filtro > total_linhas:
        partes.append(
            f'Total no filtro: {total_filtro} · Exportando os {total_linhas} '
            f"mais recentes (limite de {int(meta.get('limite') or 0)})"
        )
    else:
        partes.append(f"Total: {total_linhas} registro{'s' if total_linhas != 1 else ''}")

    ws.merge_range(linha_titulo, 0, linha_titulo, total_colunas - 1,
                   'LOGS DE OUVIDORIA E SEGURANÇA', titulo_fmt)
    ws.set_row(linha_titulo, 30)

    ws.merge_range(linha_meta, 0, linha_meta, total_colunas - 1,
                   ' · '.join(partes), meta_fmt)
    ws.set_row(linha_meta, 18)
    ws.set_row(2, 6)

    # ---------------- cabecalho da tabela ----------------
    for coluna, (_, rotulo, _, _) in enumerate(COLUNAS_LOGS_XLSX):
        ws.write(linha_cabecalho, coluna, rotulo, cabecalho_fmt)
    ws.set_row(linha_cabecalho, 30)

    # ---------------- dados ----------------
    for indice, log in enumerate(logs):
        num_linha = primeira_linha_dados + indice
        zebra = indice % 2 == 1
        for coluna, (campo, rotulo, _, _) in enumerate(COLUNAS_LOGS_XLSX):
            centralizada = rotulo in COLUNAS_CENTRALIZADAS_LOGS

            if campo == 'criado_em':
                momento = _utc_para_local(getattr(log, 'criado_em', None))
                if momento is not None:
                    ws.write_datetime(
                        num_linha, coluna, momento.replace(tzinfo=None),
                        formatos[(centralizada, zebra, 'data')],
                    )
                else:
                    ws.write(num_linha, coluna, '', formatos[(centralizada, zebra)])
                continue

            valor = _valor_texto_log(log, campo)
            if campo == 'status' and valor in ('sucesso', 'falha'):
                ws.write(num_linha, coluna, valor, _formato_status(valor, zebra))
            elif campo == 'id' and valor != '':
                ws.write_number(num_linha, coluna, int(valor),
                                formatos[(centralizada, zebra)])
            else:
                ws.write(num_linha, coluna, valor, formatos[(centralizada, zebra)])
        # Sem set_row nas linhas de dados: altura automatica — o Excel
        # expande a linha ate o JSON de DETALHES inteiro ficar visivel.

    # ---------------- larguras ----------------
    for coluna, (campo, _, minima, maxima) in enumerate(COLUNAS_LOGS_XLSX):
        ws.set_column(coluna, coluna,
                      _largura_coluna_log(logs, campo, minima, maxima))

    # ---------------- navegacao ----------------
    ws.freeze_panes(primeira_linha_dados, 0)
    ws.autofilter(linha_cabecalho, 0, linha_cabecalho + len(logs),
                  total_colunas - 1)
    # no papel repete o CABECALHO da tabela no topo de cada pagina
    ws.repeat_rows(linha_cabecalho)
    ws.hide_gridlines(2)
    # ID do recurso numerico segue texto — sem triangulo verde no Excel
    ws.ignore_errors({'number_stored_as_text': True})

    # ---------------- impressao ----------------
    ws.set_landscape()
    ws.fit_to_pages(1, 0)
    ws.center_horizontally()
    ws.set_paper(9)  # A4
    ws.set_margins(0.3, 0.5, 1.2, 0.5)

    logo_esquerda = meta.get('logo_esquerda')
    logo_direita = meta.get('logo_direita')
    if (logo_esquerda and logo_direita
            and os.path.isfile(logo_esquerda) and os.path.isfile(logo_direita)):
        ws.set_header(
            '&L&G'
            '&C&"Calibri,Bold"&12 COORDENADORIA GERAL REGIONAL - CGR.9'
            '&R&G',
            {
                'image_left': logo_esquerda,
                'image_right': logo_direita,
                'image_left_scale': 0.05,
                'image_right_scale': 0.4,
                'image_right_margin_right': 0.6,
                'image_right_margin_top': 0.6,
                'image_left_margin': 2.5,
            },
        )

    ws.set_footer(
        '&LPágina &P de &N'
        '&CEmitido em: &D'
        f'&RTotal: {total_linhas}',
        {'margin': 0.2},
    )


@ouvidoria_bp.route('/ouvidoria/logs/exportar.xlsx')
@login_required
@superadmin_required
@audit_event()
def exportar_logs_xlsx():
    consulta, filtros = _consulta_logs()
    total_filtro = consulta.count()
    logs = (
        consulta.order_by(LogAuditoria.criado_em.desc())
        .limit(LIMITE_EXPORTACAO_LOGS)
        .all()
    )

    meta = {
        'emitido_em': datetime.now(FUSO_LOCAL).strftime('%d/%m/%Y %H:%M'),
        'usuario': str(getattr(current_user, 'login', '') or ''),
        'filtros': _filtros_ativos(filtros),
        'total_filtro': total_filtro,
        'total_linhas': len(logs),
        'limite': LIMITE_EXPORTACAO_LOGS,
        'logo_esquerda': os.path.join(current_app.root_path, 'static', 'imagen2.jpg'),
        'logo_direita': os.path.join(current_app.root_path, 'static', 'Imagem1.png'),
    }

    buffer = io.BytesIO()
    workbook = xlsxwriter.Workbook(buffer, {'in_memory': True})
    ws = workbook.add_worksheet('LOGS')
    _escrever_logs_xlsx(ws, workbook, logs, meta)
    workbook.close()
    buffer.seek(0)

    registrar_evento_seguro(
        'OUVIDORIA_EXPORTAR_XLSX',
        categoria='ouvidoria',
        recurso='logs_auditoria',
        detalhes={
            'filtros': filtros,
            'total_linhas': len(logs),
            'total_filtro': total_filtro,
        },
    )

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f'logs_ouvidoria_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )

@ouvidoria_bp.route('/ouvidoria/ip/desbloquear', methods=['POST'])
@login_required
@superadmin_required
@audit_event()
def desbloquear_ip_login():
    ip = (request.form.get('ip') or '').strip()
    motivo = (request.form.get('motivo') or '').strip()
    retorno = _retorno_logs_seguro(request.form.get('retorno')) or url_for('ouvidoria.logs_ouvidoria')
    ok, msg = desbloquear_ip_login_superadmin(ip, motivo)
    flash(msg, 'success' if ok else 'error')
    return redirect(retorno)
