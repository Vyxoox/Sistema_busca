from flask import Blueprint, request, redirect, url_for, session
from flask_login import login_required

from core.audit_policy import audit_event
from services.auditoria_services import registrar_evento_seguro

columns_bp = Blueprint('columns', __name__)


@columns_bp.route('/prefs/cols', methods=['POST'])
@login_required
@audit_event()
def set_cols_prefs():
    cols = request.form.getlist('cols')
    session['cols'] = cols
    q = (request.form.get('q') or '').strip()
    vinculo = (request.form.get('vinculo') or 'todos').strip() or 'todos'
    registrar_evento_seguro(
        'BUSCA_COLUNAS_ATUALIZADAS',
        categoria='configuracao',
        recurso='interface_busca',
        detalhes={
            'total_colunas': len(cols),
            'colunas': cols,
            'q': q[:120],
            'vinculo': vinculo,
        },
    )
    return redirect(url_for('busca.index', q=q, vinculo=vinculo))
