from __future__ import annotations

import unittest

from routes.criacao import (
    _validar_selects_cadastro,
    OPCOES_SUBTIPO_VINCULO,
    OPCOES_LOTACAO,
    OPCOES_AREA,
    OPCOES_COORDENADORIA,
    OPCOES_TIPO,
    OPCOES_FORMA_INGRESSO,
    OPCOES_SITUACAO,
)


def _form_base() -> dict[str, str]:
    return {
        "subtipo_vinculo": OPCOES_SUBTIPO_VINCULO[0],
        "lotacao": OPCOES_LOTACAO[0],
        "area": OPCOES_AREA[0],
        "coordenadoria": OPCOES_COORDENADORIA[0],
        "tipo": OPCOES_TIPO[0],
        "forma_ingresso": OPCOES_FORMA_INGRESSO[0],
        "situacao": OPCOES_SITUACAO[0],
    }


class TestCriacaoAllowlist(unittest.TestCase):
    def test_form_valido(self) -> None:
        campo, erro = _validar_selects_cadastro(_form_base())
        self.assertIsNone(campo)
        self.assertIsNone(erro)

    def test_situacao_invalida(self) -> None:
        form = _form_base()
        form["situacao"] = "VALOR_INVALIDO"
        campo, erro = _validar_selects_cadastro(form)
        self.assertEqual(campo, "situacao")
        self.assertIn("Situacao", erro)

    def test_subtipo_obrigatorio(self) -> None:
        form = _form_base()
        form["subtipo_vinculo"] = ""
        campo, erro = _validar_selects_cadastro(form)
        self.assertEqual(campo, "subtipo_vinculo")
        self.assertIn("Subtipo", erro)

    def test_case_insensitive(self) -> None:
        form = _form_base()
        form["tipo"] = OPCOES_TIPO[0].lower()
        campo, erro = _validar_selects_cadastro(form)
        self.assertIsNone(campo)
        self.assertIsNone(erro)


if __name__ == "__main__":
    unittest.main()
