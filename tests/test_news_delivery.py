"""Entrega do MP4 final no editor de Notícias, sem renderização ou rede externa."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from fastapi.testclient import TestClient
    with patch("leonida.gallery.build"):
        from apps.noticias import app as news
    from leonida import post, server
except ImportError:
    TestClient = None


@unittest.skipIf(TestClient is None, "FastAPI/httpx não disponível")
class NewsDeliveryTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.posts = self.root / "posts"
        self.output = self.root / "prontos"
        self.posts.mkdir()
        self.output.mkdir()
        self.pid = "2026-10-12-noticia-fixture"
        self.folder = self.output / "2026-10-12" / self.pid
        for active in (patch.object(server, "POSTS_DIR", self.posts),
                       patch.object(server, "OUT_DIR", self.output),
                       patch.object(post, "POSTS_DIR", self.posts)):
            active.start()
            self.addCleanup(active.stop)
        self.client = TestClient(news.app)
        self.addCleanup(self.client.close)
        self.write_post()

    def write_post(self, date="2026-10-12"):
        source = self.posts / self.pid
        source.mkdir(exist_ok=True)
        (source / "post.yaml").write_text(
            f'id: {self.pid}\ndate: "{date}"\n', encoding="utf-8")

    def write_asset(self, relative, content=b"fixture"):
        path = self.folder / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def write_manifest(self, files=None):
        manifest = {"id": self.pid, "date": "2026-10-12", "files": files or {}}
        self.write_asset("post.json", json.dumps(manifest).encode("utf-8"))

    def get_delivery(self):
        return self.client.get(f"/api/posts/{self.pid}/delivery")

    def test_news_editor_exposes_existing_pt_and_en_videos_with_support_files(self):
        for sub, cover, caption in (("br", "01_capa.png", "legenda.txt"),
                                    ("us", "01_cover.png", "caption.txt")):
            self.write_asset(f"{sub}/tiktok/post.mp4")
            self.write_asset(f"{sub}/{cover}")
            self.write_asset(f"{sub}/{caption}")
        self.write_manifest({"br": ["tiktok/post.mp4"], "us": ["tiktok/post.mp4"]})
        response = self.get_delivery()
        self.assertEqual(response.status_code, 200)
        prefix = f"/prontos/2026-10-12/{self.pid}"
        self.assertEqual(response.json(), {"id": self.pid, "videos": [
            {"lang": "pt", "video_url": f"{prefix}/br/tiktok/post.mp4",
             "cover_url": f"{prefix}/br/01_capa.png", "caption_url": f"{prefix}/br/legenda.txt"},
            {"lang": "en", "video_url": f"{prefix}/us/tiktok/post.mp4",
             "cover_url": f"{prefix}/us/01_cover.png", "caption_url": f"{prefix}/us/caption.txt"},
        ]})

    def test_final_edit_has_priority_over_legacy_animated_cover(self):
        self.write_asset("br/video.mp4", b"old animated cover")
        self.write_asset("br/tiktok/post.mp4", b"final edit")
        # Older manifests may declare only the former cover video.
        self.write_manifest({"br": ["video.mp4"]})
        response = self.get_delivery()
        self.assertEqual(response.status_code, 200)
        videos = response.json()["videos"]
        self.assertEqual(len(videos), 1)
        self.assertTrue(videos[0]["video_url"].endswith("/br/tiktok/post.mp4"))

    def test_legacy_video_is_available_when_no_final_edit_exists(self):
        self.write_asset("br/video.mp4")
        self.write_manifest({"br": ["video.mp4"]})
        response = self.get_delivery()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["videos"], [{
            "lang": "pt", "video_url": f"/prontos/2026-10-12/{self.pid}/br/video.mp4",
        }])

    def test_pending_post_without_manifest_has_no_completed_video(self):
        self.write_asset("br/tiktok/post.mp4", b"partially written")
        response = self.get_delivery()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"id": self.pid, "videos": []})

    def test_reading_delivery_does_not_queue_a_render_or_change_the_video(self):
        video = self.write_asset("br/tiktok/post.mp4", b"existing complete video")
        self.write_manifest({"br": ["tiktok/post.mp4"]})
        previous = (video.read_bytes(), video.stat().st_mtime_ns)
        with patch.object(server, "_job") as worker, patch.object(post, "build") as renderer:
            response = self.get_delivery()
        self.assertEqual(response.status_code, 200)
        worker.assert_not_called()
        renderer.assert_not_called()
        self.assertEqual((video.read_bytes(), video.stat().st_mtime_ns), previous)

    def test_missing_declared_videos_do_not_appear_as_downloads(self):
        self.write_asset("br/01_capa.png")
        self.write_manifest({"br": ["missing.mp4", "tiktok/post.mp4"], "us": ["missing.mp4"]})
        response = self.get_delivery()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["videos"], [])

    def test_manifest_paths_cannot_expose_files_outside_the_language_folder(self):
        external = self.root / "outside.mp4"
        external.write_bytes(b"private fixture")
        sibling = self.folder / "outside.mp4"
        sibling.parent.mkdir(parents=True, exist_ok=True)
        sibling.write_bytes(b"another language or private asset")
        self.write_asset("br/01_capa.png")
        self.write_manifest({"br": [str(external), "../outside.mp4", "../../../../outside.mp4"]})
        response = self.get_delivery()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["videos"], [])

    def test_invalid_and_unknown_post_ids_are_rejected(self):
        self.assertEqual(self.client.get("/api/posts/bad.id/delivery").status_code, 400)
        self.assertEqual(self.client.get("/api/posts/bad%20id/delivery").status_code, 400)
        self.assertEqual(self.client.get("/api/posts/not-found/delivery").status_code, 404)

    def test_invalid_post_date_cannot_select_an_output_directory(self):
        self.write_post("../../outside")
        response = self.get_delivery()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "data do post inválida")

    def test_corrupt_manifest_reports_unavailable_delivery(self):
        for content in (b"{incomplete", b"[]", b"null"):
            with self.subTest(content=content):
                self.write_asset("post.json", content)
                self.assertEqual(self.get_delivery().status_code, 409)

    def test_wrong_manifest_file_collection_type_does_not_break_delivery(self):
        self.write_asset("br/tiktok/post.mp4")
        for files in (["legacy.mp4"], "legacy.mp4", {"br": "legacy.mp4"}):
            with self.subTest(files=files):
                self.write_manifest(files)
                response = self.get_delivery()
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.json()["videos"][0]["video_url"].endswith("/br/tiktok/post.mp4"))


if __name__ == "__main__":
    unittest.main()
