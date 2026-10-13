"""Apps locais: só o próprio PC (Host/Origin), ids e datas sem caminho, uploads limitados."""
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from leonida import localguard, post

try:
    from fastapi.testclient import TestClient
    with patch("leonida.gallery.build"):
        from leonida import server
    from apps.gameplay import app as cuts
    from apps.noticias import app as news
except ImportError:
    TestClient = None


class GuardRules(unittest.TestCase):
    def test_hosts(self):
        for host in ("127.0.0.1:8768", "localhost:8769", "[::1]:8768", "localhost"):
            self.assertIsNone(localguard.rejection("GET", {"host": host}), host)
        for host in ("evil.example:8768", "", "127.0.0.1.evil.example", "testserver"):
            self.assertIsNotNone(localguard.rejection("GET", {"host": host}), host)

    def test_origins_on_writes(self):
        local = {"host": "127.0.0.1:8768"}
        self.assertIsNone(localguard.rejection("POST", {**local, "origin": "http://127.0.0.1:8768"}))
        self.assertIsNone(localguard.rejection("POST", {**local, "origin": "http://localhost:8768"}))
        self.assertIsNone(localguard.rejection("POST", local))   # curl / scripts locais
        for origin in ("https://evil.example", "null", "http://127.0.0.1.evil.example"):
            self.assertIsNotNone(localguard.rejection("POST", {**local, "origin": origin}), origin)
        self.assertIsNotNone(localguard.rejection("PUT", {**local, "sec-fetch-site": "cross-site"}))
        self.assertIsNone(localguard.rejection("GET", {**local, "origin": "https://evil.example"}))

    def test_extra_hosts_from_environment(self):
        with patch.dict("os.environ", {"LEONIDA_ALLOWED_HOSTS": "meupc.lan"}):
            self.assertIsNone(localguard.rejection("GET", {"host": "meupc.lan:8768"}))


class PostPaths(unittest.TestCase):
    def test_ids_and_dates_cannot_become_paths(self):
        for bad in ("../x", "a/b", "..", "", "a\\b", ".hidden", "x" * 200, None):
            with self.assertRaises(ValueError):
                post.check_id(bad)
        self.assertEqual(post.check_id("2026-10-11-gta6-mission-freedom-us-capa-v2"), "2026-10-11-gta6-mission-freedom-us-capa-v2")
        for bad in ("../../../tmp/pwn", "2026-13-01", "2026-10-1", "hoje", None):
            with self.assertRaises(ValueError):
                post.check_date(bad)
        with self.assertRaises(ValueError):
            post.new("titulo", "../../../tmp/pwn")
        with self.assertRaises(ValueError):
            post.save({"id": "../fora", "date": "2026-10-13"})
        with self.assertRaises(ValueError):
            post.save({"id": "ok-id", "date": "../../fora"})


@unittest.skipIf(TestClient is None, "FastAPI/httpx não disponível")
class ServerSecurity(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.posts = Path(self.temp.name) / "posts"
        (self.posts / "p1").mkdir(parents=True)
        (self.posts / "p1" / "post.yaml").write_text("id: p1\ndate: '2026-10-13'\n", encoding="utf-8")
        for target in (server, post):
            active = patch.object(target, "POSTS_DIR", self.posts)
            active.start()
            self.addCleanup(active.stop)
        self.client = TestClient(server.app, base_url="http://127.0.0.1")
        self.addCleanup(self.client.close)

    def png(self):
        buf = io.BytesIO()
        Image.new("RGB", (4, 4), "red").save(buf, "PNG")
        return buf.getvalue()

    def test_foreign_host_and_origin_are_refused_in_every_app(self):
        for app in (server.app, news.app, cuts.app):
            with TestClient(app, base_url="http://evil.example:8768") as foreign:
                self.assertEqual(foreign.get("/api/status").status_code, 403)
            with TestClient(app, base_url="http://127.0.0.1") as local:
                response = local.post("/api/jobs/x", headers={"Origin": "https://evil.example"})
                self.assertEqual(response.status_code, 403)

    def test_cross_site_upload_never_reaches_the_disk(self):
        response = self.client.post("/api/posts/p1/upload", headers={"Origin": "https://evil.example"},
                                    files={"file": ("a.png", self.png(), "image/png")})
        self.assertEqual(response.status_code, 403)
        self.assertFalse((self.posts / "p1" / "imagem.png").exists())

    def test_upload_checks_extension_size_and_content(self):
        ok = self.client.post("/api/posts/p1/upload", files={"file": ("a.png", self.png(), "image/png")})
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertTrue((self.posts / "p1" / "imagem.png").is_file())
        self.assertEqual(self.client.post("/api/posts/p1/upload",
                                          files={"file": ("a.html", b"<script>", "text/html")}).status_code, 400)
        self.assertEqual(self.client.post("/api/posts/p1/upload",
                                          files={"file": ("a.jpg", b"not an image", "image/jpeg")}).status_code, 400)
        with patch.object(server, "MAX_IMAGE_BYTES", 10):
            self.assertEqual(self.client.post("/api/posts/p1/upload",
                                              files={"file": ("a.png", self.png(), "image/png")}).status_code, 413)
        self.assertEqual(self.client.post("/api/posts/nao-existe/upload",
                                          files={"file": ("a.png", self.png(), "image/png")}).status_code, 404)
        self.assertEqual([p.name for p in (self.posts / "p1").iterdir() if p.name.startswith(".upload")], [])

    def test_bad_ids_and_dates_are_rejected(self):
        self.assertEqual(self.client.post("/api/posts/new", json={"title": "x", "date": "../../../tmp/pwn"}).status_code, 400)
        self.assertEqual(self.client.put("/api/posts/p1", json={"date": "../../x"}).status_code, 400)
        self.assertEqual(self.client.post("/api/posts/..%2E/build").status_code in (400, 404), True)
        self.assertEqual(self.client.post("/api/posts/.hidden/build").status_code, 400)

    def test_thumb_never_reads_files_outside_the_project(self):
        outside = Path(self.temp.name) / "secret.png"
        outside.write_bytes(self.png())
        for ref in (str(outside), "../secret.png", "C:/Windows/win.ini", "leonida/server.py", "posts/../../x.png"):
            self.assertEqual(self.client.get("/api/thumb", params={"url": ref}).status_code, 400, ref)
        image = self.posts / "p1" / "imagem.png"
        image.write_bytes(self.png())
        with patch.object(server, "ROOT", Path(self.temp.name)):
            self.assertEqual(self.client.get("/api/thumb", params={"url": "posts/p1/imagem.png"}).status_code, 200)


if __name__ == "__main__":
    unittest.main()
