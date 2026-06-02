from urllib.parse import urlparse, urljoin

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user

from core.audit_policy import audit_event
from models import Usuario
from services.auditoria_services import registrar_evento_seguro
from services.alertas_seguranca import ip_origem_requisicao, verificar_ip_bloqueado_login

auth_bp = Blueprint('auth', __name__)


def is_url_safe(target):
    if not target:
        return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc


@auth_bp.route('/login', methods=['GET', 'POST'])
@audit_event()
def login():
    if request.method == 'POST':
        login_value = request.form.get('login') or ''
        password = request.form.get('password', '')
        ip_origem = ip_origem_requisicao()

        bloqueado, _ = verificar_ip_bloqueado_login(ip_origem)
        if bloqueado:
            registrar_evento_seguro(
                'AUTH_LOGIN_BLOQUEADO_IP',
                categoria='seguranca',
                status='falha',
                recurso='autenticacao',
                recurso_id=ip_origem or None,
                detalhes={
                    'login_informado': login_value,
                    'ip_alvo': ip_origem,
                },
                processar_alertas=False,
            )
            flash(
                f'Este IP está bloqueado por segurança. Contate o administrador do sistema para liberação.',
                'error',
            )
            return render_template('login.html'), 429

        user = Usuario.query.filter_by(login=login_value).first()
        if user and user.check_password(password):
            login_user(user)
            registrar_evento_seguro(
                'AUTH_LOGIN_SUCESSO',
                categoria='seguranca',
                status='sucesso',
                recurso='usuario',
                recurso_id=str(user.id),
                detalhes={'login_informado': login_value},
            )
            next_page = request.args.get('next')
            if next_page and is_url_safe(next_page):
                return redirect(next_page)
            return redirect(url_for('busca.index'))

        registrar_evento_seguro(
            'AUTH_LOGIN_FALHA',
            categoria='seguranca',
            status='falha',
            recurso='usuario',
            detalhes={'login_informado': login_value},
        )
        flash('Usuário ou senha Inválidos.', 'error')
    return render_template('login.html')


@auth_bp.route('/logout', methods=['POST'])
@login_required
@audit_event()
def logout():
    registrar_evento_seguro(
        'AUTH_LOGOUT',
        categoria='seguranca',
        status='sucesso',
        recurso='usuario',
        recurso_id=str(current_user.id),
    )
    logout_user()
    return redirect(url_for('busca.index'))
