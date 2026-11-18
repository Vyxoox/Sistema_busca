from flask import render_template, redirect, url_for, flash, request, abort, Blueprint
from flask_login import login_required, current_user

from core import db
from core.audit_policy import audit_event
from models import Funcionario
from services.normalizacao_service import normalizar_maiusculo
from services.auditoria_services import registrar_evento_seguro
from services.busca_service import (
    obter_perfil_usuario,
    PERFIS_TODOS,
    PERFIS_TERCEIRO_COORD,
)
verfunc_bp = Blueprint('verfunc', __name__)


def _funcionario_visivel_para_user(funcionario) -> bool:
    """Aplica a visualizacao o mesmo escopo de perfil da busca e do painel.

    - superadmin / perfis CA.9 e SA.9: acesso total;
    - admin sem perfil: acesso total (paridade com busca_service);
    - CGR.9 / CO.9 / CT.9: somente terceirizados da propria coordenadoria;
    - demais perfis: nenhum acesso.
    """
    perfil = obter_perfil_usuario(current_user)

    if current_user.is_superadmin or perfil in PERFIS_TODOS:
        return True

    if current_user.is_admin and not (current_user.perfil or '').strip():
        return True

    if perfil in PERFIS_TERCEIRO_COORD:
        if str(funcionario.vinculo or '').strip().upper() != 'TERCEIRIZADO':
            return False
        coord = perfil.upper()
        valores = (
            str(funcionario.coordenadoria or '').upper(),
            str(funcionario.area or '').upper(),
            str(funcionario.lotacao or '').upper(),
        )
        return any(coord in valor for valor in valores)

    return False


@verfunc_bp.route('/funcionario/<int:funcionario_id>')
@login_required
@audit_event()
def ver_funcionario(funcionario_id):
    funcionario = db.get_or_404(Funcionario, funcionario_id)

    if not _funcionario_visivel_para_user(funcionario):
        registrar_evento_seguro(
            'FUNCIONARIO_VISUALIZAR_NEGADO',
            categoria='seguranca',
            status='falha',
            recurso='funcionario',
            recurso_id=str(funcionario.id),
            detalhes={
                'motivo': 'fora_do_escopo_do_perfil',
                'perfil': obter_perfil_usuario(current_user),
            },
        )
        abort(404)

    registrar_evento_seguro(
        'FUNCIONARIO_VISUALIZAR',
        categoria='consulta',
        status='sucesso',
        recurso='funcionario',
        recurso_id=str(funcionario.id),
        detalhes={
            'funcionario_nome': funcionario.nome_completo,
            'funcionario_vinculo': funcionario.vinculo,
        },
    )
    return render_template('funcionario_detalhes.html', funcionario=funcionario)


def validar_campos_condicionais(func, vinculo_norm):
    if vinculo_norm == 'SERVIDOR':
        if not (func.matricula or '').strip():
            return 'Matrícula é obrigatória para servidor.'
    elif vinculo_norm == 'TERCEIRIZADO':
        obrigatorios = [
            func.empresa_contratada,
            func.numero_contrato,
            func.gestor_contrato,
            func.fiscal_tecnico,
            func.fiscal_administrativo,
            func.preposto
        ]
        if not all((v or '').strip() for v in obrigatorios):
            return 'Todos os campos de contrato são obrigatórios para terceirizado.'

    if func.situacao and 'ATIVO' not in normalizar_maiusculo(func.situacao):
        if func.data_desligamento is None:
            return 'Data de desligamento é obrigatória quando a situação não for ativa.'

    return None


