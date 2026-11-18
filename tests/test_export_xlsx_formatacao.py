from __future__ import annotations

import io
import unittest
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import patch

import xlsxwriter
from flask import Flask
from openpyxl import load_workbook

from core.extensions import db
from routes.planilha import (
    ORDEM_EXPORTACAO,
    _escrever_relatorio_xlsx,
    planilha_bp,
)

COR_CABECALHO = 'FF2F5597'
COR_ZEBRA = 'FFF5F7FA'


def _linha_vazia() -> dict[str, object]:
    return {rotulo: '' for _, rotulo in ORDEM_EXPORTACAO}


def _linha_servidor() -> dict[str, object]:
    linha = _linha_vazia()
    linha.update({
        'NOME COMPLETO': 'Servidor Teste',
        'VÍNCULO': 'SERVIDOR',
        'MATRÍCULA': '42219',
        'CPF': '328.381.518-60',
        'DATA DE NASCIMENTO': date(1989, 10, 13),
        'INGRESSO NO DER': datetime(2026, 5, 18),
        'SITUAÇÃO': 'Ativo',
        'EMPRESA CONTRATADA': 'Não se aplica',
        'PREPOSTO': 'Não se aplica',
    })
    return linha


def _linha_terceirizado() -> dict[str, object]:
    linha = _linha_vazia()
    linha.update({
        'NOME COMPLETO': 'Terceirizado Teste',
        'VÍNCULO': 'TERCEIRIZADO',
        'MATRÍCULA': 'Não se aplica',
        'CPF': '519.928.088-05',
        'DATA DE NASCIMENTO': '24/07/2006',  # string também vira data real
        'SITUAÇÃO': 'Inativo - Término de contrato',
        'DATA DESLIGAMENTO': '*',
        'EMPRESA CONTRATADA': 'G4f Solucoes Corporativas Ltda',
        'PREPOSTO': 'Jenifer Caroline Da Rocha',
    })
    return linha


def _gerar_planilha(linhas, meta=None) -> bytes:
    if meta is None:
        meta = {
            'emitido_em': '03/11/2026 10:50',
            'usuario': 'admin',
            'filtro': 'Todos os vínculos',
            'busca': '',
            'total': len(linhas),
        }
    buffer = io.BytesIO()
    workbook = xlsxwriter.Workbook(buffer, {'in_memory': True})
    ws = workbook.add_worksheet('FUNCIONARIOS')
    _escrever_relatorio_xlsx(ws, workbook, linhas, ORDEM_EXPORTACAO, meta)
    workbook.close()
    buffer.seek(0)
    return buffer.getvalue()


def _cor(celula) -> str:
    rgb = celula.font.color.rgb if celula.font.color else ''
    return (rgb or '')[-6:]


class TestFormatacaoRelatorioXlsx(unittest.TestCase):
    """Formatação visual do relatório, testada direto na função de escrita."""

    @classmethod
    def setUpClass(cls) -> None:
        conteudo = _gerar_planilha([_linha_servidor(), _linha_terceirizado()])
        planilha = load_workbook(io.BytesIO(conteudo)).active
        assert planilha is not None
        cls.planilha = planilha

    def test_titulo_e_metadados_visiveis_na_tela(self) -> None:
        self.assertEqual(self.planilha['A1'].value, 'RELATÓRIO DE FUNCIONÁRIOS')
        meta = self.planilha['A2'].value
        assert meta is not None
        self.assertIn('Emitido em 03/11/2026 10:50', meta)
        self.assertIn('por admin', meta)
        self.assertIn('Vínculo: Todos os vínculos', meta)
        self.assertIn('Total: 2 registros', meta)
        faixas = [str(faixa) for faixa in self.planilha.merged_cells.ranges]
        self.assertIn('A1:AJ1', faixas)
        self.assertIn('A2:AJ2', faixas)

    def test_cabecalho_da_tabela_na_linha_4(self) -> None:
        celula = self.planilha['A4']
        self.assertEqual(celula.value, 'NOME COMPLETO')
        assert celula.fill is not None
        self.assertEqual(celula.fill.fgColor.rgb, COR_CABECALHO)
        assert celula.font is not None
        self.assertTrue(celula.font.bold)

    def test_dados_comecam_na_linha_5(self) -> None:
        self.assertEqual(self.planilha['A5'].value, 'Servidor Teste')
        self.assertEqual(self.planilha['A6'].value, 'Terceirizado Teste')

    def test_datas_como_celula_de_data_real(self) -> None:
        # coluna I = DATA DE NASCIMENTO (9a coluna)
        nascimento = self.planilha['I5']
        self.assertTrue(nascimento.is_date)
        self.assertEqual(nascimento.value, datetime(1989, 10, 13))
        self.assertEqual(nascimento.number_format.lower(), 'dd/mm/yyyy')
        # string '24/07/2006' é convertida em data real também
        nascimento_txt = self.planilha['I6']
        self.assertTrue(nascimento_txt.is_date)
        self.assertEqual(nascimento_txt.value, datetime(2006, 7, 24))

    def test_valor_nao_data_permite_texto(self) -> None:
        # coluna AC = DATA DESLIGAMENTO; '*' não é data e segue como texto
        celula = self.planilha['AC6']
        self.assertEqual(celula.value, '*')
        self.assertFalse(celula.is_date)

    def test_nao_se_aplica_em_italico_cinza(self) -> None:
        # coluna C = MATRÍCULA do terceirizado
        celula = self.planilha['C6']
        self.assertEqual(celula.value, 'Não se aplica')
        assert celula.font is not None
        self.assertTrue(celula.font.italic)
        self.assertEqual(_cor(celula), '808080')

    def test_situacao_com_cor(self) -> None:
        # coluna AB = SITUAÇÃO
        ativo = self.planilha['AB5']
        self.assertEqual(ativo.value, 'Ativo')
        self.assertEqual(_cor(ativo), '006100')
        assert ativo.font is not None
        self.assertTrue(ativo.font.bold)

        inativo = self.planilha['AB6']
        self.assertEqual(inativo.value, 'Inativo - Término de contrato')
        self.assertEqual(_cor(inativo), '9C0006')

    def test_zebra_apartir_da_segunda_linha_de_dados(self) -> None:
        primeira = self.planilha['A5']
        segunda = self.planilha['A6']
        self.assertIsNone(primeira.fill.patternType)
        assert segunda.fill is not None
        self.assertEqual(segunda.fill.fgColor.rgb, COR_ZEBRA)

    def test_navegacao_e_impressao(self) -> None:
        self.assertEqual(self.planilha.freeze_panes, 'A5')
        # no papel repete o CABEÇALHO (linha 4), não a 1ª linha de dados
        self.assertEqual(self.planilha.print_title_rows, '$4:$4')
        self.assertEqual(self.planilha.auto_filter.ref, 'A4:AJ6')
        assert self.planilha.sheet_view is not None
        self.assertFalse(self.planilha.sheet_view.showGridLines)

    def test_relatorio_vazio_mantem_estrutura(self) -> None:
        conteudo = _gerar_planilha([])
        ws = load_workbook(io.BytesIO(conteudo)).active
        assert ws is not None
        self.assertEqual(ws['A1'].value, 'RELATÓRIO DE FUNCIONÁRIOS')
        meta = ws['A2'].value
        assert meta is not None
        self.assertIn('Total: 0 registros', meta)
        self.assertEqual(ws['A4'].value, 'NOME COMPLETO')
        self.assertIsNone(ws['A5'].value)


