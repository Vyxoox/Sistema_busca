from flask import Blueprint
from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user

from core import db
from core.audit_policy import audit_event
from models import Funcionario
from routes.verfunc import preencher_campos_comuns, validar_campos_condicionais
from services.foto_service import salvar_foto
from services.indexacao_service import reindexar_funcionario
from services.auditoria_services import registrar_evento_seguro
from services.normalizacao_service import normalizar_maiusculo
from routes.editfunc import  (
    OPCOES_TIPO,
    OPCOES_SITUACAO,
    OPCOES_AREA,
    OPCOES_FORMA_INGRESSO,
    OPCOES_LOTACAO,
    OPCOES_COORDENADORIA,
    OPCOES_SUBTIPO_VINCULO,
)
criacao_bp = Blueprint('criacao', __name__)

SET_SUBTIPO = {normalizar_maiusculo(v) for v in OPCOES_SUBTIPO_VINCULO}
SET_LOTACAO = {normalizar_maiusculo(v) for v in OPCOES_LOTACAO}
SET_AREA = {normalizar_maiusculo(v) for v in OPCOES_AREA}
SET_COORDENADORIA = {normalizar_maiusculo(v) for v in OPCOES_COORDENADORIA}
SET_TIPO = {normalizar_maiusculo(v) for v in OPCOES_TIPO}
SET_FORMA_INGRESSO = {normalizar_maiusculo(v) for v in OPCOES_FORMA_INGRESSO}
SET_SITUACAO = {normalizar_maiusculo(v) for v in OPCOES_SITUACAO}

def _valor_em_lista(valor: str | None, opcoes_norm: set[str], *, obrigatorio: bool = False) -> bool:
    txt = normalizar_maiusculo(valor)
    if not txt:
        return not obrigatorio
    return txt in opcoes_norm

def _validar_selects_cadastro(form):
    regras = [
        ('subtipo_vinculo', SET_SUBTIPO, 'Subtipo de Vinculo'),
        ('lotacao', SET_LOTACAO, 'Lotacao'),
        ('area', SET_AREA, 'Area'),
        ('coordenadoria', SET_COORDENADORIA, 'Coordenadoria'),
        ('tipo', SET_TIPO, 'Tipo de contrato'),
        ('forma_ingresso', SET_FORMA_INGRESSO, 'Forma de ingresso'),
        ('situacao', SET_SITUACAO, 'Situacao')
    ]
    for campo, opcoes, rotulo in regras:
        if not _valor_em_lista(form.get(campo), opcoes, obrigatorio=True):
            return campo, f'{rotulo} inválido.'
    return None, None