def preencher_campos_comuns(func, form, prefixo=''):
    from app import (normalizar_maiusculo, normalizar_titulo, normalizar_rg, normalizar_ramal, normalizar_titulo_simples,
                     normalizar_cpf, tratar_nao_se_aplica,parse_date, obter_email_institucional, montar_lotacao)
    func.nome_completo = normalizar_titulo(form.get(f'{prefixo}nome_completo'))
    func.cpf = normalizar_cpf(form.get(f'{prefixo}cpf'))
    func.rg = normalizar_rg(form.get(f'{prefixo}rg'))
    func.cin = tratar_nao_se_aplica(form.get(f'{prefixo}cin'))
    func.titulo_eleitor = tratar_nao_se_aplica(form.get(f'{prefixo}titulo_eleitor'))
    func.pis_pasep = tratar_nao_se_aplica(form.get(f'{prefixo}pis_pasep')) or ''
    func.data_nasc = parse_date(form.get(f'{prefixo}data_nasc'))

    func.endereco_residencial = tratar_nao_se_aplica(form.get(f'{prefixo}endereco_residencial')) or ''
    func.telefone_pessoal = tratar_nao_se_aplica(form.get(f'{prefixo}telefone_pessoal'))
    func.contato_emergencia = tratar_nao_se_aplica(form.get(f'{prefixo}contato_emergencia'))
    func.email_pessoal = tratar_nao_se_aplica(form.get(f'{prefixo}email_pessoal'))
    func.email_institucional = obter_email_institucional(form, prefixo)
    func.ramal = normalizar_ramal(form.get(f'{prefixo}ramal'))

    from core.constante import MAP_FORMA_INGRESSO, MAP_SITUACAO
    func.vinculo = normalizar_maiusculo(form.get(f'{prefixo}vinculo')) or func.vinculo
    func.tipo = normalizar_maiusculo(form.get(f'{prefixo}tipo'))
    func.subtipo_vinculo = normalizar_maiusculo(form.get(f'{prefixo}subtipo_vinculo'))
    
    val_fi = form.get(f'{prefixo}forma_ingresso')
    if val_fi:
        val_fi_clean = str(val_fi).strip()
        func.forma_ingresso = MAP_FORMA_INGRESSO.get(val_fi_clean.upper(), normalizar_titulo(val_fi_clean))
    else:
        func.forma_ingresso = ''

    func.prontuario_funcional = tratar_nao_se_aplica(form.get(f'{prefixo}prontuario_funcional'))

    func.cargo_exercicio = normalizar_titulo(form.get(f'{prefixo}cargo_exercicio'))
    func.cargo_origem = normalizar_titulo(form.get(f'{prefixo}cargo_origem'))

    func.lotacao = montar_lotacao(form, prefixo)
    func.area = normalizar_titulo(form.get(f'{prefixo}area'))
    func.coordenadoria = normalizar_maiusculo(form.get(f'{prefixo}coordenadoria')) or ''

    func.data_ingresso_der = parse_date(form.get(f'{prefixo}data_ingresso_der'))
    func.data_inicio = parse_date(form.get(f'{prefixo}data_inicio'))
    func.data_admissao = parse_date(form.get(f'{prefixo}data_admissao'))

    val_sit = form.get(f'{prefixo}situacao')
    if val_sit:
        val_sit_clean = str(val_sit).strip()
        func.situacao = MAP_SITUACAO.get(val_sit_clean.upper(), normalizar_titulo(val_sit_clean))
    else:
        func.situacao = ''
    func.data_desligamento = parse_date(form.get(f'{prefixo}data_desligamento'))

    func.doe_portaria = tratar_nao_se_aplica(form.get(f'{prefixo}doe_portaria'))
    func.ativo = (normalizar_maiusculo(func.situacao or '') == 'ATIVO')

    vinculo_norm = normalizar_maiusculo(func.vinculo)

    if vinculo_norm == 'SERVIDOR':
        func.matricula = tratar_nao_se_aplica(form.get(f'{prefixo}matricula'))
        func.empresa_contratada = None
        func.numero_contrato = None
        func.gestor_contrato = None
        func.fiscal_tecnico = None
        func.fiscal_administrativo = None
        func.preposto = None
    else:
        func.matricula = None
        func.empresa_contratada = normalizar_titulo_simples(form.get(f'{prefixo}empresa_contratada'))
        func.numero_contrato = tratar_nao_se_aplica(form.get(f'{prefixo}numero_contrato'))
        func.gestor_contrato = normalizar_titulo(form.get(f'{prefixo}gestor_contrato'))
        func.fiscal_tecnico = normalizar_titulo(form.get(f'{prefixo}fiscal_tecnico'))
        func.fiscal_administrativo = normalizar_titulo(form.get(f'{prefixo}fiscal_administrativo'))
        func.preposto = normalizar_titulo(form.get(f'{prefixo}preposto'))