class TestRotaExportarXlsx(unittest.TestCase):
    """A rota /export/xlsx entrega o arquivo com o novo layout."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = Flask(__name__)
        cls.app.config.update(
            SECRET_KEY='test-secret',
            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            LOGIN_DISABLED=True,
        )
        cls.app.config['WHOOSH_IX'] = object()
        # endpoint dummy: a rota redireciona para busca.index quando chamada
        # sem parâmetros de filtro
        cls.app.add_url_rule('/', endpoint='busca.index', view_func=lambda: 'busca teste')
        db.init_app(cls.app)
        cls.app.register_blueprint(planilha_bp)
        with cls.app.app_context():
            db.create_all()

    @classmethod
    def tearDownClass(cls) -> None:
        with cls.app.app_context():
            db.session.remove()
            db.drop_all()

    def setUp(self) -> None:
        self.app_ctx = self.app.app_context()
        self.app_ctx.push()
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        db.session.remove()
        self.app_ctx.pop()

    def test_export_produz_planilha_com_novo_layout(self) -> None:
        resultados = [
            {
                'nome_completo': 'Servidor Teste',
                'vinculo': 'SERVIDOR',
                'matricula': '42219',
                'cpf': '32838151860',
                'data_nasc': datetime(1989, 10, 13),
                'situacao': 'Ativo',
            },
            {
                'nome_completo': 'Terceirizado Teste',
                'vinculo': 'TERCEIRIZADO',
                'empresa_contratada': 'G4f Solucoes Corporativas Ltda',
                'situacao': 'Ativo',
            },
        ]

        usuario_fake = SimpleNamespace(is_authenticated=True, login='admin')
        with patch('routes.planilha.executar_busca', return_value=resultados), \
             patch('routes.planilha.registrar_evento_seguro') as audit_mock, \
             patch('routes.planilha.current_user', usuario_fake):
            resp = self.client.get('/export/xlsx?q=&vinculo=todos')

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.mimetype,
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        self.assertIn(
            'relatorio_funcionarios.xlsx',
            resp.headers.get('Content-Disposition', ''),
        )

        ws = load_workbook(io.BytesIO(resp.data)).active
        assert ws is not None
        self.assertEqual(ws['A1'].value, 'RELATÓRIO DE FUNCIONÁRIOS')
        meta = ws['A2'].value
        assert meta is not None
        self.assertIn('por admin', meta)
        self.assertEqual(ws['A4'].value, 'NOME COMPLETO')
        self.assertEqual(ws['A5'].value, 'Servidor Teste')
        self.assertEqual(ws['A6'].value, 'Terceirizado Teste')
        self.assertTrue(ws['I5'].is_date)
        # terceirizado sem matrícula → "Não se aplica" discreto
        self.assertEqual(ws['C6'].value, 'Não se aplica')

        audit_mock.assert_called_once()
        self.assertEqual(audit_mock.call_args[0][0], 'RELATORIO_EXPORTAR_XLSX')

    def test_export_sem_parametros_redireciona_para_busca(self) -> None:
        resp = self.client.get('/export/xlsx')
        self.assertEqual(resp.status_code, 302)


if __name__ == '__main__':
    unittest.main()
