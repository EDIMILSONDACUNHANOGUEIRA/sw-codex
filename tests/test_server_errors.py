"""Servidor: post.yaml ruim não derruba a lista; erros previsíveis voltam como 4xx com JSON."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from leonida import post

try:
    from fastapi.testclient import TestClient
    with patch("leonida.gallery.build"):
        from leonida import server
    from apps.noticias import app as news
except ImportError:
    TestClient = None


@unittest.skipIf(TestClient is None, "FastAPI/httpx não disponível")
class ServerErrors(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.posts = Path(self.temp.name) / "posts"
        files = {"ok": "id: ok\ndate: '2026-10-13'\npt: {headline: Tudo certo}\n",
                 "sintaxe": "id: [quebrado\n",
                 "lista": "- a\n- b\n",
                 "pt-texto": "id: pt-texto\ndate: '2026-10-13'\npt: só texto\n",
                 "id-ruim": "id: ../fora\ndate: '2026-10-13'\n"}
        for name, content in files.items():
            (self.posts / name).mkdir(parents=True)
            (self.posts / name / "post.yaml").write_text(content, encoding="utf-8")
        for target in (server, post):
            active = patch.object(target, "POSTS_DIR", self.posts)
            active.start()
            self.addCleanup(active.stop)

    def test_broken_posts_are_listed_with_error_and_others_survive(self):
        for app in (server.app, news.app):
            with TestClient(app, base_url="http://127.0.0.1") as client:
                response = client.get("/api/posts")
                self.assertEqual(response.status_code, 200)
                items = {i["id"]: i for i in response.json()}
                self.assertEqual(items["ok"]["headline"], "Tudo certo")
                self.assertNotIn("error", items["ok"])
                self.assertNotIn("error", items["pt-texto"])
                for broken in ("sintaxe", "lista", "id-ruim"):
                    self.assertIn("inválido", items[broken]["error"], broken)

    def test_predictable_errors_are_json_4xx(self):
        for app in (server.app, news.app):
            with TestClient(app, base_url="http://127.0.0.1", raise_server_exceptions=False) as client:
                broken = client.get("/api/posts/sintaxe")
                self.assertEqual(broken.status_code, 400)
                self.assertIn("detail", broken.json())
                listed = client.get("/api/posts/lista")
                self.assertEqual(listed.status_code, 400)
                self.assertIn("inválido", listed.json()["detail"])
                missing = client.post("/api/posts/ok/preview")
                self.assertEqual(missing.status_code, 400)
                self.assertIn("detail", missing.json())
        with TestClient(server.app, base_url="http://127.0.0.1", raise_server_exceptions=False) as client:
            clip = client.post("/api/clips", json={"src": "x"})
            self.assertEqual(clip.status_code, 400)
            self.assertIn("campo obrigatório", clip.json()["detail"])


if __name__ == "__main__":
    unittest.main()
