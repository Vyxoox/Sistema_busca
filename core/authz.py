from functools import wraps
from flask import flash, redirect, url_for
from flask_login import current_user
from services.auditoria_services import registrar_evento_seguro

def superadmin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            registrar_evento_seguro(
                'AUTH_SUPERADMIN_NAO_AUTENTICADO',
                categoria='seguranca',
                status='falha',
                recurso='autorizacao',
                detalhes={'decorator': 'superadmin_required'},
            )
            return redirect(url_for('auth.login'))

        if not getattr(current_user, 'is_superadmin', False):
            registrar_evento_seguro(
                'AUTH_SUPERADMIN_NEGADO',
                categoria='seguranca',
                status='falha',
                recurso='autorizacao',
                detalhes={'decorator': 'superadmin_required'},
            )
            flash('Acesso restrito ao administrador mestre.', 'error')
            return redirect(url_for('painel'))

        return fn(*args, **kwargs)

    return wrapper
