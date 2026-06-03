import json
import re

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError

from core import db
from core.audit_policy import audit_event
from core.authz import superadmin_required
from models import Usuario
from services.auditoria_services import registrar_evento_seguro, gerar_diff_antes_depois
from services.email_services import enviar_email
from repositories.usuario_repository import UsuarioRepository

usuario_bp = Blueprint('usuarios', __name__)
PERFIS_ADMIN_VALIDOS = {"CA.9", "SA.9", "CGR.9", "CO.9", "CT.9"}
PERMISSOES_ADMIN_VALIDAS ={"usuarios_gerenciar", "funcionarios_gerenciar", "ouvidoria_logs", "reindexar",}

def validar_senha(password: str) ->tuple[bool, str]:
    if len(password) < 8:
        return False, 'A senha deve ter pelo menos 8 caracteres.'
    if not re.search(r'[A-Z]', password):
        return False, 'A senha deve conter ao menos uma letra maiúscula.'
    if not re.search(r'[a-z]', password):
        return False, 'A senha deve conter ao menos uma letra minúscula.'
    if not re.search(r'[0-9]', password):
        return False, 'A senha dev conter ao menos um número.'
    if not re.search(r'[@$!%*?&#§=\-_+§\(\)\[\]\{\}]', password):
        return False, 'A senha deve conter ao menos um caractere especial. (Ex:@#$%&*)'
    return True, ''

def _parse_permissoes(raw: str | None) -> list[str]:
    if not raw:
        return []
    txt = str(raw).strip()
    if not txt:
        return []
    try:
        val = json.loads(txt)
        if isinstance(val, list):
            return [str(x).strip() for x in val if str(x).strip()]
    except Exception:
        pass
    return [p.strip() for p in txt.split(',') if p.strip()]

def _dump_permissoes(permissoes: list[str]) -> str | None:
    base = sorted({p for p in permissoes if p})
    if not base:
        return None
    return json.dumps(base, ensure_ascii=False)

@usuario_bp.route('/usuarios')
@login_required
@superadmin_required
@audit_event()
def listar_admin():
    usuarios = UsuarioRepository.listar_todos_admins()
    registrar_evento_seguro(
        'USUARIOS_LISTAR',
        categoria='administracao',
        recurso='usuario',
        detalhes={'total_usuarios': len(usuarios)},
    )
    return render_template('lista_admin.html', usuarios=usuarios)

@usuario_bp.route('/usuarios/novo', methods=['GET', 'POST'])
@login_required
@superadmin_required
def criar_admin():
    errors = {}
    form_data = {}

    if request.method == 'POST':
        login = (request.form.get('login') or '').strip()
        lotacao = (request.form.get('lotacao') or '').strip().upper()
        password = request.form.get('password') or ''
        confirm_password = request.form.get('confirm_password') or ''

        form_data = {'login': login, 'lotacao': lotacao}

        def registrar_falha_validacao(motivo: str) -> None:
            registrar_evento_seguro(
                'USUARIO_CRIAR_ADMIN_FALHA',
                categoria='administracao',
                status='falha',
                recurso='usuario',
                detalhes={
                    'motivo': motivo,
                    'login_informado': login or None,
                    'perfil_informado': lotacao or None,
                },
            )
        login = (request.form.get('login') or '').strip()
        password = request.form.get('password') or ''
        confirm_password = request.form.get('confirm_password') or ''
        lotacao = (request.form.get('lotacao') or '').strip().upper()

        if not login:
            errors['login'] = 'O nome de usuário é obrigatório.'
        elif UsuarioRepository.buscar_por_login(login):
            errors['login'] = 'Este login já está em uso.'
            registrar_falha_validacao('login_duplicado')

        if not password:
            errors['password'] = 'A senha é obrigatória.'
        else:
            senha_valida, msg_erro = validar_senha(password)
            if not senha_valida:
                errors['password'] = msg_erro

        if password != confirm_password:
            errors['confirm_password'] = 'As senhas não coincidem.'

        if not lotacao:
            errors['lotacao'] = 'Selecione a lotação de acesso.'
        elif lotacao not in PERFIS_ADMIN_VALIDOS:
            errors['lotacao'] = 'Lotação de acesso inválida.'

            # Se houver erros, volta para o form com os dados
        if errors:
            if not errors.get('login') == 'Este login já está em uso.':  # Evita log duplicado
                registrar_falha_validacao('validacao_campos')
            return render_template('criar_usuario.html', errors=errors, form_data=form_data)

            # Se passou por tudo, cria o usuário
        usuario = Usuario(
            login=login,
            perfil=lotacao,
            is_admin=True,
            is_superadmin=False
        )
        usuario.set_password(password)
        UsuarioRepository.salvar(usuario)

        try:
            flash('Administrador criado com sucesso!', 'success')
            return redirect(url_for('usuarios.listar_admin'))
        except IntegrityError:
            db.session.rollback()
            flash('Erro interno ao salvar', 'error')
            return render_template('criar_usuario.html',form_data=form_data)

    return render_template('criar_usuario.html', form_data=form_data, errors=errors)


