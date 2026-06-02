import json
import csv
import io
from datetime import datetime, time, UTC
from zoneinfo import ZoneInfo
from sqlalchemy import func, or_

from flask import Blueprint, render_template, request, send_file, url_for, flash, redirect
from flask_login import login_required

from core.audit_policy import audit_event
from core.authz import superadmin_required
from models import LogAuditoria
from services.auditoria_services import registrar_evento_seguro
from services.alertas_seguranca import desbloquear_ip_login_superadmin, obter_bloqueio_ip_login

ouvidoria_bp = Blueprint('ouvidoria', __name__)
FUSO_LOCAL = ZoneInfo('America/Sao_Paulo')

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

def _consulta_logs():
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
        ips_bloqueados = _ips_bloqueados_atualmente()
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


@ouvidoria_bp.route('/ouvidoria/logs')
@login_required
@superadmin_required
@audit_event()
def logs_ouvidoria():
    page = max(request.args.get('page', 1, type=int), 1)
    per_page = min(max(request.args.get('per_page', 50, type=int), 10), 200)

    consulta, filtros = _consulta_logs()
    ips_bloqueados_ativos = _ips_bloqueados_atualmente()
    total_ips_bloqueados = len(ips_bloqueados_ativos)

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
    log = LogAuditoria.query.get_or_404(log_id)
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
    logs = consulta.order_by(LogAuditoria.criado_em.desc()).limit(5000).all()

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
            formatar_datahora_local(log.criado_em),
            log.usuario_login or '',
            log.acao or '',
            log.categoria or '',
            log.status or '',
            log.recurso or '',
            log.recurso_id or '',
            log.ip_origem or '',
            log.rota or '',
            log.detalhes or '',
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
