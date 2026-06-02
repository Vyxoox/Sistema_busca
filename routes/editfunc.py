from flask import Blueprint, flash, redirect, url_for, request, render_template, session, current_app
from flask_login import login_required, current_user

from core import db
from core.audit_policy import audit_event
from models import Funcionario
from routes.verfunc import preencher_campos_comuns, validar_campos_condicionais

from services.normalizacao_service import normalizar_maiusculo
from services.foto_service import salvar_foto, remover_foto
from services.indexacao_service import reindexar_funcionario
from services.auditoria_services import registrar_evento_seguro, gerar_diff_antes_depois

editfunc_bp = Blueprint('editfunc', __name__)

###################################################
##ROTAS#PRA#EDIÇÃO#DE#INFORMAÇÕES#DE#FUNCIONÁRIOS##
###################################################

OPCOES_SUBTIPO_VINCULO=[
    'ADMINISTRATIVO',
    'OPERACIONAL',
]

OPCOES_LOTACAO = [
    '38.842 - COORDENADORIA GERAL REGIONAL - CGR.9',
    '38.844 - COORDENADORIA ADMINISTRATIVA - CA.9',
    '38.886 - COORDENADORIA DE CONSERVAÇÃO E OPERAÇÕES VIÁRIAS - CO.9',
    '38.922 - COORDENADORIA TÉCNICA - CT.9',
    '38.846 - SERVIÇO DE ADMINISTRAÇÃO DE PESSOAL - SA.9',
    '38.867 - SERVIÇO DE AQUISIÇÕES E CONTRATAÇÕES -SQ.9',
    '38.851 - SERVIÇO DE FINANÇAS - SF.9',
    '38.869 - SERVIÇO DE PATRIMÔNIO, TECNOLOGIA E ATIVIDADES GERAIS - SG.9',
    '36.759 - SERVIÇO DE FAIXA DE DOMÍNIO, PEDÁGIOS, RADAR E BALANÇA - SR.9',
    '36.765 - SERVIÇO DE UNIDADE BÁSICA DE ATENDIMENTO - UBA - SB.9',
    '36.766 - SERVIÇO DE CONSERVAÇÃO DE ROTINA - SC.9',
    '36.767 - SERVIÇO DE CONSTRUÇÃO - ST.9',
    '36.768 - SERVIÇO DE PLANEJAMENTO E PROJETOS - SP.9',
]

OPCOES_AREA = [
    '38.842 - COORDENADORIA GERAL REGIONAL - CGR.9',
    '38.844 - COORDENADORIA ADMINISTRATIVA - CA.9',
    '38.886 - COORDENADORIA DE CONSERVAÇÃO E OPERAÇÕES VIÁRIAS - CO.9',
    '38.922 - COORDENADORIA TÉCNICA - CT.9',
    '38.846 - SERVIÇO DE ADMINISTRAÇÃO DE PESSOAL - SA.9',
    '38.867 - SERVIÇO DE AQUISIÇÕES E CONTRATAÇÕES -SQ.9',
    '38.851 - SERVIÇO DE FINANÇAS - SF.9',
    '38.869 - SERVIÇO DE PATRIMÔNIO, TECNOLOGIA E ATIVIDADES GERAIS - SG.9',
    '36.759 - SERVIÇO DE FAIXA DE DOMÍNIO, PEDÁGIOS, RADAR E BALANÇA - SR.9',
    '36.765 - SERVIÇO DE UNIDADE BÁSICA DE ATENDIMENTO - UBA - SB.9',
    '36.766 - SERVIÇO DE CONSERVAÇÃO DE ROTINA - SC.9',
    '36.767 - SERVIÇO DE CONSTRUÇÃO - ST.9',
    '36.768 - SERVIÇO DE PLANEJAMENTO E PROJETOS - SP.9',
    'SERVIÇO EXTERNO',
]

OPCOES_COORDENADORIA = [
    '38.842 - COORDENADORIA GERAL REGIONAL - CGR.9',
    '38.844 - COORDENADORIA ADMINISTRATIVA - CA.9',
    '38.886 - COORDENADORIA DE CONSERVAÇÃO E OPERAÇÕES VIÁRIAS - CO.9',
    '38.922 - COORDENADORIA TÉCNICA - CT.9',
]

