from __future__ import annotations

import io
import unittest
from datetime import datetime, UTC
from types import SimpleNamespace
from unittest.mock import patch

import xlsxwriter
from flask import Flask
from openpyxl import load_workbook

from core.extensions import db
from models import LogAuditoria
from routes.ouvidoria import (
    _escrever_logs_xlsx,
    ouvidoria_bp,
)
from services.alertas_seguranca import ACOES_EXPORTACAO_LOGS, _avaliar_exportacao_massiva

COR_CABECALHO = 'FF2F5597'
COR_ZEBRA = 'FFF5F7FA'


def _log_exemplo(**overrides):
    base = {
        'id': 365,
        'criado_em': datetime(2026, 11, 3, 13, 51, 52, tzinfo=UTC),
        'usuario_login': 'admin',
        'acao': 'OUVIDORIA_VISUALIZAR_LOGS',
        'categoria': 'ouvidoria',
        'status': 'sucesso',
        'recurso': 'logs_auditoria',
        'recurso_id': '',
        'ip_origem': '127.0.0.1',
        'rota': '/ouvidoria/logs',
        'detalhes': '{"endpoint": "ouvidoria.logs_ouvidoria", "status_code": 200}',
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _meta_exemplo(logs, **overrides):
    meta = {
        'emitido_em': '03/11/2026 10:51',
        'usuario': 'mestre',
        'filtros': ['Status: "falha"'],
        'total_filtro': len(logs),
        'total_linhas': len(logs),
        'limite': 5000,
    }
    meta.update(overrides)
    return meta


def _gerar_planilha_logs(logs, meta=None) -> bytes:
    buffer = io.BytesIO()
    workbook = xlsxwriter.Workbook(buffer, {'in_memory': True})
    ws = workbook.add_worksheet('LOGS')
    _escrever_logs_xlsx(ws, workbook, logs, meta or _meta_exemplo(logs))
    workbook.close()
    buffer.seek(0)
    return buffer.getvalue()


def _cor(celula) -> str:
    rgb = celula.font.color.rgb if celula.font.color else ''
    return (rgb or '')[-6:]


class TestFormatacaoLogsXlsx(unittest.TestCase):
    """Formatação visual do export de logs, testada na função de escrita."""

    @classmethod
    def setUpClass(cls) -> None:
        logs = [
            _log_exemplo(),
            _log_exemplo(
                id=366,
                criado_em=datetime(2026, 11, 3, 13, 52, 10, tzinfo=UTC),
                usuario_login='',
                status='falha',
                acao='AUTH_LOGIN_FALHA',
                detalhes='texto solto sem json',
            ),
        ]
        conteudo = _gerar_planilha_logs(logs)
        planilha = load_workbook(io.BytesIO(conteudo)).active
        assert planilha is not None
        cls.planilha = planilha

    def test_titulo_e_metadados(self) -> None:
        self.assertEqual(self.planilha['A1'].value, 'LOGS DE OUVIDORIA E SEGURANÇA')
        meta = self.planilha['A2'].value
        assert meta is not None
        self.assertIn('Emitido em 03/11/2026 10:51', meta)
        self.assertIn('por mestre', meta)
        self.assertIn('Filtros: Status: "falha"', meta)
        self.assertIn('Total: 2 registros', meta)
        faixas = [str(faixa) for faixa in self.planilha.merged_cells.ranges]
        self.assertIn('A1:K1', faixas)
        self.assertIn('A2:K2', faixas)

    def test_cabecalho_azul_e_dados(self) -> None:
        celula = self.planilha['A4']
        self.assertEqual(celula.value, 'ID')
        assert celula.fill is not None
        self.assertEqual(celula.fill.fgColor.rgb, COR_CABECALHO)
        self.assertEqual(self.planilha['B4'].value, 'DATA/HORA')
        self.assertEqual(self.planilha['K4'].value, 'DETALHES')
        self.assertEqual(self.planilha['A5'].value, 365)
        self.assertEqual(self.planilha['D5'].value, 'OUVIDORIA_VISUALIZAR_LOGS')

    def test_datahora_celula_real_convertida_para_local(self) -> None:
        # 13:51:52 UTC → 10:51:52 no fuso de Sao Paulo (UTC-3)
        celula = self.planilha['B5']
        self.assertTrue(celula.is_date)
        self.assertEqual(celula.value, datetime(2026, 11, 3, 10, 51, 52))
        self.assertEqual(celula.number_format.lower(), 'dd/mm/yyyy hh:mm')

    def test_status_colorido(self) -> None:
        sucesso = self.planilha['F5']
        self.assertEqual(sucesso.value, 'sucesso')
        self.assertEqual(_cor(sucesso), '006100')
        assert sucesso.font is not None
        self.assertTrue(sucesso.font.bold)

        falha = self.planilha['F6']
        self.assertEqual(falha.value, 'falha')
        self.assertEqual(_cor(falha), '9C0006')

    def test_detalhes_como_json_legivel(self) -> None:
        detalhes = self.planilha['K5'].value
        assert detalhes is not None
        self.assertIn('"endpoint": "ouvidoria.logs_ouvidoria"', detalhes)
        self.assertIn('\n', detalhes)  # indentado em varias linhas
        # texto que nao é JSON permanece como veio
        bruto = self.planilha['K6'].value
        self.assertEqual(bruto, 'texto solto sem json')

    def test_usuario_vazio_permance_vazio(self) -> None:
        # celula vazia — o Excel le como None ou '', nunca com conteudo
        self.assertIn(self.planilha['C6'].value, (None, ''))

    def test_zebra_navegacao_e_impressao(self) -> None:
        primeira = self.planilha['A5']
        segunda = self.planilha['A6']
        self.assertIsNone(primeira.fill.patternType)
        assert segunda.fill is not None
        self.assertEqual(segunda.fill.fgColor.rgb, COR_ZEBRA)
        self.assertEqual(self.planilha.freeze_panes, 'A5')
        self.assertEqual(self.planilha.print_title_rows, '$4:$4')
        self.assertEqual(self.planilha.auto_filter.ref, 'A4:K6')
        assert self.planilha.sheet_view is not None
        self.assertFalse(self.planilha.sheet_view.showGridLines)

    def test_sem_logs_mantem_estrutura(self) -> None:
        conteudo = _gerar_planilha_logs([], _meta_exemplo([], filtros=[]))
        ws = load_workbook(io.BytesIO(conteudo)).active
        assert ws is not None
        self.assertEqual(ws['A1'].value, 'LOGS DE OUVIDORIA E SEGURANÇA')
        meta = ws['A2'].value
        assert meta is not None
        self.assertIn('Total: 0 registros', meta)
        self.assertIn('Filtros: nenhum', meta)
        self.assertEqual(ws['A4'].value, 'ID')
        self.assertIsNone(ws['A5'].value)

    def test_truncamento_no_limite_aparece_no_metadado(self) -> None:
        logs = [_log_exemplo(id=i) for i in range(3)]
        meta = _meta_exemplo(logs, total_filtro=5000, total_linhas=3, limite=5000)
        conteudo = _gerar_planilha_logs(logs, meta)
        ws = load_workbook(io.BytesIO(conteudo)).active
        assert ws is not None
        texto_meta = ws['A2'].value
        assert texto_meta is not None
        self.assertIn('Total no filtro: 5000', texto_meta)
        self.assertIn('Exportando os 3 mais recentes', texto_meta)


class TestRotaExportarLogsXlsx(unittest.TestCase):
    """A rota /ouvidoria/logs/exportar.xlsx: superadmin, filtros e auditoria."""

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
        cls.app.add_url_rule('/painel', endpoint='painel', view_func=lambda: 'painel')
        db.init_app(cls.app)
        cls.app.register_blueprint(ouvidoria_bp)
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
        db.session.query(LogAuditoria).delete()
        db.session.commit()
        self.client = self.app.test_client()

        base = datetime(2026, 11, 3, 13, 0, 0)  # 10:00 no fuso local
        db.session.add(LogAuditoria(
            id=9001, usuario_login='admin', acao='AUTH_LOGIN_FALHA',
            categoria='seguranca', status='falha', recurso='autenticacao',
            recurso_id='', ip_origem='10.0.0.9', rota='/login',
            detalhes='{"login_informado": "admin"}', criado_em=base,
        ))
        db.session.add(LogAuditoria(
            id=9002, usuario_login='admin', acao='BUSCA_REALIZADA',
            categoria='consulta', status='sucesso', recurso='funcionarios',
            recurso_id='', ip_origem='10.0.0.9', rota='/',
            detalhes='{"q": ""}', criado_em=base,
        ))
        db.session.add(LogAuditoria(
            id=9003, usuario_login='admin', acao='AUTH_LOGIN_FALHA',
            categoria='seguranca', status='falha', recurso='autenticacao',
            recurso_id='', ip_origem='10.0.0.9', rota='/login',
            detalhes='{"login_informado": "admin"}',
            criado_em=base.replace(hour=14),  # mais recente
        ))
        db.session.commit()

        self.superadmin = SimpleNamespace(
            is_authenticated=True, is_superadmin=True, login='mestre', id=1,
        )

    def tearDown(self) -> None:
        db.session.remove()
        self.app_ctx.pop()

    def _exportar(self, query_string=None):
        with patch('routes.ouvidoria.current_user', self.superadmin), \
             patch('core.authz.current_user', self.superadmin), \
             patch('routes.ouvidoria.registrar_evento_seguro') as audit_mock:
            resp = self.client.get(
                '/ouvidoria/logs/exportar.xlsx', query_string=query_string)
        return resp, audit_mock

    def test_superadmin_exporta_xlsx_com_filtros_aplicados(self) -> None:
        resp, audit_mock = self._exportar({'status': 'falha'})

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.mimetype,
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        self.assertIn('logs_ouvidoria_', resp.headers.get('Content-Disposition', ''))

        ws = load_workbook(io.BytesIO(resp.data)).active
        assert ws is not None
        self.assertEqual(ws['A1'].value, 'LOGS DE OUVIDORIA E SEGURANÇA')
        meta = ws['A2'].value
        assert meta is not None
        self.assertIn('por mestre', meta)
        self.assertIn('Filtros: Status: "falha"', meta)
        self.assertIn('Total: 2 registros', meta)

        # somente as 2 falhas, a mais recente primeiro
        self.assertEqual(ws['A5'].value, 9003)
        self.assertEqual(ws['A6'].value, 9001)
        # data/hora real convertida para o fuso local
        self.assertEqual(ws['B5'].value, datetime(2026, 11, 3, 11, 0, 0))

        audit_mock.assert_called_once()
        self.assertEqual(audit_mock.call_args[0][0], 'OUVIDORIA_EXPORTAR_XLSX')
        detalhes = audit_mock.call_args.kwargs['detalhes']
        self.assertEqual(detalhes['total_filtro'], 2)
        self.assertEqual(detalhes['total_linhas'], 2)

    def test_sem_filtros_exporta_tudo(self) -> None:
        resp, _ = self._exportar()
        self.assertEqual(resp.status_code, 200)
        ws = load_workbook(io.BytesIO(resp.data)).active
        assert ws is not None
        self.assertEqual(ws['A5'].value, 9003)  # ordem: mais recente primeiro
        self.assertEqual(ws['A6'].value, 9002)
        self.assertEqual(ws['A7'].value, 9001)

    def test_sem_superadmin_e_redirecionado_e_auditado(self) -> None:
        comum = SimpleNamespace(
            is_authenticated=True, is_superadmin=False, login='admin', id=2,
        )
        with patch('routes.ouvidoria.current_user', comum), \
             patch('core.authz.current_user', comum), \
             patch('core.authz.registrar_evento_seguro') as negado_mock:
            resp = self.client.get('/ouvidoria/logs/exportar.xlsx')

        self.assertEqual(resp.status_code, 302)
        self.assertIn('/painel', resp.headers.get('Location', ''))
        negado_mock.assert_called_once()
        self.assertEqual(negado_mock.call_args[0][0], 'AUTH_SUPERADMIN_NEGADO')


class TestAlertaExportacaoMassivaXlsx(unittest.TestCase):
    """Exports CSV e XLSX contam para o mesmo alerta de exportação massiva."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = Flask(__name__)
        cls.app.config.update(
            SECRET_KEY='test-secret',
            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            TESTING=True,
        )
        db.init_app(cls.app)
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
        db.session.query(LogAuditoria).delete()
        db.session.commit()

    def tearDown(self) -> None:
        db.session.remove()
        self.app_ctx.pop()

    def _config(self):
        return {
            'export_limite': 3,
            'export_janela_min': 10,
            'export_cooldown_min': 20,
            'fuso': 'America/Sao_Paulo',
        }

    def test_exports_xlsx_e_csv_acumulam_no_mesmo_limite(self) -> None:
        agora = datetime.now(UTC).replace(tzinfo=None)
        db.session.add(LogAuditoria(
            usuario_login='mestre', acao='OUVIDORIA_EXPORTAR_CSV',
            status='sucesso', criado_em=agora,
        ))
        db.session.add(LogAuditoria(
            usuario_login='mestre', acao='OUVIDORIA_EXPORTAR_XLSX',
            status='sucesso', criado_em=agora,
        ))
        gatilho = LogAuditoria(
            usuario_login='mestre', acao='OUVIDORIA_EXPORTAR_XLSX',
            status='sucesso', criado_em=agora,
        )
        db.session.add(gatilho)
        db.session.commit()  # no fluxo real o evento ja esta gravado

        with patch('services.alertas_seguranca._em_cooldown', return_value=False), \
             patch('services.alertas_seguranca._registrar_alerta') as alerta_mock:
            _avaliar_exportacao_massiva(gatilho, self._config())

        alerta_mock.assert_called_once()
        self.assertEqual(
            alerta_mock.call_args[0][0], 'SEC_ALERTA_EXPORTACAO_MASSIVA')
        contexto = alerta_mock.call_args[0][2]
        self.assertEqual(contexto['ocorrencias'], 3)

    def test_export_de_funcionarios_nao_conta_para_o_alerta(self) -> None:
        agora = datetime.now(UTC).replace(tzinfo=None)
        db.session.add(LogAuditoria(
            usuario_login='mestre', acao='RELATORIO_EXPORTAR_XLSX',
            status='sucesso', criado_em=agora,
        ))
        db.session.commit()

        gatilho = LogAuditoria(
            usuario_login='mestre', acao='OUVIDORIA_EXPORTAR_XLSX',
            status='sucesso', criado_em=agora,
        )

        with patch('services.alertas_seguranca._em_cooldown', return_value=False), \
             patch('services.alertas_seguranca._registrar_alerta') as alerta_mock:
            _avaliar_exportacao_massiva(gatilho, self._config())

        alerta_mock.assert_not_called()

    def test_acoes_monitoradas(self) -> None:
        self.assertIn('OUVIDORIA_EXPORTAR_CSV', ACOES_EXPORTACAO_LOGS)
        self.assertIn('OUVIDORIA_EXPORTAR_XLSX', ACOES_EXPORTACAO_LOGS)


if __name__ == '__main__':
    unittest.main()