@usuario_bp.route('/usuarios/<int:usuario_id>/reset-senha', methods=['POST','GET'])
@login_required
@superadmin_required
def resetar_senha_admin(usuario_id: int):

    usuario_alvo = UsuarioRepository.buscar_por_id(usuario_id) or abort(404)

    def registrar_falha(motivo: str, *, erro: str | None = None) -> None:
        detalhes = {
            'motivo': motivo,
            'usuario_alvo': usuario_alvo.login,
        }
        if erro:
            detalhes['erro'] = erro
        registrar_evento_seguro(
            'USUARIO_RESET_SENHA_FALHA',
            categoria='administracao',
            status='falha',
            recurso='usuario',
            recurso_id=str(usuario_alvo.id),
            detalhes=detalhes,
        )

    if request.method == 'POST':
        password = request.form.get('password') or ''
        confirm_password = request.form.get('confirm_password') or ''

        if not password:
            registrar_falha('senha_nao_informada')
            flash('Informe a nova senha.', 'error')
            return redirect(request.url)

        senha_valida, msg_erro = validar_senha(password)
        if not senha_valida:
            registrar_falha('Senha fraca')
            flash(msg_erro, 'error')
            return redirect(request.url)

        if password != confirm_password:
            registrar_falha('senha_confirmacao_diferente')
            flash('As senhas não coincidem tente novamente.', 'error')
            return redirect(request.url)

        try:
            usuario_alvo.set_password(password)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            registrar_falha('erro_salvar', erro=str(e))
            flash(f'Não foi possível alterar a senha.', 'error')
            return redirect(request.url)

        registrar_evento_seguro(
            'USUARIO_RESET_SENHA_SUCESSO',
            categoria='administracao',
            status='sucesso',
            recurso='usuario',
            recurso_id=str(usuario_alvo.id),
            detalhes={'usuario_alvo': usuario_alvo.login},
        )
        flash('Senha alterada com sucesso!', 'success')
        return redirect(url_for('usuarios.listar_admin'))
    return render_template('reset_senha_admin.html', usuario_alvo=usuario_alvo)

@usuario_bp.route('/usuarios/<int:usuario_id>/editar-acesso', methods=['GET', 'POST'])
@login_required
@superadmin_required
def editar_acesso_admin(usuario_id: int):
    usuario_alvo = UsuarioRepository.buscar_por_id(usuario_id) or abort(404)
    permissoes_atuais = _parse_permissoes(usuario_alvo.permissoes)

    # Impedir que um superadmin rebaixe a si mesmo ou mude seu próprio perfil acidentalmente
    # (Embora superadmin_required já proteja, o próprio superadmin logado não deve se auto-editar aqui)
    if usuario_alvo.id == current_user.id:
        flash('Você não pode editar o seu próprio perfil de acesso nesta tela.', 'warning')
        return redirect(url_for('usuarios.listar_admin'))

    if request.method == 'POST':
        perfil_novo = (request.form.get('perfil') or '').strip().upper()
        permissoes_novas = request.form.getlist('permissoes')
        permissoes_novas = sorted({p.strip() for p in permissoes_novas if p.strip()})

        if not perfil_novo:
            registrar_evento_seguro(
                'USUARIO_EDITAR_ACESSO_FALHA',
                categoria='administracao',
                status='falha',
                recurso='usuario',
                recurso_id=str(usuario_alvo.id),
                detalhes={'motivo': 'perfil_nao_informado', 'usuario_alvo': usuario_alvo.login},
            )
            flash('Selecione o perfil de acesso.', 'error')
            return redirect(request.url)

        # Proteção: Se o alvo é superadmin, garantir que ele não seja "rebaixado" para admin normal
        # se ele for o único superadmin do sistema.
        if usuario_alvo.is_superadmin and perfil_novo not in {'SA.9', 'CA.9'}:
             # Nota: No sistema atual, is_superadmin é uma flag separada,
             # mas o perfil define o nível de acesso real em muitos lugares.
             # Se for rebaixar o perfil, precisamos garantir que ainda existam outros superadmins.
             outros_super = UsuarioRepository.contar_outros_superadmins(usuario_alvo.id)
             if outros_super == 0:
                 flash('Não é possível alterar o perfil do único Superadmin do sistema.', 'error')
                 return redirect(request.url)

        if perfil_novo not in PERFIS_ADMIN_VALIDOS:
            registrar_evento_seguro(
                'USUARIO_EDITAR_ACESSO_FALHA',
                categoria='administracao',
                status='falha',
                recurso = 'usuario',
                recurso_id=str(usuario_alvo.id),
                detalhes={'motivo': 'perfil_invalido', 'usuario_alvo': usuario_alvo.login, 'perfil_informado': perfil_novo},
            )
            flash('Perfil de acesso inválido.', 'error')
            return redirect(request.url)

        invalidas = [p for p in permissoes_novas if p not in PERMISSOES_ADMIN_VALIDAS]
        if invalidas:
            registrar_evento_seguro(
                'USUARIO_EDITAR_ACESSO_FALHA',
                categoria='administracao',
                status='falha',
                recurso = 'usuario',
                recurso_id=str(usuario_alvo.id),
                detalhes={'motivo': 'permissoes_invalidas', 'usuario_alvo': usuario_alvo.login, 'permissoes_informadas': invalidas},
            )
            flash('Foram informadas permissoes invalidas.', 'error')
            return redirect(request.url)

        antes = {
            'perfil': usuario_alvo.perfil,
            'permissoes': permissoes_atuais,
        }

        usuario_alvo.perfil = perfil_novo
        usuario_alvo.permissoes = _dump_permissoes(permissoes_novas)


        depois = {
            'perfil': usuario_alvo.perfil,
            'permissoes': permissoes_novas,
        }
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            registrar_evento_seguro(
                'USUARIO_EDITAR_ACESSO_FALHA',
                categoria='administracao',
                status='falha',
                recurso = 'usuario',
                recurso_id=str(usuario_alvo.id),
                detalhes={'motivo': 'erro_salvar', 'usuario_alvo': usuario_alvo.login, 'erro': str(e)},
            )
            flash('Nao foi possivel salvar as alteracoes de acesso.', 'error')
            return redirect(request.url)

        alteracoes = gerar_diff_antes_depois(antes, depois, ('perfil', 'permissoes'))
        registrar_evento_seguro(
            'USUARIO_EDITAR_ACESSO_SUCESSO',
            categoria='administracao',
            status='sucesso',
            recurso = 'usuario',
            recurso_id=str(usuario_alvo.id),
            detalhes={'usuario_alvo': usuario_alvo.login,
                      'alteracoes': alteracoes,
                      'total_alteracoes': len(alteracoes),
            },
        )
        flash('Acesso alterado com sucesso!', 'success')
        return redirect(url_for('usuarios.listar_admin'))

    return render_template(
        'editar_acesso_admin.html',
        usuario_alvo=usuario_alvo,
        perfis_validos=PERFIS_ADMIN_VALIDOS,
        permissoes_validas=sorted(PERMISSOES_ADMIN_VALIDAS),
        permissoes_atuais=permissoes_atuais,
    )