@criacao_bp.route('/funcionario/novo/servidor', methods=['GET', 'POST'])
@login_required
@audit_event()
def novo_servidor():
    if not current_user.is_admin:
        registrar_evento_seguro(
            'FUNCIONARIO_CADASTRAR_SERVIDOR_NEGADO',
            categoria='seguranca',
            status='falha',
            recurso='funcionario',
        )
        flash('Acesso negado: você não tem privilégios administrativos.', 'error')
        return redirect(url_for('painel'))

    if request.method == 'POST':
        func = Funcionario(vinculo='SERVIDOR')
        preencher_campos_comuns(func, request.form)

        campo_invalido, erro_select = _validar_selects_cadastro(request.form)
        if erro_select:
            registrar_evento_seguro(
                'FUNCIONARIO_CADASTRAR_SERVIDOR_FALHA',
                categoria='cadastro',
                status='falha',
                recurso='funcionario',
                detalhes={
                    'motivo': 'validacao_allowlist_cadastro',
                    'campo': campo_invalido,
                    'valor': request.form.get(campo_invalido),
                    'funcionario_vinculo': 'SERVIDOR',
                },
            )
            flash(erro_select, 'error')
            return redirect(request.url)

        func.vinculo = 'SERVIDOR'

        erro = validar_campos_condicionais(func, 'SERVIDOR')
        if erro:
            registrar_evento_seguro(
                'FUNCIONARIO_CADASTRAR_SERVIDOR_FALHA',
                categoria='cadastro',
                status='falha',
                recurso='funcionario',
                detalhes={
                    'motivo': 'validacao_campos_condicionais',
                    'funcionario_vinculo': 'SERVIDOR',
                    'nome_informado': request.form.get('nome_completo'),
                    'cpf_informado': request.form.get('cpf'),
                },
            )
            flash(erro, 'error')
            return redirect(request.url)

        try:
            db.session.add(func)
            db.session.flush()
            foto = request.files.get('foto')
            salvar_foto(current_app.root_path, foto, func.id)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            # IntegrityError – duplicata de matrícula, CPF, etc.
            if 'IntegrityError' in type(e).__name__ or (hasattr(e, 'orig') and 'IntegrityError' in type(e.orig).__name__):
                msg_erro = str(e.orig) if hasattr(e, 'orig') else str(e)
                if 'matricula' in msg_erro.lower():
                    flash('Já existe um funcionário com esta matrícula.', 'error')
                elif 'cpf' in msg_erro.lower():
                    flash('Já existe um funcionário com este CPF.', 'error')
                else:
                    flash('Erro: registro duplicado. Verifique os dados e tente novamente.', 'error')
                current_app.logger.warning('IntegrityError ao cadastrar servidor: %s', e)
                return redirect(request.url)
            current_app.logger.exception('Erro inesperado ao cadastrar servidor')
            flash('Erro inesperado ao salvar. Tente novamente.', 'error')
            return redirect(request.url)

        registrar_evento_seguro(
            'FUNCIONARIO_CADASTRAR_SERVIDOR_SUCESSO',
            categoria='cadastro',
            status='sucesso',
            recurso='funcionario',
            recurso_id=str(func.id),
            detalhes={
                'funcionario_nome': func.nome_completo,
                'funcionario_vinculo': func.vinculo,
                'cpf': func.cpf,
                'matricula': func.matricula,
                'coordenadoria': func.coordenadoria,
                'tem_foto': bool(foto and getattr(foto, 'filename', '')),
            },
        )
        
        try:
            ix = current_app.config['WHOOSH_IX']
            reindexar_funcionario(ix, func)

        except Exception as e:
            registrar_evento_seguro(
                'WHOOSH_REINDEXAR_FALHA',
                categoria='observabilidade',
                status='falha',
                recurso='indice_busca',
                recurso_id=str(func.id),
                detalhes={
                    'erro': str(e),
                    'funcionario_nome': func.nome_completo
                }
            )
            current_app.logger.exception(
                'Falha ao reindexar funcionário'
            )
        flash(
            'Servidor cadastrado com sucesso!',
            'success'
        )
        return redirect(url_for('painel'))
    return render_template(
        'form_servidor.html',
        opcoes_tipo=OPCOES_TIPO,
        opcoes_situacao=OPCOES_SITUACAO,
        opcoes_area=OPCOES_AREA,
        opcoes_forma_ingresso=OPCOES_FORMA_INGRESSO,
        opcoes_lotacao=OPCOES_LOTACAO,
        opcoes_coordenadoria=OPCOES_COORDENADORIA,
        opcoes_subtipo_vinculo=OPCOES_SUBTIPO_VINCULO,
    )
