import os
import tempfile

import pandas as pd
from flask import Blueprint, request, redirect, url_for, session, send_file, current_app
from flask_login import login_required

from core.audit_policy import audit_event
from services.busca_service import executar_busca
from services.formatacao_service import formatar_cpf, formatar_rg
from services.exportacao_service import valor_exportacao_resultado, limpar_valor_excel

from services.auditoria_services import registrar_evento_seguro

planilha_bp = Blueprint('planilha', __name__)


def _prioridade_vinculo_planilha(resultado):
    vinculo = str(resultado.get('vinculo', '') or '').upper()
    if vinculo == 'SERVIDOR':
        return 0
    if vinculo == 'TERCEIRIZADO':
        return 1
    return 2


def _chave_ordenacao_planilha(resultado, separar_por_vinculo=False):
    chave_base = (
        str(resultado.get('nome_completo', '') or '').strip().casefold(),
        str(resultado.get('cpf', '') or '').strip(),
    )
    if separar_por_vinculo:
        return (_prioridade_vinculo_planilha(resultado),) + chave_base
    return chave_base


@planilha_bp.route('/export/xlsx')
@login_required
@audit_event()
def exportar_xlsx():
    query = request.args.get('q', '').strip()
    vinculo_selecionado = request.args.get('vinculo', 'todos')

    if 'q' not in request.args and 'vinculo' not in request.args:
        return redirect(url_for('busca.index'))

    ix = current_app.config['WHOOSH_IX']
    resultados = executar_busca(ix, query, vinculo_selecionado)
    separar_por_vinculo = not vinculo_selecionado or vinculo_selecionado.lower() == 'todos'
    resultados.sort(key=lambda r: _chave_ordenacao_planilha(r, separar_por_vinculo))

    campos = [
        ('matricula', 'MATRÍCULA'),
        ('cpf', 'CPF'),
        ('rg', 'RG'),
        ('cin', 'CIN'),
        ('titulo_eleitor', 'TÍTULO DE ELEITOR'),
        ('pis_pasep', 'PIS/PASEP'),
        ('data_nasc', 'DATA DE NASCIMENTO'),
        ('endereco_residencial', 'ENDEREÇO RESIDENCIAL'),
        ('telefone_pessoal', 'TELEFONE PESSOAL'),
        ('email_pessoal', 'EMAIL PESSOAL'),
        ('email_institucional', 'EMAIL INSTITUCIONAL'),
        ('ramal', 'RAMAL'),
        ('tipo', 'TIPO'),
        ('subtipo_vinculo', 'SUBTIPO VÍNCULO'),
        ('forma_ingresso', 'FORMA DE INGRESSO'),
        ('prontuario_funcional', 'PRONTUÁRIO FUNCIONAL'),
        ('cargo_exercicio', 'CARGO EM EXERCÍCIO'),
        ('cargo_origem', 'CARGO DE ORIGEM'),
        ('lotacao', 'LOTAÇÃO'),
        ('area', 'ÁREA'),
        ('coordenadoria', 'COORDENADORIA'),
        ('data_ingresso_der', 'INGRESSO NO DER'),
        ('data_inicio', 'DATA INÍCIO'),
        ('data_admissao', 'DATA ADMISSÃO'),
        ('situacao', 'SITUAÇÃO'),
        ('data_desligamento', 'DATA DESLIGAMENTO'),
        ('doe_portaria', 'DOE / PORTARIA'),
        ('empresa_contratada', 'EMPRESA CONTRATADA'),
        ('numero_contrato', 'NÚMERO DO CONTRATO'),
        ('gestor_contrato', 'GESTOR DO CONTRATO'),
        ('fiscal_tecnico', 'FISCAL TÉCNICO'),
        ('fiscal_administrativo', 'FISCAL ADMINISTRATIVO'),
        ('preposto', 'PREPOSTO')
    ]

    cols_selecionadas = session.get('cols', [])
    if not cols_selecionadas:
        cols_selecionadas = [c for c, _ in campos]

    ordem = [('nome_completo', 'NOME COMPLETO'), ('vinculo', 'VÍNCULO')]
    for key, label in campos:
        if key in cols_selecionadas:
            ordem.append((key, label))

    rows = []
    for r in resultados:
        row = {}
        for key, label in ordem:
            val = valor_exportacao_resultado(r, key)
            val = limpar_valor_excel(val)

            if key == 'cpf' and val not in ('', 'Não se aplica'):
                val = formatar_cpf(val)
            elif key == 'rg' and val not in ('', 'Não se aplica'):
                val = formatar_rg(val)
            elif hasattr(val, 'strftime'):
                val = val.strftime('%d/%m/%Y')

            val = limpar_valor_excel(val)
            row[label] = val

        rows.append(row)

    df = pd.DataFrame(rows, columns=[label for _, label in ordem])

    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
    temp_path = temp_file.name
    temp_file.close()

    with pd.ExcelWriter(temp_path, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Funcionarios', startrow=0)


        ws = writer.sheets['Funcionarios']
        workbook = writer.book

        #alturas
        ws.set_row(0,60)
        ws.set_row(1,28)
        ws.set_row(2,18)

        #################################
        #FORMATAÇÃO DO TITULO E SUBTÍTULO
        #################################

        ws.repeat_rows(1)

        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#2F5597',
            'color': 'white',
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'font_name': 'Calibri',
            'font_size': 10
        })

        cell_format = workbook.add_format({
            'border': 1,
            'text_wrap': True,
            'valign': 'vcenter',
            'font_name': 'Calibri',
            'font_size': 9
        })

        zebra_format = workbook.add_format({
            'bg_color': '#F5F7FA',
            'border': 1,
            'text_wrap': True,
            'valign': 'vcenter',
            'font_name': 'Calibri',
            'font_size': 9
        })

        center_format = workbook.add_format({
            'border': 1,
            'text_wrap': True,
            'valign': 'vcenter',
            'align': 'center',
            'font_name': 'Calibri',
            'font_size': 9
        })

        center_zebra_format = workbook.add_format({
            'bg_color': '#F5F7FA',
            'border': 1,
            'text_wrap': True,
            'valign': 'vcenter',
            'align': 'center',
            'font_name': 'Calibri',
            'font_size': 9
        })

        colunas_centralizadas = {
            'VÍNCULO', 'MATRÍCULA', 'CPF', 'RG', 'CIN', 'PIS/PASEP',
            'RAMAL', 'TIPO', 'SUBTIPO VÍNCULO', 'INGRESSO NO DER',
            'DATA INÍCIO', 'DATA ADMISSÃO', 'DATA DESLIGAMENTO'
        }

        for col_num, value in enumerate(df.columns):
            ws.write(0, col_num, value, header_format)

        for col_num, col_name in enumerate(df.columns):
            for row_num, val in enumerate(df[col_name].astype(str), start=1):
                fmt = (
                    center_zebra_format if row_num % 2 == 0 else center_format
                ) if col_name in colunas_centralizadas else (
                    zebra_format if row_num % 2 == 0 else cell_format
                )

                ws.write(row_num, col_num, val, fmt)
                ws.set_row(row_num, 22)

            if col_name == 'NOME COMPLETO':
                ws.set_column(col_num, col_num, 40)
            elif col_name in ['CPF', 'RG']:
                ws.set_column(col_num, col_num, 18)
            elif col_name == 'VÍNCULO':
                ws.set_column(col_num, col_num, 14)
            elif col_name == 'MATRÍCULA':
                ws.set_column(col_num, col_num, 12)
            elif col_name in ['CIN', 'RAMAL', 'TIPO']:
                ws.set_column(col_num, col_num, 15)
            else:
                ws.set_column(col_num, col_num, 20)

        ws.freeze_panes(1, 0)
        ws.autofilter(0, 0, len(df), len(df.columns) - 1)

        ws.set_landscape()
        ws.fit_to_pages(1, 0)
        ws.center_horizontally()
        ws.set_paper(9)  #a4
        ws.set_margins(0.3, 0.5, 1.2, 0.5)

        logo_esquerda = os.path.join(current_app.root_path, 'static', 'imagen2.jpg')
        logo_direita = os.path.join(current_app.root_path, 'static', 'Imagem1.png')

        cabecalho = (
            '&L&G'
            '&C&"Calibri,Bold"&14 COORDENADORIA GERAL REGIONAL - CGR.9\n'
            '&"Calibri, 10" RELATÓRIO DE FUNCIONÁRIOS'
            '&R&G'
        )

        ws.set_header(
            cabecalho,
            {
                'image_left': logo_esquerda,
                'image_right': logo_direita,
                'image_left_scale': 0.05,
                'image_right_scale': 0.4,
                'image_right_margin_right': 0.6,
                'image_right_margin_top': 0.6,
                'image_left_margin': 2.5,
            }
        )

        total_funcionarios = len(df)

        rodape = (
            '&LPágina &P de &N'
            '&CEmitido em: &D'
            f'&RTotal: {total_funcionarios}'
        )
        ws.set_footer(rodape, {'margin': 0.2})

        registrar_evento_seguro(
            'RELATORIO_EXPORTAR_XLSX',
            categoria='relatorio',
            status='sucesso',
            recurso='funcionarios',
            detalhes={
                'q': query[:120],
                'vinculo': vinculo_selecionado,
                'total_resultados': len(resultados),
            },
        )

    return send_file(
        temp_path,
        as_attachment=True,
        download_name='relatorio_funcionarios.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
