from flask import render_template, redirect, url_for, flash, request, app, Blueprint
from flask_login import login_required

from core.audit_policy import audit_event
from models import Funcionario
from services.normalizacao_service import normalizar_maiusculo
from services.auditoria_services import registrar_evento_seguro
verfunc_bp = Blueprint('verfunc', __name__)

@verfunc_bp.route('/funcionario/<int:funcionario_id>')
@login_required
@audit_event()
def ver_funcionario(funcionario_id):
    funcionario = Funcionario.query.get_or_404(funcionario_id)
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
    func.email_pessoal = tratar_nao_se_aplica(form.get(f'{prefixo}email_pessoal'))
    func.email_institucional = obter_email_institucional(form, prefixo)
    func.ramal = normalizar_ramal(form.get(f'{prefixo}ramal'))

    func.vinculo = normalizar_maiusculo(form.get(f'{prefixo}vinculo')) or func.vinculo
    func.tipo = normalizar_maiusculo(form.get(f'{prefixo}tipo'))
    func.subtipo_vinculo = normalizar_maiusculo(form.get(f'{prefixo}subtipo_vinculo'))
    func.forma_ingresso = normalizar_titulo(form.get(f'{prefixo}forma_ingresso')) or ''
    func.prontuario_funcional = tratar_nao_se_aplica(form.get(f'{prefixo}prontuario_funcional'))

    func.cargo_exercicio = normalizar_titulo(form.get(f'{prefixo}cargo_exercicio'))
    func.cargo_origem = normalizar_titulo(form.get(f'{prefixo}cargo_origem'))

    func.lotacao = montar_lotacao(form, prefixo)
    func.area = normalizar_titulo(form.get(f'{prefixo}area'))
    func.coordenadoria = normalizar_maiusculo(form.get(f'{prefixo}coordenadoria')) or ''

    func.data_ingresso_der = parse_date(form.get(f'{prefixo}data_ingresso_der'))
    func.data_inicio = parse_date(form.get(f'{prefixo}data_inicio'))
    func.data_admissao = parse_date(form.get(f'{prefixo}data_admissao'))

    func.situacao = normalizar_titulo(form.get(f'{prefixo}situacao')) or ''
    func.data_desligamento = parse_date(form.get(f'{prefixo}data_desligamento'))

    func.doe_portaria = tratar_nao_se_aplica(form.get(f'{prefixo}doe_portaria'))
    func.ativo = True if normalizar_maiusculo(func.situacao or '') == 'ATIVO' else True  # mantém controle lógico ativo

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
