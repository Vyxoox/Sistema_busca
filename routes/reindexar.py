from flask import redirect, url_for, flash, Blueprint, current_app
from flask_login import login_required, current_user

from core.audit_policy import audit_event
from services.auditoria_services import registrar_evento_seguro
from services.indexacao_service import reindexar_todos
reindexar_bp = Blueprint('reindexar', __name__)

@reindexar_bp.route('/reindexar', methods=['POST'])
@login_required
@audit_event()
def reindexar():
    if not current_user.is_admin:
        registrar_evento_seguro(
            'REINDEXAR_NEGADO',
            categoria='seguranca',
            status='falha',
            recurso='funcionarios',
        )
        flash("Acesso negado.", "error")
        return redirect(url_for('painel'))

    try:
        ix = current_app.config['WHOOSH_IX']
        reindexar_todos(ix)
        registrar_evento_seguro(
            'REINDEXAR_TODOS_SUCESSO',
            categoria='indexacao',
            status='sucesso',
            recurso='funcionarios',
        )
        flash("Índice de busca atualizado com sucesso!", "success")
    except Exception as e:
        registrar_evento_seguro(
            'REINDEXAR_TODOS_FALHA',
            categoria='indexacao',
            status='falha',
            recurso='funcionarios',
            detalhes={'error': str(e)},
        )
        flash(f"Erro ao reindexar: {e}", "error")

    return redirect(url_for('painel'))
