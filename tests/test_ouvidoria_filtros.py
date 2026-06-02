from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from flask import Flask

from core.extensions import db
from models import LogAuditoria, Usuario
from routes.ouvidoria import _consulta_logs

class TestOuvidoriaFiltros(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = Flask(__name__)
        cls.app.config.update(
            SECRET_KEY="test-secret",
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
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

        self.ids = self._seed_logs()

    def tearDown(self) -> None:
        db.session.remove()
        self.app_ctx.pop()

    def _seed_logs(self) -> dict[str, int]:
        base = datetime(2026, 4, 15, 10, 0, 0)

        alvo = LogAuditoria(
            id = 70001,
            usuario_login = "Analista",
            acao = "BUSCA_REALIZADA",
            categoria = "busca",
            status = "sucesso",
            recurso = "funcionario",
            recurso_id = "abc",
            detalhes = '{"termo":"estrela guia"}',
            criado_em = base,
        )
        db.session.add(alvo)

        log_outro = LogAuditoria(
            usuario_login="maria",
            acao="BUSCA_REALIZADA",
            categoria="busca",
            status="sucesso",
            recurso="funcionario",
            recurso_id="def",
            detalhes='{"termo":"lua"}',
            criado_em=base + timedelta(seconds=1),
        )
        db.session.add(log_outro)

        bloqueio_ip1 = LogAuditoria(
            usuario_login="admin",
            acao="SEC_BLOQUEIO_IP_LOGIN",
            categoria="seguranca",
            status="sucesso",
            recurso="autenticacao",
            recurso_id="10.0.0.1",
            detalhes='{"ip_alvo":"10.0.0.1"}',
            criado_em=base + timedelta(seconds=10),
        )
        db.session.add(bloqueio_ip1)

        bloqueio_ip2 = LogAuditoria(
            usuario_login="admin",
            acao="SEC_BLOQUEIO_IP_LOGIN",
            categoria="seguranca",
            status="sucesso",
            recurso="autenticacao",
            recurso_id="10.0.0.2",
            detalhes='{"ip_alvo":"10.0.0.2"}',
            criado_em=base + timedelta(seconds=11),
        )
        db.session.add(bloqueio_ip2)

        desbloqueio_ip2 = LogAuditoria(
            usuario_login="admin",
            acao="SEC_DESBLOQUEIO_IP_LOGIN_MANUAL",
            categoria="seguranca",
            status="sucesso",
            recurso="autenticacao",
            recurso_id="10.0.0.2",
            detalhes='{"ip_alvo":"10.0.0.2"}',
            criado_em=base + timedelta(seconds=12),
        )
        db.session.add(desbloqueio_ip2)

        auth_bloqueado_ip1 = LogAuditoria(
            usuario_login="app",
            acao="AUTH_LOGIN_BLOQUEADO_IP",
            categoria="seguranca",
            status="falha",
            recurso="autenticacao",
            recurso_id="10.0.0.1",
            detalhes='{"ip_alvo":"10.0.0.1","login_informado":"estrela"}',
            criado_em=base + timedelta(seconds=13),
        )
        db.session.add(auth_bloqueado_ip1)

        auth_bloqueado_ip2 = LogAuditoria(
            usuario_login="app",
            acao="AUTH_LOGIN_BLOQUEADO_IP",
            categoria="seguranca",
            status="falha",
            recurso="autenticacao",
            recurso_id="10.0.0.2",
            detalhes='{"ip_alvo":"10.0.0.2","login_informado":"estrela"}',
            criado_em=base + timedelta(seconds=14),
        )
        db.session.add(auth_bloqueado_ip2)

        alerta =LogAuditoria(
            usuario_login="sec",
            acao="SEC_ALERTA_EXPORTACAO_MASSIVA",
            categoria="alerta",
            status="sucesso",
            recurso="ouvidoria",
            recurso_id="csv",
            detalhes='{"regra":"exportacao"}',
            criado_em=base+timedelta(seconds = 15),
        )
        db.session.add(alerta)

        falha_comum = LogAuditoria(
            usuario_login="app",
            acao="AUTH_LOGIN_FALHA",
            categoria="seguranca",
            status="falha",
            recurso="autenticacao",
            recurso_id="usr",
            detalhes='{"motivo":"senha"}',
            criado_em=base + timedelta(seconds=16),
        )
        db.session.add(falha_comum)

        operacao = LogAuditoria(
            usuario_login="app",
            acao="AUTH_LOGIN_SUCESSO",
            categoria="seguranca",
            status="sucesso",
            recurso="autenticacao",
            recurso_id="usr",
            detalhes='{"ok":true}',
            criado_em=base + timedelta(seconds=17),
        )
        db.session.add(operacao)

        db.session.commit()

        return{
            "id_q_termo": alvo.id,
            "id_q_id": alvo.id,
            "id_auth_ip1": auth_bloqueado_ip1.id,
            "id_auth_ip2": auth_bloqueado_ip2.id,
            "id_alerta": alerta.id,
            "id_falha_comum": falha_comum.id,
            "id_operacao": operacao.id,
        }

    def _consultar(self, querystring: str):
        with self.app.test_request_context(f"/ouvidoria/logs?{querystring}"):
            consulta, filtros = _consulta_logs()
            logs = consulta.order_by(LogAuditoria.id.asc()).all()
            return logs, filtros

    def test_q_busca_por_termo(self) -> None:
            logs, filtros = self._consultar("q=estrela")
            ids = {log.id for log in logs}

            self.assertIn(self.ids["id_q_termo"], ids)
            self.assertIn(self.ids["id_auth_ip1"], ids)
            self.assertIn(self.ids["id_auth_ip2"], ids)
            self.assertEqual(filtros["q"], "estrela")

    def test_q_busca_por_id_numerico(self) -> None:
            logs, filtros = self._consultar(f"q={self.ids['id_q_id']}")
            ids = [log.id for log in logs]

            self.assertEqual(ids, [self.ids["id_q_id"]])
            self.assertEqual(filtros["q"], str(self.ids["id_q_id"]))

    def test_q_sem_resultados(self) -> None:
            logs, filtros = self._consultar("q=nao_existe_termo_xyz_123")
            self.assertEqual(len(logs), 0)
            self.assertEqual(filtros["q"], "nao_existe_termo_xyz_123")

    def test_q_com_somente_bloqueados(self) -> None:
            logs, filtros = self._consultar("q=auth_login_bloqueado_ip&somente_bloqueados=1")
            ids = {log.id for log in logs}

            self.assertIn(self.ids["id_auth_ip1"], ids)
            self.assertNotIn(self.ids["id_auth_ip2"], ids)
            self.assertTrue(all(log.recurso_id == "10.0.0.1" for log in logs))
            self.assertEqual(filtros["somente_bloqueados"], "1")

    def test_ip_bloqueado_com_somente_bloqueados(self) -> None:
        logs, _ = self._consultar("ip_bloqueado=10.0.0.2&somente_bloqueados=1")
        self.assertEqual(len(logs), 0)

    def test_tipo_evento_alerta(self) -> None:
        logs, filtros = self._consultar("tipo_evento=alerta")
        ids = {log.id for log in logs}
        self.assertIn(self.ids["id_alerta"], ids)
        self.assertEqual(filtros["tipo_evento"], "alerta")

    def test_tipo_evento_falha(self) -> None:
        logs, filtros = self._consultar("tipo_evento=falha")
        ids = {log.id for log in logs}
        self.assertIn(self.ids["id_falha_comum"], ids)
        self.assertNotIn(self.ids["id_alerta"], ids)
        self.assertEqual(filtros["tipo_evento"], "falha")

    def test_tipo_evento_operacao(self) -> None:
        logs, filtros = self._consultar("tipo_evento=operacao")
        ids = {log.id for log in logs}
        self.assertIn(self.ids["id_operacao"], ids)
        self.assertNotIn(self.ids["id_alerta"], ids)
        self.assertEqual(filtros["tipo_evento"], "operacao")
        self.assertNotIn(self.ids["id_falha_comum"], ids)

    if __name__ == "__main__":
        unittest.main()
