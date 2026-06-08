from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask

from core.extensions import db
from models import LogAuditoria, Usuario
from routes.usuarios import usuario_bp


class TestUsuariosExcluir(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        cls.app = Flask(__name__, template_folder=str(repo_root / "templates"))
        cls.app.config.update(
            SECRET_KEY="test-secret",
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            LOGIN_DISABLED=True,
        )
        cls.app.jinja_env.globals["csrf_token"] = lambda: ""

        db.init_app(cls.app)
        cls.app.add_url_rule("/painel", endpoint="painel", view_func=lambda: "painel teste")
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

        db.session.query(LogAuditoria).delete()
        db.session.query(Usuario).delete()
        db.session.commit()

        alvo = Usuario(
            login="admin_teste",
            perfil="CO.9",
            is_admin=True,
            is_superadmin=False,
        )
        alvo.set_password("SenhaInicial123!")
        db.session.add(alvo)
        db.session.commit()

        log = LogAuditoria(
            usuario_id=alvo.id,
            usuario_login=alvo.login,
            acao="USUARIO_TESTE",
            categoria="administracao",
            status="sucesso",
            recurso="usuario",
            recurso_id=str(alvo.id),
        )
        db.session.add(log)
        db.session.commit()

        self.alvo_id = alvo.id
        self.log_id = log.id
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        db.session.remove()
        self.app_ctx.pop()

    @staticmethod
    def _superadmin_fake():
        return SimpleNamespace(
            is_authenticated=True,
            is_superadmin=True,
            is_admin=True,
            id=999,
            login="superadmin_teste",
        )

    def test_excluir_admin_desvincula_logs_e_remove_usuario(self) -> None:
        with patch("routes.usuarios.current_user", self._superadmin_fake()), \
             patch("core.authz.current_user", self._superadmin_fake()), \
             patch("routes.usuarios.registrar_evento_seguro"):
            resp = self.client.post(
                f"/usuarios/{self.alvo_id}/excluir",
                data={},
                follow_redirects=False,
            )

        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.headers["Location"].endswith("/usuarios"))

        usuario = db.session.get(Usuario, self.alvo_id)
        self.assertIsNone(usuario)

        log = db.session.get(LogAuditoria, self.log_id)
        self.assertIsNotNone(log)
        self.assertIsNone(log.usuario_id)
        self.assertEqual(log.usuario_login, "admin_teste")


if __name__ == "__main__":
    unittest.main()