@criacao_bp.route('/funcionario/novo/terceirizado', methods=['GET', 'POST'])
@login_required
@audit_event()
def novo_terceirizado():
    if not current_user.is_admin:
        registrar_evento_seguro(
            'FUNCIONARIO_CADASTRAR_TERCEIRIZADO_NEGADO',
            categoria='seguranca',
            status='falha',
            recurso='funcionario',
        )
        flash('Acesso negado: você não tem privilégios administrativos.', 'error')
        return redirect(url_for('painel'))

    if request.method == 'POST':
        func = Funcionario(vinculo='TERCEIRIZADO')
        preencher_campos_comuns(func, request.form)

        campo_invalido, erro_select = _validar_selects_cadastro(request.form)
        if erro_select:
            registrar_evento_seguro(
                'FUNCIONARIO_CADASTRAR_TERCEIRIZADO_FALHA',
                categoria='cadastro',
                status='falha',
                recurso='funcionario',
                detalhes={
                    'motivo': 'validacao_allowlist_cadastro',
                    'campo': campo_invalido,
                    'valor': request.form.get(campo_invalido),
                    'funcionario_vinculo': 'TERCEIRIZADO',
                },
            )
            flash(erro_select, 'error')
            return redirect(request.url)

        func.vinculo = 'TERCEIRIZADO'

        erro = validar_campos_condicionais(func, 'TERCEIRIZADO')
        if erro:
            registrar_evento_seguro(
                'FUNCIONARIO_CADASTRAR_TERCEIRIZADO_FALHA',
                categoria='cadastro',
                status='falha',
                recurso='funcionario',
                detalhes={
                    'motivo': 'validacao_campos_condicionais',
                    'funcionario_vinculo': 'TERCEIRIZADO',
                    'nome_informado': request.form.get('nome_completo'),
                    'cpf_informado': request.form.get('cpf'),
                },
            )
            flash(erro, 'error')
            return redirect(request.url)

        try:
            db.session.add(func)
            db.session.flush()
            foto = request.files.get('foto')
            salvar_foto(current_app.root_path, foto, func.id)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            if 'IntegrityError' in type(e).__name__ or (hasattr(e, 'orig') and 'IntegrityError' in type(e.orig).__name__):
                msg_erro = str(e.orig) if hasattr(e, 'orig') else str(e)
                if 'matricula' in msg_erro.lower():
                    flash('Já existe um funcionário com esta matrícula.', 'error')
                elif 'cpf' in msg_erro.lower():
                    flash('Já existe um funcionário com este CPF.', 'error')
                else:
                    flash('Erro: registro duplicado. Verifique os dados e tente novamente.', 'error')
                current_app.logger.warning('IntegrityError ao cadastrar terceirizado: %s', e)
                return redirect(request.url)
            current_app.logger.exception('Erro inesperado ao cadastrar terceirizado')
            flash('Erro inesperado ao salvar. Tente novamente.', 'error')
            return redirect(request.url)

        registrar_evento_seguro(
            'FUNCIONARIO_CADASTRAR_TERCEIRIZADO_SUCESSO',
            categoria='cadastro',
            status='sucesso',
            recurso='funcionario',
            recurso_id=str(func.id),
            detalhes={
                'funcionario_nome': func.nome_completo,
                'funcionario_vinculo': func.vinculo,
                'cpf': func.cpf,
                'empresa_contratada': func.empresa_contratada,
                'numero_contrato': func.numero_contrato,
                'coordenadoria': func.coordenadoria,
                'tem_foto': bool(foto and getattr(foto, 'filename', '')),
            },
        )

        try:
            ix = current_app.config['WHOOSH_IX']
            reindexar_funcionario(ix, func)

        except Exception as e:
            registrar_evento_seguro(
                'WHOOSH_REINDEXAR_FALHA',
                categoria='observabilidade',
                status='falha',
                recurso='indice_busca',
                recurso_id=str(func.id),
                detalhes={
                    'erro': str(e),
                    'funcionario_nome': func.nome_completo
                }
            )
            current_app.logger.exception(
                'Falha ao reindexar funcionário'
            )
        flash(
            'Terceirizado cadastrado com sucesso!',
            'success'
        )
        return redirect(url_for('painel'))


    return render_template(
        'form_terceirizado.html'
        ,opcoes_tipo=OPCOES_TIPO
        ,opcoes_situacao=OPCOES_SITUACAO
        ,opcoes_area=OPCOES_AREA
        ,opcoes_forma_ingresso=OPCOES_FORMA_INGRESSO
        ,opcoes_lotacao=OPCOES_LOTACAO
        ,opcoes_coordenadoria=OPCOES_COORDENADORIA
        ,opcoes_subtipo_vinculo=OPCOES_SUBTIPO_VINCULO
    )


@criacao_bp.route('/funcionario/novo', methods=['GET', 'POST'])
@login_required
@audit_event()
def novo_funcionario():
    return redirect(url_for('painel'))


@criacao_bp.route('/preview/form-errors')
@login_required
@audit_event()
def preview_form_errors():
    errors = {
        'nome_completo': 'Informe o nome completo.',
        'cpf': 'CPF invalido.',
        'email_institucional': 'Informe um e-mail institucional valido.',
        'tipo': 'Selecione o tipo.',
        'situacao': 'Selecione a situacao.',
        'ramal': 'Informe apenas os 4 ultimos digitos do ramal.',
    }
    form_data = {
        'nome_completo': '',
        'cpf': '123.456.789-00',
        'email_institucional': '',
        'tipo': '',
        'situacao': '',
        'ramal': '12',
    }
    return render_template(
        'preview_form_errors.html',
        errors=errors,
        form_data=form_data,
        opcoes_tipo=OPCOES_TIPO,
        opcoes_situacao=OPCOES_SITUACAO,
    )
