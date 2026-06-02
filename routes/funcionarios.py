from flask import Blueprint, redirect, url_for, flash, current_app
from flask_login import login_required, current_user

from core.audit_policy import audit_event
from models import Funcionario, db

from services.normalizacao_service import normalizar_maiusculo, normalizar_cpf
from services.indexacao_service import reindexar_funcionario
from services.auditoria_services import registrar_evento_seguro, gerar_diff_antes_depois

funcionarios_bp = Blueprint('funcionarios', __name__)


@funcionarios_bp.route('/funcionario/inativar/<int:id>', methods = ['POST'])
@login_required
@audit_event()
def inativar_funcionario(id):
    if not current_user.is_admin:
        registrar_evento_seguro(
            'FUNCIONARIO_INATIVAR_NEGADO',
            categoria='seguranca',
            status='falha',
            recurso='funcionario',
            recurso_id=str(id),
        )
        flash('Acesso negado: Você não tem privilégios administrtativos.', 'error')
        return redirect(url_for('painel'))

    func = Funcionario.query.get_or_404(id)
    valores_antes= {
        'ativo': func.ativo,
        'situacao': func.situacao,
    }
    func.ativo = False
    if normalizar_maiusculo(func.situacao or '') == 'ATIVO':
        func.situacao = 'Inativo'
    db.session.commit()

    ix = current_app.config['WHOOSH_IX']
    writer =ix.writer()
    writer.delete_by_term('cpf', normalizar_cpf(func.cpf))
    writer.commit()

    valores_depois = {
        'ativo': func.ativo,
        'situacao': func.situacao,
    }
    alteracoes = gerar_diff_antes_depois(valores_antes, valores_depois)

    registrar_evento_seguro(
        'FUNCIONARIO_INATIVAR_SUCESSO',
        categoria='cadastro',
        status='sucesso',
        recurso='funcionario',
        recurso_id=str(func.id),
        detalhes={
            'funcionario_nome': func.nome_completo,
            'funcionario_vinculo': func.vinculo,
            'situacao': func.situacao,
            'alteracoes': alteracoes,
        },
    )
    flash('Funcionário Inativado','success')
    return redirect(url_for('painel'))

@funcionarios_bp.route('/funcionario/reativar/<int:id>', methods=['POST'])
@login_required
@audit_event()
def reativar_funcionario(id):
    if not current_user.is_admin:
        registrar_evento_seguro(
            'FUNCIONARIO_REATIVAR_NEGADO',
            categoria='seguranca',
            status='falha',
            recurso='funcionario',
            recurso_id=str(id),
        )
        flash('Acesso negado: você não tem privilégios administrativos', 'error')
        return redirect(url_for('painel'))

    func = Funcionario.query.get_or_404(id)

    valores_antes = {
        'ativo': func.ativo,
        'situacao': func.situacao,
        'data_desligamento': func.data_desligamento,
    }

    func.ativo = True
    if not func.situacao or 'ATIVO' not in normalizar_maiusculo(func.situacao):
        func.situacao = 'Ativo'
    func.data_desligamento = None
    db.session.commit()

    ix = current_app.config['WHOOSH_IX']
    reindexar_funcionario(ix, func)

    valores_depois = {
        'ativo': func.ativo,
        'situacao': func.situacao,
        'data_desligamento': func.data_desligamento,
    }
    alteracoes = gerar_diff_antes_depois(valores_antes, valores_depois)

    registrar_evento_seguro(
        'FUNCIONARIO_REATIVAR_SUCESSO',
        categoria='cadastro',
        status='sucesso',
        recurso='funcionario',
        recurso_id=str(func.id),
        detalhes={
            'funcionario_nome': func.nome_completo,
            'funcionario_vinculo': func.vinculo,
            'situacao': func.situacao,
            'alteracoes': alteracoes,
        },
    )
    flash('Funcionário reativado', 'success')
    return redirect(url_for('painel'))
