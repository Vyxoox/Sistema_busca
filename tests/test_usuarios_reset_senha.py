from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask

from core.extensions import db
from models import Usuario
from routes.usuarios import usuario_bp


class TestUsuariosResetSenha(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        cls.app = Flask(__name__, template_folder=str(repo_root / "templates"))
        cls.app.jinja_env.globals["csrf_token"] = lambda: ""
        cls.app.config.update(
            SECRET_KEY="test-secret",
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            LOGIN_DISABLED=True,
        )
        db.init_app(cls.app)
        cls.app.register_blueprint(usuario_bp)

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

        db.session.query(Usuario).delete()
        db.session.commit()

        alvo = Usuario(
            login="admin_alvo",
            perfil="CA.9",
            is_admin=True,
            is_superadmin=False,
        )
        alvo.set_password("SenhaInicial123")
        db.session.add(alvo)
        db.session.commit()

        self.alvo_id = alvo.id
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        db.session.remove()
        self.app_ctx.pop()

    def _superadmin_fake(self):
        return SimpleNamespace(
            is_authenticated=True,
            is_superadmin=True,
            id=999,
            login="superadmin_teste",
        )

    def test_get_tela_reset(self) -> None:
        with patch("core.authz.current_user", self._superadmin_fake()):
            resp = self.client.get(f"/usuarios/{self.alvo_id}/reset-senha")

        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Reset de Senha", resp.data)

    def test_post_falha_confirmacao_nao_altera_senha(self) -> None:
        with patch("core.authz.current_user", self._superadmin_fake()), \
             patch("routes.usuarios.registrar_evento_seguro") as audit_mock:
            resp = self.client.post(
                f"/usuarios/{self.alvo_id}/reset-senha",
                data={
                    "password": "NovaSenha123!",
                    "confirm_password": "Diferente123!",
                },
                follow_redirects=False,
            )

        self.assertEqual(resp.status_code, 302)

        alvo = db.session.get(Usuario, self.alvo_id)
        self.assertTrue(alvo.check_password("SenhaInicial123"))

        self.assertEqual(audit_mock.call_count, 1)
        self.assertEqual(audit_mock.call_args.args[0], "USUARIO_RESET_SENHA_FALHA")
        detalhes = audit_mock.call_args.kwargs["detalhes"]
        self.assertEqual(detalhes["motivo"], "senha_confirmacao_diferente")
        self.assertEqual(detalhes["usuario_alvo"], "admin_alvo")

    def test_post_sucesso_altera_senha(self) -> None:
        with patch("core.authz.current_user", self._superadmin_fake()), \
             patch("routes.usuarios.registrar_evento_seguro") as audit_mock:
            resp = self.client.post(
                f"/usuarios/{self.alvo_id}/reset-senha",
                data={
                    "password": "NovaSenha123!",
                    "confirm_password": "NovaSenha123!",
                },
                follow_redirects=False,
            )

        self.assertEqual(resp.status_code, 302)

        alvo = db.session.get(Usuario, self.alvo_id)
        self.assertTrue(alvo.check_password("NovaSenha123!"))
        self.assertFalse(alvo.check_password("SenhaInicial123"))

        self.assertEqual(audit_mock.call_count, 1)
        self.assertEqual(audit_mock.call_args.args[0], "USUARIO_RESET_SENHA_SUCESSO")
        detalhes = audit_mock.call_args.kwargs["detalhes"]
        self.assertEqual(detalhes["usuario_alvo"], "admin_alvo")


if __name__ == "__main__":
    unittest.main()