OPCOES_TIPO = [
    'CELETISTA',
    'EFETIVO',
    'COMISSIONADO',
    'CELETISTA ESTÁVEL',
    'TERCEIRIZADO'
]

OPCOES_FORMA_INGRESSO = [
    'Livre Provimento',
    'Processo Seletivo',
    'Concurso Público',
    'Prestador de Serviço',
]

OPCOES_SITUACAO = [
    'Ativo',
    'Inativo - Exoneração',
    'Inativo - Demissão',
    'Inativo - Aposentadoria',
    'Inativo - Término de contrato',
    'Inativo - Outros',
]

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

@editfunc_bp.route('/funcionario/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@audit_event()
def editar_funcionario(id):
    if not current_user.is_admin:
        registrar_evento_seguro(
            'FUNCIONARIO_EDITAR_NEGADO',
            categoria='seguranca',
            status='falha',
            recurso='funcionario',
            recurso_id=str(id),
        )
        flash('Acesso negado: você não tem privilégios administrativos.', 'error')
        return redirect(url_for('painel'))

    func = Funcionario.query.get_or_404(id)

    if request.method == 'POST':
        current_app.logger.warning("INICIO POST")
        current_app.logger.warning(
            f"CONTENT_LENGTH={request.content_length}"
        )
        campos_auditoria = (
            'nome_completo', 'cpf', 'rg', 'vinculo', 'tipo', 'subtipo_vinculo',
            'forma_ingresso', 'matricula', 'cargo_exercicio', 'cargo_origem',
            'lotacao', 'area', 'coordenadoria', 'situacao', 'data_desligamento',
            'empresa_contratada', 'numero_contrato', 'gestor_contrato',
            'fiscal_tecnico', 'fiscal_administrativo', 'preposto',
        )
        valores_antes = {campo: getattr(func, campo, None) for campo in campos_auditoria}

        vinculo_norm = normalizar_maiusculo(request.form.get('vinculo'))
        func.vinculo = vinculo_norm

        prefixo = ''
        if vinculo_norm == 'SERVIDOR' and request.form.get('nome_completo_s'):
            prefixo = ''
        elif vinculo_norm == 'TERCEIRIZADO' and request.form.get('nome_completo_t'):
            prefixo = ''

        preencher_campos_comuns(func, request.form, prefixo=prefixo)

        if not _valor_em_lista(request.form.get('subtipo_vinculo'), SET_SUBTIPO, obrigatorio=True):
            flash('Subtipo de vinculo inválido.', 'error')
            return redirect(url_for('editfunc.editar_funcionario', id=id))

        if not _valor_em_lista(request.form.get('lotacao'), SET_LOTACAO, obrigatorio=True):
            flash('Lotação inválida.', 'error')
            return redirect(url_for('editfunc.editar_funcionario', id=id))

        if not _valor_em_lista(request.form.get('area'), SET_AREA, obrigatorio=True):
            flash('Área inválida.', 'error')
            return redirect(url_for('editfunc.editar_funcionario', id=id))

        if not _valor_em_lista(request.form.get('coordenadoria'), SET_COORDENADORIA, obrigatorio=True):
            flash('Coordenadoria inválida.', 'error')
            return redirect(url_for('editfunc.editar_funcionario', id=id))

        if not _valor_em_lista(request.form.get('tipo'), SET_TIPO, obrigatorio=True):
            flash('Tipo de contrato inválido.', 'error')
            return redirect(url_for('editfunc.editar_funcionario', id=id))

        if not _valor_em_lista(request.form.get('forma_ingresso'), SET_FORMA_INGRESSO, obrigatorio=True):
            flash('Forma de ingresso é inválida.', 'error')
            return redirect(url_for('editfunc.editar_funcionario', id=id))

        if not _valor_em_lista(request.form.get('situacao'), SET_SITUACAO, obrigatorio=True):
            flash('Situação do funcionário é inválida.', 'error')
            return redirect(url_for('editfunc.editar_funcionario', id=id))


        erro = validar_campos_condicionais(func, vinculo_norm)
        if erro:
            registrar_evento_seguro(
                'FUNCIONARIO_EDITAR_FALHA',
                categoria='cadastro',
                status='falha',
                recurso='funcionario',
                recurso_id=str(func.id),
                detalhes={'motivo': 'validacao_campos_condicionais', 'funcionario_vinculo': vinculo_norm},
            )
            flash(erro, 'error')
            return redirect(url_for('editfunc.editar_funcionario', id=id))

        try:

            foto = request.files.get('foto')

            db.session.commit()

            salvar_foto(
                current_app.root_path,
                foto,
                func.id
            )

            ix = current_app.config['WHOOSH_IX']
            reindexar_funcionario(ix, func)

            valores_depois = {campo: getattr(func, campo, None) for campo in campos_auditoria}
            alteracoes = gerar_diff_antes_depois(valores_antes, valores_depois, campos_auditoria)

            registrar_evento_seguro(
                'FUNCIONARIO_EDITAR_SUCESSO',
                categoria='cadastro',
                status='sucesso',
                recurso='funcionario',
                recurso_id=str(func.id),
                detalhes={
                    'funcionario_nome': func.nome_completo,
                    'funcionario_vinculo': func.vinculo,
                    'total_alteracoes': len(alteracoes),
                    'alteracoes': alteracoes,
                },
            )

            flash('Funcionário atualizado com sucesso!', 'success')
            return redirect(url_for('painel'))
        except Exception as e:
            db.session.rollback()

            registrar_evento_seguro(
                'FUNCIONARIO_EDITAR_FALHA',
                categoria='cadastro',
                status='falha',
                recurso='funcionario',
                recurso_id=str(func.id),
                detalhes={'motivo': 'erro_salvar', 'error': str(e)},
            )
            flash(f'Erro ao salvar no banco: {str(e)}', 'error')
            return redirect(url_for('editfunc.editar_funcionario', id=id))

    return render_template(
        'form_funcionario.html',
        func=func,
        opcoes_subtipo_vinculo=OPCOES_SUBTIPO_VINCULO,
        opcoes_lotacao=OPCOES_LOTACAO,
        opcoes_coordenadoria=OPCOES_COORDENADORIA,
        opcoes_area=OPCOES_AREA,
        opcoes_tipo=OPCOES_TIPO,
        opcoes_forma_ingresso=OPCOES_FORMA_INGRESSO,
        opcoes_situacao=OPCOES_SITUACAO,
    )

@editfunc_bp.route('/funcionario/remover-foto/<int:id>', methods=['POST'])
@login_required
@audit_event()
def remover_foto_funcionario(id):
    if not current_user.is_admin:
        registrar_evento_seguro(
            'FUNCIONARIO_REMOVER_FOTO_NEGADO',
            categoria='seguranca',
            status='falha',
            recurso='funcionario',
            recurso_id=str(id),
        )
        session.pop('_flashes', None)
        flash('Acesso negado: você não tem privilégios administrativos.', 'error')
        return redirect(url_for('painel'))

    func = Funcionario.query.get_or_404(id)

    try:
        removida = remover_foto(current_app.root_path, func.id)

        session.pop('_flashes', None)
        if removida:
            registrar_evento_seguro(
                'FUNCIONARIO_REMOVER_FOTO_SUCESSO',
                categoria='cadastro',
                status='sucesso',
                recurso='funcionario',
                recurso_id=str(func.id),
                detalhes={'foto_removida': True},
            )
            flash('Foto removida com sucesso!', 'success')
        else:
            registrar_evento_seguro(
                'FUNCIONARIO_REMOVER_FOTO_SEM_ARQUIVO',
                categoria='cadastro',
                status='falha',
                recurso='funcionario',
                recurso_id=str(func.id),
                detalhes={'foto_removida': False},
            )
            flash('Este funcionário não possui foto cadastrada.', 'error')

    except Exception as e:
        registrar_evento_seguro(
            'FUNCIONARIO_REMOVER_FOTO_FALHA',
            categoria='cadastro',
            status='falha',
            recurso='funcionario',
            recurso_id=str(func.id),
            detalhes={'motivo': 'erro_remocao', 'error': str(e)},
        )
        session.pop('_flashes', None)
        flash(f'Erro ao remover foto: {str(e)}', 'error')

    return redirect(url_for('editfunc.editar_funcionario', id=func.id))
