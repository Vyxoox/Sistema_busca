import os
import tempfile
from datetime import date, datetime
from zoneinfo import ZoneInfo

import xlsxwriter
from flask import Blueprint, request, redirect, url_for, send_file, current_app
from flask_login import login_required, current_user

from core.audit_policy import audit_event
from services.busca_service import executar_busca
from services.formatacao_service import formatar_cpf, formatar_rg
from services.exportacao_service import valor_exportacao_resultado, limpar_valor_excel

from services.auditoria_services import registrar_evento_seguro

planilha_bp = Blueprint('planilha', __name__)

FUSO_LOCAL = ZoneInfo('America/Sao_Paulo')

NAO_SE_APLICA = 'Não se aplica'

# Campos gravados como celula de DATA real do Excel (dd/mm/aaaa), em vez de
# texto: permitem ordenar e filtrar por periodo dentro da planilha.
CAMPOS_DATA = {
    'data_nasc',
    'data_ingresso_der',
    'data_inicio',
    'data_admissao',
    'data_desligamento',
}

# Paleta do relatorio (azul institucional mantido do layout anterior).
COR_CABECALHO = '#2F5597'
COR_ZEBRA = '#F5F7FA'
COR_SUBTITULO = '#7F7F7F'
COR_TEXTO_DISCRETO = '#808080'
COR_SITUACAO_ATIVA = '#006100'
COR_SITUACAO_INATIVA = '#9C0006'

LARGURA_MIN = 11
LARGURA_MAX = 42

ORDEM_EXPORTACAO = [
    ('nome_completo', 'NOME COMPLETO'),
    ('vinculo', 'VÍNCULO'),
    ('matricula', 'MATRÍCULA'),
    ('cpf', 'CPF'),
    ('rg', 'RG'),
    ('cin', 'CIN'),
    ('titulo_eleitor', 'TÍTULO DE ELEITOR'),
    ('pis_pasep', 'PIS/PASEP'),
    ('data_nasc', 'DATA DE NASCIMENTO'),
    ('endereco_residencial', 'ENDEREÇO RESIDENCIAL'),
    ('telefone_pessoal', 'TELEFONE PESSOAL'),
    ('contato_emergencia', 'CONTATO DE EMERGÊNCIA'),
    ('email_pessoal', 'EMAIL PESSOAL'),
    ('email_institucional', 'EMAIL INSTITUCIONAL'),
    ('ramal', 'RAMAL(173218)'),
    ('tipo', 'TIPO'),
    ('subtipo_vinculo', 'SUBTIPO VÍNCULO'),
    ('forma_ingresso', 'FORMA DE INGRESSO'),
    ('prontuario_funcional', 'PRONTUÁRIO FUNCIONAL'),
    ('cargo_exercicio', 'CARGO EM EXERCÍCIO'),
    ('cargo_origem', 'CARGO DE ORIGEM'),
    ('lotacao', 'LOTAÇÃO'),
    ('area', 'ÁREA DE ATUAÇÃO'),
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
    ('preposto', 'PREPOSTO'),
]

# Colunas centralizadas horizontalmente (codigos, datas e categorias curtas).
COLUNAS_CENTRALIZADAS = {
    'VÍNCULO', 'MATRÍCULA', 'CPF', 'RG', 'CIN', 'PIS/PASEP',
    'RAMAL(173218)', 'TIPO', 'SUBTIPO VÍNCULO', 'SITUAÇÃO',
    'DATA DE NASCIMENTO', 'INGRESSO NO DER', 'DATA INÍCIO',
    'DATA ADMISSÃO', 'DATA DESLIGAMENTO',
}


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


def _rotulo_vinculo(vinculo_selecionado):
    chave = (vinculo_selecionado or 'todos').strip().lower()
    return {
        'todos': 'Todos os vínculos',
        'servidor': 'Servidores',
        'terceirizado': 'Terceirizados',
    }.get(chave, vinculo_selecionado or 'Todos os vínculos')


def _valor_para_datetime(valor):
    """Converte date/datetime (ou string de data conhecida) em datetime ingênuo.

    Retorna None quando o valor não representa uma data válida — nesse caso a
    célula é gravada como texto comum (ex.: '*', 'Não se aplica', '').
    """
    if isinstance(valor, datetime):
        return valor.replace(tzinfo=None) if valor.tzinfo is not None else valor
    if isinstance(valor, date):
        return datetime(valor.year, valor.month, valor.day)
    if isinstance(valor, str):
        texto = valor.strip()
        if not texto:
            return None
        for formato in ('%d/%m/%Y', '%Y-%m-%d'):
            try:
                return datetime.strptime(texto[:10], formato)
            except ValueError:
                continue
    return None


def _largura_exibicao(valor):
    """Tamanho aproximado do valor tal como exibido na planilha."""
    if valor is None:
        return 0
    if isinstance(valor, (datetime, date)):
        return 10
    return len(str(valor))


