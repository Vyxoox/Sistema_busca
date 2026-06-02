from __future__ import annotations

import unittest
import json

from services.auditoria_services import _serializar_detalhes

class TestAuditoriaMascaramento(unittest.TestCase):
    def test_chave_sensivel_password(self) -> None:
        bruto = _serializar_detalhes({"password": "abc123", "acao": "teste"})
        self.assertIsNotNone(bruto)
        obj = json.loads(bruto)
        self.assertEqual(obj["password"], "****")
        self.assertNotIn("abc123", bruto)

    def test_cpf_em_texto_livre(self) ->  None:
        bruto = _serializar_detalhes({"mensagem": "CPF informado 123.456.789-00 no cadastro"})
        self.assertIsNotNone(bruto)
        self.assertNotIn("123.456.789-00", bruto)
        self.assertIn("[cpf_mascarado]", bruto)

    def test_email_em_texto_livre(self) -> None:
        bruto = _serializar_detalhes({"mensagem": "Contato: joao.silva@orgao.gov.br"})
        self.assertIsNotNone(bruto)
        self.assertNotIn("joao.silva@orgao.gov.br", bruto)
        self.assertIn("[email_mascarado]", bruto)

    def test_telefone_em_texto_livre(self) -> None:
        bruto = _serializar_detalhes({"mensagem": "Telefone (11) 98765-4321"})
        self.assertIsNotNone(bruto)
        self.assertNotIn("98765-4321", bruto)
        self.assertIn("[telefone_mascarado]", bruto)

    def test_contexto_ids_nao_mascarar(self) -> None:
        req = "da7475aef3e17f095f47341b"
        sess = "e62f11a1d7444b33aca3a9fb30e4e0fd"
        bruto = _serializar_detalhes({
            "request_id": req,
            "correlation_id": req,
            "session_id": sess,
            "timestamp_utc": "2026-04-17T12:41:30.815905+00:00",
        })
        obj = json.loads(bruto)
        self.assertEqual(obj["request_id"], req)
        self.assertEqual(obj["correlation_id"], req)
        self.assertEqual(obj["session_id"], sess)

    def test_numero_solto_nao_telefone(self) -> None:
        bruto = _serializar_detalhes({"mensagem": "trace 12345678"})
        self.assertIn("12345678", bruto)

if __name__ == "__main__":
        unittest.main()
