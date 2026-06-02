from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask

from core.extensions import db
from models import Funcionario
from routes.criacao import (
    criacao_bp,
    OPCOES_SUBTIPO_VINCULO,
    OPCOES_LOTACAO,
    OPCOES_AREA,
    OPCOES_COORDENADORIA,
    OPCOES_TIPO,
    OPCOES_FORMA_INGRESSO,
    OPCOES_SITUACAO,
)


def _payload_base()->dict[str, str]:
    return {
        "subtipo_vinculo": OPCOES_SUBTIPO_VINCULO[0],
        "lotacao": OPCOES_LOTACAO[0],
        "area": OPCOES_AREA[0],
        "coordenadoria": OPCOES_COORDENADORIA[0],
        "tipo": OPCOES_TIPO[0],
        "forma_ingresso": OPCOES_FORMA_INGRESSO[0],
        "situacao": OPCOES_SITUACAO[0],
    }

def _preencher_servidor_minimo(func, form):
    func.nome_completo = "Servidor Teste"
    func.cpf = "11122233344"
    func.pis_pasep = "12345678900"
    func.endereco_residencial = "Rua Teste, 1"
    func.email_institucional = "srv@teste.gov"
    func.ramal = "1732180001"
    func.tipo = form["tipo"]
    func.subtipo_vinculo = form["subtipo_vinculo"]
    func.forma_ingresso = form["forma_ingresso"]
    func.lotacao = form["lotacao"]
    func.area = form["area"]
    func.coordenadoria = form["coordenadoria"]
    func.situacao = form["situacao"]
    func.matricula = "MAT-001"
    func.ativo = True

def _preencher_terceirizado_minimo(func, form):
    func.nome_completo = "Terceirizado Teste"
    func.cpf = "55566677788"
    func.pis_pasep = "00987654321"
    func.endereco_residencial = "Rua Teste, 2"
    func.email_institucional = "terc@teste.gov"
    func.ramal = "1732180002"
    func.tipo = form["tipo"]
    func.subtipo_vinculo = form["subtipo_vinculo"]
    func.forma_ingresso = form["forma_ingresso"]
    func.lotacao = form["lotacao"]
    func.area = form["area"]
    func.coordenadoria = form["coordenadoria"]
    func.situacao = form["situacao"]
    func.empresa_contratada = "Empresa X"
    func.numero_contrato = "CTR-01"
    func.gestor_contrato = "Gestor X"
    func.fiscal_tecnico = "Fiscal Tec"
    func.fiscal_administrativo = "Fiscal Adm"
    func.preposto = "Preposto X"
    func.ativo = True

class TestCriacaoRotasAllowlist(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = Flask(__name__)
        cls.app.config.update(
            SECRET_KEY="test-secret",
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            TESTING=True,
            WTF_CSRF_ENABLE=False,
            LOGIN_DISABLED=True,
        )
        cls.app.config["WHOOSH_IX"] = object()
        cls.app.add_url_rule("/painel", endpoint="painel", view_func=lambda: "Painel teste")
        db.init_app(cls.app)
        cls.app.register_blueprint(criacao_bp)
        with cls.app.app_context():
            db.create_all()

    @classmethod
    def tearDownClass(cls) -> None:
        with cls.app.app_context():
            db.drop_all()

    def setUp(self) -> None:
        self.app_ctx = self.app.app_context()
        self.app_ctx.push()
        db.session.query(Funcionario).delete()
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        db.session.remove()
        self.app_ctx.pop()

    def test_servidor_payload_invalido_bloqueia_cadastro(self) -> None:
        payload = _payload_base()
        payload["tipo"] = "TIPO_INVALIDO"

        admin_fake = SimpleNamespace(is_admin=True, is_authenticated=True, id=1, login="admin")

        with patch("routes.criacao.current_user", admin_fake),\
             patch("routes.criacao.preencher_campos_comuns"),\
             patch("routes.criacao.registrar_evento_seguro") as audit_mock:
            resp = self.client.post("/funcionario/novo/servidor", data=payload, follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Funcionario.query.count(), 0)

        acao = audit_mock.call_args[0][0]
        detalhes = audit_mock.call_args.kwargs["detalhes"]

        self.assertEqual(acao, "FUNCIONARIO_CADASTRAR_SERVIDOR_FALHA")
        self.assertEqual(detalhes["motivo"], "validacao_allowlist_cadastro")
        self.assertEqual(detalhes["campo"], "tipo")
        self.assertEqual(detalhes["valor"], "TIPO_INVALIDO")

    def test_terceirizado_payload_invalido_bloqueia_cadastro(self) -> None:
        payload = _payload_base()
        payload["situacao"] = "SITUACAO_INVALIDA"

        admin_fake = SimpleNamespace(is_admin=True, is_authenticated=True, id=1, login="admin")

        with patch("routes.criacao.current_user", admin_fake), \
            patch("routes.criacao.preencher_campos_comuns"), \
            patch("routes.criacao.registrar_evento_seguro") as audit_mock:
            resp = self.client.post("/funcionario/novo/terceirizado", data=payload, follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Funcionario.query.count(), 0)

        acao = audit_mock.call_args.args[0]
        detalhes = audit_mock.call_args.kwargs["detalhes"]

        self.assertEqual(acao, "FUNCIONARIO_CADASTRAR_TERCEIRIZADO_FALHA")
        self.assertEqual(detalhes["motivo"], "validacao_allowlist_cadastro")
        self.assertEqual(detalhes["campo"], "situacao")
        self.assertEqual(detalhes["valor"], "SITUACAO_INVALIDA")

    def test_servidor_payload_valido_cadastra(self) -> None:
        payload = _payload_base()
        admin_fake = SimpleNamespace(is_admin=True, is_authenticated=True, id=1, login="admin")

        with patch("routes.criacao.current_user", admin_fake), \
            patch("routes.criacao.preencher_campos_comuns", side_effect=_preencher_servidor_minimo), \
            patch("routes.criacao.salvar_foto"), \
            patch("routes.criacao.reindexar_funcionario"), \
            patch("routes.criacao.registrar_evento_seguro") as audit_mock:
            resp = self.client.post("/funcionario/novo/servidor", data=payload, follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Funcionario.query.count(), 1)
        self.assertEqual(Funcionario.query.first().vinculo, "SERVIDOR")
        self.assertEqual(audit_mock.call_args.args[0], "FUNCIONARIO_CADASTRAR_SERVIDOR_SUCESSO")

    def test_terceirizado_payload_valido_cadastra(self) -> None:
        payload = _payload_base()
        admin_fake = SimpleNamespace(is_admin=True, is_authenticated=True, id=1, login="admin")

        with patch("routes.criacao.current_user", admin_fake), \
            patch("routes.criacao.preencher_campos_comuns", side_effect=_preencher_terceirizado_minimo), \
            patch("routes.criacao.salvar_foto"), \
            patch("routes.criacao.reindexar_funcionario"), \
            patch("routes.criacao.registrar_evento_seguro") as audit_mock:
            resp = self.client.post("/funcionario/novo/terceirizado", data=payload, follow_redirects=False)

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Funcionario.query.count(), 1)
        self.assertEqual(Funcionario.query.first().vinculo, "TERCEIRIZADO")
        self.assertEqual(audit_mock.call_args.args[0], "FUNCIONARIO_CADASTRAR_TERCEIRIZADO_SUCESSO")

if __name__ == "__main__":
    unittest.main()