@usuario_bp.route('/usuarios/<int:usuario_id>/excluir', methods=['POST'])
@login_required
@superadmin_required
@audit_event()
def excluir_admin(usuario_id: int):
    usuario_alvo = UsuarioRepository.buscar_por_id(usuario_id) or abort(404)

    # Impedir que o superadmin se exclua
    if usuario_alvo.id == current_user.id:
        flash('Você não pode excluir a sua própria conta.', 'warning')
        return redirect(url_for('usuarios.listar_admin'))

    # Se o alvo for um superadmin, garantir que existam outros
    if usuario_alvo.is_superadmin:
        outros_super = UsuarioRepository.contar_outros_superadmins(usuario_alvo.id)
        if outros_super == 0:
            flash('Não é possível excluir o único Superadmin do sistema.', 'error')
            return redirect(url_for('usuarios.listar_admin'))

    login_alvo = usuario_alvo.login
    try:
        UsuarioRepository.excluir(usuario_alvo)

        registrar_evento_seguro(
            'USUARIO_EXCLUIR_SUCESSO',
            categoria='administracao',
            status='sucesso',
            recurso='usuario',
            recurso_id=str(usuario_id),
            detalhes={'usuario_alvo': login_alvo},
        )
        flash(f'Administrador {login_alvo} excluído com sucesso.', 'success')
    except Exception as e:
        db.session.rollback()
        registrar_evento_seguro(
            'USUARIO_EXCLUIR_FALHA',
            categoria='administracao',
            status='falha',
            recurso='usuario',
            recurso_id=str(usuario_id),
            detalhes={'usuario_alvo': login_alvo, 'erro': str(e)},
        )
        flash('Não foi possível excluir o administrador devido a um erro no servidor.', 'error')

    return redirect(url_for('usuarios.listar_admin'))

@usuario_bp.route(
    "/usuarios/teste-email",
    methods=["GET", "POST"]
)
@login_required
@superadmin_required
@audit_event()
def teste_email():

    if request.method == "POST":

        destinatario = (
            request.form.get("destinatario") or ""
        ).strip()

        if not destinatario:

            flash(
                "Informe um e-mail válido.",
                "error"
            )

            return render_template(
                "teste_email.html"
            )

        sucesso = enviar_email(
            destinatario,
            "Teste SMTP",
            "Este é um teste do Sistema de Busca."
        )

        if sucesso:

            registrar_evento_seguro(
                "EMAIL_TESTE_SUCESSO",
                categoria="seguranca",
                status="sucesso",
                recurso="smtp",
                detalhes={
                    "destinatario": destinatario
                }
            )

            flash(
                "E-mail enviado com sucesso.",
                "success"
            )

        else:

            registrar_evento_seguro(
                "EMAIL_TESTE_FALHA",
                categoria="seguranca",
                status="falha",
                recurso="smtp",
                detalhes={
                    "destinatario": destinatario
                }
            )

            flash(
                "Falha ao enviar e-mail.",
                "error"
            )

    return render_template(
        "teste_email.html"
    )
