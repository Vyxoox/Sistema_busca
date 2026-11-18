from __future__ import annotations

import os
import unittest
from unittest.mock import PropertyMock, patch

from sqlalchemy.exc import DBAPIError, OperationalError

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret")

import app as app_module
from app import app
from core.config import _engine_options


class TestEngineOptions(unittest.TestCase):
    """Regressao do HY092 (2026-11-03): attrs_before so aceita atributos de
    CONEXAO (SQLSetConnectAttr); SQL_ATTR_QUERY_TIMEOUT e atributo de
    STATEMENT. Defini-lo ali derrubava TODAS as conexoes pyodbc, mesmo com
    o banco saudavel. O query timeout nunca deve voltar para _engine_options."""

    def test_engine_options_sem_attrs_before(self) -> None:
        opts = _engine_options(
            "mssql+pyodbc://usuario:senha@host:1433/db?driver=ODBC+Driver+18+for+SQL+Server"
        )
        self.assertNotIn("attrs_before", opts["connect_args"])
        # timeout de LOGIN (pyodbc) continua presente
        self.assertEqual(opts["connect_args"]["timeout"], 10)

    def test_listener_timeout_query_aplicado_em_conexao_pyodbc(self) -> None:
        class ConexaoPyodbcFake:
            timeout = 0

        ConexaoPyodbcFake.__module__ = "pyodbc"  # simula modulo do driver
        conn = ConexaoPyodbcFake()
        app_module._aplicar_timeout_query(conn, None)
        self.assertEqual(conn.timeout, app.config.get("DB_STATEMENT_TIMEOUT", 300))

    def test_listener_nao_toca_conexoes_nao_pyodbc(self) -> None:
        class ConexaoSqliteFake:
            timeout = 5  # busy timeout do sqlite — nao deve ser alterado

        ConexaoSqliteFake.__module__ = "sqlite3"
        conn = ConexaoSqliteFake()
        app_module._aplicar_timeout_query(conn, None)
        self.assertEqual(conn.timeout, 5)

    def test_listener_respeita_zero_desativado(self) -> None:
        class ConexaoPyodbcFake:
            timeout = 0

        ConexaoPyodbcFake.__module__ = "pyodbc"
        conn = ConexaoPyodbcFake()
        with patch.dict(app.config, {"DB_STATEMENT_TIMEOUT": 0}):
            app_module._aplicar_timeout_query(conn, None)
        self.assertEqual(conn.timeout, 0)


class TestGateBoot(unittest.TestCase):
    """Gate de boot (_verificar_conexao_banco): comportamento nas 3 saidas."""

    @classmethod
    def setUpClass(cls) -> None:
        app.config.update(TESTING=True)

    def test_gate_sucesso_banco_responde(self) -> None:
        with app.app_context():
            self.assertTrue(
                app_module._verificar_conexao_banco(tentativas=1, pausa_segundos=0)
            )

    def test_gate_falha_banco_inacessivel(self) -> None:
        with app.app_context():
            with patch.object(
                type(app_module.db),
                "engine",
                new_callable=PropertyMock,
            ) as engine_falso:
                engine_falso.side_effect = OperationalError(
                    "08001", None, Exception("SQL Server nao responde")
                )
                self.assertFalse(
                    app_module._verificar_conexao_banco(tentativas=2, pausa_segundos=0)
                )

    def test_gate_desativado_por_env_nao_toca_banco(self) -> None:
        with app.app_context():
            with patch.dict(os.environ, {"DB_BOOT_CHECK": "false"}):
                with patch.object(
                    type(app_module.db),
                    "engine",
                    new_callable=PropertyMock,
                ) as engine_falso:
                    engine_falso.side_effect = RuntimeError(
                        "DB_BOOT_CHECK=false nao deveria tocar o banco"
                    )
                    self.assertTrue(
                        app_module._verificar_conexao_banco(
                            tentativas=1, pausa_segundos=0
                        )
                    )


class TestHandlerBancoIndisponivel(unittest.TestCase):
    """OperationalError em rota real (POST /login) -> pagina 503 amigavel
    com Retry-After, no lugar do 500 criptico do waitress."""

    @classmethod
    def setUpClass(cls) -> None:
        app.config.update(TESTING=True)

    def setUp(self) -> None:
        self.client = app.test_client()

    def test_503_pagina_amigavel_rota_comum(self) -> None:
        with patch(
            "repositories.usuario_repository.UsuarioRepository.buscar_por_login",
            side_effect=OperationalError("08001", None, Exception("conexao morta")),
        ):
            # CSRF desligado apenas neste teste: o foco e o caminho do erro
            # de banco, nao a validacao de formulario.
            with patch.dict(app.config, {"WTF_CSRF_ENABLED": False}):
                resp = self.client.post(
                    "/login", data={"login": "qualquer", "password": "qualquer"}
                )

        self.assertEqual(resp.status_code, 503)
        self.assertIn("temporariamente indispon", resp.get_data(as_text=True).lower())
        self.assertEqual(resp.headers.get("Retry-After"), "30")

    def test_503_para_erros_dbapi_genericos(self) -> None:
        """Erros de driver/config (ex.: HY092) chegam como DBAPIError puro,
        nao OperationalError — antes escapavam para o 500 do waitress."""
        with patch(
            "repositories.usuario_repository.UsuarioRepository.buscar_por_login",
            side_effect=DBAPIError(
                "SELECT 1", None, RuntimeError("(HY092) atributo invalido"), False
            ),
        ):
            with patch.dict(app.config, {"WTF_CSRF_ENABLED": False}):
                resp = self.client.post(
                    "/login", data={"login": "qualquer", "password": "qualquer"}
                )

        self.assertEqual(resp.status_code, 503)
        self.assertIn("temporariamente indispon", resp.get_data(as_text=True).lower())


if __name__ == "__main__":
    unittest.main()