def _escrever_relatorio_xlsx(ws, workbook, linhas, ordem, meta):
    """Escreve o relatório completo (título, metadados e tabela) na planilha.

    Função pura de apresentação: não toca em request/current_app, para poder
    ser testada isoladamente e reaproveitada.

    - ws/workbook: objetos do XlsxWriter;
    - linhas: lista de dicts {rótulo: valor bruto} (datas como date/datetime);
    - ordem: lista de tuplas (campo, rótulo) — define colunas e ordem;
    - meta: emitido_em, usuario, filtro, busca, total e caminhos das logos.
    """
    rotulos = [rotulo for _, rotulo in ordem]
    campo_por_rotulo = {rotulo: campo for campo, rotulo in ordem}
    total_colunas = len(rotulos)

    linha_titulo = 0
    linha_meta = 1
    # linha 2 é um respiro visual entre o cabeçalho do relatório e a tabela
    linha_cabecalho = 3
    primeira_linha_dados = 4

    # ---------------- formatos ----------------
    titulo_fmt = workbook.add_format({
        'font_name': 'Calibri', 'font_size': 16, 'bold': True,
        'font_color': COR_CABECALHO, 'valign': 'vcenter',
    })
    meta_fmt = workbook.add_format({
        'font_name': 'Calibri', 'font_size': 9, 'italic': True,
        'font_color': COR_SUBTITULO, 'valign': 'vcenter',
        'bottom': 1, 'bottom_color': COR_CABECALHO,
    })
    cabecalho_fmt = workbook.add_format({
        'font_name': 'Calibri', 'font_size': 10, 'bold': True,
        'bg_color': COR_CABECALHO, 'font_color': 'white',
        'align': 'center', 'valign': 'vcenter', 'text_wrap': True,
        'border': 1,
    })

    base_celula = {
        'font_name': 'Calibri', 'font_size': 9,
        'border': 1, 'text_wrap': True, 'valign': 'vcenter',
    }

    def _formato_celula(centralizada, zebra, discreta=False, data=False):
        conf = dict(base_celula)
        conf['align'] = 'center' if centralizada else 'left'
        if zebra:
            conf['bg_color'] = COR_ZEBRA
        if discreta:
            conf['italic'] = True
            conf['font_color'] = COR_TEXTO_DISCRETO
        if data:
            conf['num_format'] = 'dd/mm/yyyy'
        return workbook.add_format(conf)

    formatos = {}
    for centralizada in (False, True):
        for zebra in (False, True):
            formatos[(centralizada, zebra)] = _formato_celula(centralizada, zebra)
            formatos[(centralizada, zebra, 'nsa')] = _formato_celula(
                centralizada, zebra, discreta=True)
            formatos[(centralizada, zebra, 'data')] = _formato_celula(
                centralizada, zebra, data=True)

    cache_situacao = {}

    def _formato_situacao(valor, zebra):
        texto = str(valor).strip().lower()
        cor = COR_SITUACAO_ATIVA if texto == 'ativo' else COR_SITUACAO_INATIVA
        chave = (cor, zebra)
        if chave not in cache_situacao:
            conf = dict(base_celula)
            conf.update({'align': 'center', 'bold': True, 'font_color': cor})
            if zebra:
                conf['bg_color'] = COR_ZEBRA
            cache_situacao[chave] = workbook.add_format(conf)
        return cache_situacao[chave]

    # ---------------- título e metadados (visíveis na tela) ----------------
    partes_meta = [f"Emitido em {meta['emitido_em']}"]
    if meta.get('usuario'):
        partes_meta.append(f"por {meta['usuario']}")
    partes_meta.append(f"Vínculo: {meta['filtro']}")
    if meta.get('busca'):
        partes_meta.append(f"Busca: “{meta['busca']}”")
    total = meta['total']
    partes_meta.append(f"Total: {total} registro{'s' if total != 1 else ''}")

    ws.merge_range(linha_titulo, 0, linha_titulo, total_colunas - 1,
                   'RELATÓRIO DE FUNCIONÁRIOS', titulo_fmt)
    ws.set_row(linha_titulo, 30)

    ws.merge_range(linha_meta, 0, linha_meta, total_colunas - 1,
                   ' · '.join(partes_meta), meta_fmt)
    ws.set_row(linha_meta, 18)
    ws.set_row(2, 6)

    # ---------------- cabeçalho da tabela ----------------
    for coluna, rotulo in enumerate(rotulos):
        ws.write(linha_cabecalho, coluna, rotulo, cabecalho_fmt)
    ws.set_row(linha_cabecalho, 45)

    # ---------------- dados ----------------
    for indice, linha in enumerate(linhas):
        num_linha = primeira_linha_dados + indice
        zebra = indice % 2 == 1
        for coluna, rotulo in enumerate(rotulos):
            campo = campo_por_rotulo[rotulo]
            valor = linha.get(rotulo, '')
            centralizada = rotulo in COLUNAS_CENTRALIZADAS

            if valor == NAO_SE_APLICA:
                # "Não se aplica" em itálico cinza: some do primeiro olhar
                ws.write(num_linha, coluna, valor,
                         formatos[(centralizada, zebra, 'nsa')])
            elif campo == 'situacao' and valor not in ('', None):
                ws.write(num_linha, coluna, str(valor),
                         _formato_situacao(valor, zebra))
            elif campo in CAMPOS_DATA:
                momento = _valor_para_datetime(valor)
                if momento is not None:
                    ws.write_datetime(num_linha, coluna, momento,
                                      formatos[(centralizada, zebra, 'data')])
                else:
                    # valor textual (ex.: '*') — permanece texto comum
                    ws.write(num_linha, coluna, valor if valor is not None else '',
                             formatos[(centralizada, zebra)])
            else:
                ws.write(num_linha, coluna, valor if valor is not None else '',
                         formatos[(centralizada, zebra)])
        # Altura automatica (sem set_row): o Excel expande a linha ate o
        # texto quebrado inteiro ficar visivel — enderecos e lotacoes
        # longos deixam de ficar cortados pela altura fixa antiga (22).

    # ---------------- larguras (auto-ajustadas pelo conteúdo) ----------------
    for coluna, (campo, rotulo) in enumerate(ordem):
        maior = max(
            (_largura_exibicao(linha.get(rotulo)) for linha in linhas),
            default=0,
        )
        # palavras do cabeçalho não podem quebrar no meio
        maior_palavra = max((len(palavra) for palavra in rotulo.split()), default=0)
        largura = min(
            max(maior + 2, maior_palavra + 2, LARGURA_MIN), LARGURA_MAX,
        )
        if rotulo == 'NOME COMPLETO':
            largura = max(largura, 30)
        ws.set_column(coluna, coluna, largura)

    # ---------------- navegação ----------------
    ws.freeze_panes(primeira_linha_dados, 0)
    ws.autofilter(linha_cabecalho, 0, linha_cabecalho + len(linhas),
                  total_colunas - 1)
    # Repete o CABEÇALHO da tabela no topo de cada página impressa
    # (antes repetia a primeira linha de dados — corrigido).
    ws.repeat_rows(linha_cabecalho)

    # Sem linhas de grade: fora da tabela o fundo fica limpo; a tabela em si
    # é delimitada pelas bordas das próprias células.
    ws.hide_gridlines(2)

    # Matrícula/ramal/telefone são texto de propósito (zeros à esquerda e
    # pontuação) — suprime o aviso "número armazenado como texto" do Excel.
    if hasattr(ws, 'ignore_errors'):
        ws.ignore_errors({'number_stored_as_text': True})

    # ---------------- impressão ----------------
    ws.set_landscape()
    ws.fit_to_pages(1, 0)
    ws.center_horizontally()
    ws.set_paper(9)  # A4
    ws.set_margins(0.3, 0.5, 1.2, 0.5)

    logo_esquerda = meta.get('logo_esquerda')
    logo_direita = meta.get('logo_direita')
    if (logo_esquerda and logo_direita
            and os.path.isfile(logo_esquerda) and os.path.isfile(logo_direita)):
        cabecalho_impressao = (
            '&L&G'
            '&C&"Calibri,Bold"&12 COORDENADORIA GERAL REGIONAL - CGR.9'
            '&R&G'
        )
        ws.set_header(
            cabecalho_impressao,
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

    rodape = (
        '&LPágina &P de &N'
        '&CEmitido em: &D'
        f'&RTotal: {total}'
    )
    ws.set_footer(rodape, {'margin': 0.2})


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

    linhas = []
    for r in resultados:
        linha = {}
        for campo, rotulo in ORDEM_EXPORTACAO:
            val = valor_exportacao_resultado(r, campo)
            val = limpar_valor_excel(val)

            if campo == 'cpf' and val not in ('', NAO_SE_APLICA):
                val = formatar_cpf(val)
            elif campo == 'rg' and val not in ('', NAO_SE_APLICA):
                val = formatar_rg(val)
            # As datas seguem como objetos date/datetime até a gravação —
            # viram células de data real (dd/mm/aaaa) na planilha.

            val = limpar_valor_excel(val)
            linha[rotulo] = val
        linhas.append(linha)

    usuario_exportacao = ''
    if current_user.is_authenticated:
        usuario_exportacao = str(getattr(current_user, 'login', '') or '')

    meta = {
        'emitido_em': datetime.now(FUSO_LOCAL).strftime('%d/%m/%Y %H:%M'),
        'usuario': usuario_exportacao,
        'filtro': _rotulo_vinculo(vinculo_selecionado),
        'busca': query,
        'total': len(linhas),
        'logo_esquerda': os.path.join(current_app.root_path, 'static', 'imagen2.jpg'),
        'logo_direita': os.path.join(current_app.root_path, 'static', 'Imagem1.png'),
    }

    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
    temp_path = temp_file.name
    temp_file.close()

    workbook = xlsxwriter.Workbook(temp_path)
    ws = workbook.add_worksheet('FUNCIONARIOS')
    _escrever_relatorio_xlsx(ws, workbook, linhas, ORDEM_EXPORTACAO, meta)
    workbook.close()

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
