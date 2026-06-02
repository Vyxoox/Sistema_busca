from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from flask import Flask

from core.extensions import db
from models import LogAuditoria, Usuario
from services.auditoria_retencao_service import expurgar_logs_auditoria


class TestAuditoriaRetencao(unittest.TestCase):
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
        db.session.query(Usuario).delete()
        db.session.commit()

        self.base = datetime(2026, 4, 16, 12, 0, 0)
        self._seed()

    def tearDown(self) -> None:
        db.session.remove()
        self.app_ctx.pop()

    def _seed(self) -> None:
        logs = [
            LogAuditoria(
                usuario_login='u1',
                acao='BUSCA_REALIZADA',
                categoria='busca',
                status='sucesso',
                recurso='funcionario',
                recurso_id='1',
                detalhes='{}',
                criado_em=self.base - timedelta(days=500),  # elegível geral
            ),
            LogAuditoria(
                usuario_login='u2',
                acao='AUTH_LOGIN_FALHA',
                categoria='seguranca',
                status='falha',
                recurso='auth',
                recurso_id='2',
                detalhes='{}',
                criado_em=self.base - timedelta(days=1900),  # elegível segurança
            ),
            LogAuditoria(
                usuario_login='u3',
                acao='SEC_ALERTA_EXPORTACAO_MASSIVA',
                categoria='alerta',
                status='sucesso',
                recurso='ouvidoria',
                recurso_id='3',
                detalhes='{}',
                criado_em=self.base - timedelta(days=3000),  # NÃO elegível alerta (limite 3650)
            ),
            LogAuditoria(
                usuario_login='u4',
                acao='AUTH_LOGIN_SUCESSO',
                categoria='seguranca',
                status='sucesso',
                recurso='auth',
                recurso_id='4',
                detalhes='{}',
                criado_em=self.base - timedelta(days=100),  # recente
            ),
        ]
        db.session.add_all(logs)
        db.session.commit()

    def test_dry_run_nao_apaga(self) -> None:
        r = expurgar_logs_auditoria(
            dias_geral=365,
            dias_seguranca=1825,
            dias_alerta=3650,
            dry_run=True,
            agora_utc=self.base,
        )
        self.assertEqual(r['elegiveis'], 2)
        self.assertEqual(r['apagados'], 0)
        self.assertEqual(LogAuditoria.query.count(), 4)

    def test_apply_apaga_elegiveis(self) -> None:
        r = expurgar_logs_auditoria(
            dias_geral=365,
            dias_seguranca=1825,
            dias_alerta=3650,
            dry_run=False,
            agora_utc=self.base,
        )
        self.assertEqual(r['elegiveis'], 2)
        self.assertEqual(r['apagados'], 2)
        self.assertEqual(LogAuditoria.query.count(), 3)

        acoes_restantes = {x.acao for x in LogAuditoria.query.all()}
        self.assertIn('SEC_ALERTA_EXPORTACAO_MASSIVA', acoes_restantes)
        self.assertIn('AUTH_LOGIN_SUCESSO', acoes_restantes)


if __name__ == '__main__':
    unittest.main()
