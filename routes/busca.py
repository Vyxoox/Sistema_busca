from flask import Blueprint, redirect, url_for, render_template, request, session, current_app

from core.audit_policy import audit_event
from services.busca_service import executar_busca
from flask_login import login_required
from services.auditoria_services import registrar_evento_seguro

busca_bp = Blueprint('busca', __name__)

@busca_bp.route('/')
@login_required
@audit_event()
def index():
    query = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    page = max(page, 1)
    per_page = 50

    colunas_args = request.args.getlist('cols')
    if colunas_args:
        session['cols'] = colunas_args
        return redirect(url_for('busca.index', q=query, vinculo=request.args.get('vinculo', 'todos')))

    colunas_selecionadas = session.get('cols', [])
    vinculo_selecionado = request.args.get('vinculo', 'todos')
    busca_realizada = 'q' in request.args or 'vinculo' in request.args

    ix = current_app.config['WHOOSH_IX']
    resultados = executar_busca(ix, query, vinculo_selecionado) if busca_realizada else []
    total_resultados = len(resultados)
    total_pages = max((total_resultados + per_page - 1) // per_page, 1)

    if page > total_pages:
        page = total_pages

    inicio = (page - 1) * per_page
    fim = inicio + per_page
    resultados_pagina = resultados[inicio:fim]

    if busca_realizada:
        registrar_evento_seguro(
            'BUSCA_REALIZADA',
            categoria='consulta',
            recurso='funcionarios',
            detalhes={
                'q': query[:120],
                'vinculo': vinculo_selecionado,
                'page': page,
                'total_resultados': total_resultados,
            },
        )

    return render_template(
        'busca.html',
        query=query,
        resultados=resultados_pagina,
        total_resultados=total_resultados,
        page=page,
        total_pages=total_pages,
        colunas_selecionadas=colunas_selecionadas,
        vinculo_selecionado=vinculo_selecionado,
        busca_realizada=busca_realizada
    )
