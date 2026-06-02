from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret")

from app import app


class TestHealthEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        app.config.update(TESTING=True)

    def setUp(self) -> None:
        self.client = app.test_client()

    def test_healthz_ok(self) -> None:
        resp = self.client.get("/healthz")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["status"], "ok")

    def test_readyz_ok(self) -> None:
        resp = self.client.get("/readyz")
        data = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(data["status"], "ready")
        self.assertEqual(data["database"], "ok")
        self.assertEqual(data["indice"], "ok")

    def test_readyz_db_erro(self) -> None:
        with patch("app.db.session.execute", side_effect=Exception("db indisponivel")):
            resp = self.client.get("/readyz")
        data = resp.get_json()
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(data["status"], "not_ready")
        self.assertEqual(data["database"], "erro")
