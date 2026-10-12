"""Versões revisadas locais são descobertas sem importar projetos manualmente."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from fastapi.testclient import TestClient
    from apps.gameplay import app as cuts
except ImportError:
    TestClient = None


@unittest.skipIf(TestClient is None, "FastAPI/httpx não disponível")
class GameplayRevisionsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / "cortes"
        self.revisions = self.home / "revisoes"
        self.revisions.mkdir(parents=True)
        active = patch.object(cuts, "HOME", self.home)
        active.start()
        self.addCleanup(active.stop)
        self.client = TestClient(cuts.app)
        self.addCleanup(self.client.close)

    def revision(self, name, **metadata):
        folder = self.revisions / name
        folder.mkdir()
        (folder / "video.mp4").write_bytes(b"fixture")
        (folder / "validacao.json").write_text(json.dumps(metadata), encoding="utf-8")
        return folder

    def test_completed_revision_has_quoted_local_downloads(self):
        folder = self.revision("2026-10-12 vídeo #3", title="A fuga", duration=37.1, width=1080, height=1920,
                               source_path="private path should not be listed")
        for name in ("capa.jpg", "legendas.srt", "legenda-publicacao.txt"):
            (folder / name).write_bytes(b"fixture")
        response = self.client.get("/api/gameplay/revisions")
        self.assertEqual(response.status_code, 200)
        item, = response.json()
        prefix = "/gameplay-files/revisoes/2026-10-12%20v%C3%ADdeo%20%233/"
        self.assertEqual(item["video_url"], prefix + "video.mp4")
        self.assertEqual(item["cover_url"], prefix + "capa.jpg")
        self.assertEqual(item["subtitles_url"], prefix + "legendas.srt")
        self.assertEqual(item["caption_url"], prefix + "legenda-publicacao.txt")
        self.assertEqual(item["title"], "A fuga")
        self.assertEqual(item["duration"], 37.1)
        self.assertNotIn("source_path", item)

    def test_only_ready_direct_children_are_listed_newest_first(self):
        self.revision("2026-10-11-ready")
        self.revision("2026-10-12-ready")
        unfinished = self.revision("2026-10-13-incomplete")
        (unfinished / "video.mp4").unlink()
        malformed = self.revision("2026-10-14-malformed")
        (malformed / "validacao.json").write_text("not json", encoding="utf-8")
        nested = self.revisions / "nested"
        nested.mkdir()
        (nested / "child").mkdir()
        (nested / "child" / "video.mp4").write_bytes(b"fixture")
        (nested / "child" / "validacao.json").write_text("{}", encoding="utf-8")
        outside = self.home / "news"
        outside.mkdir()
        (outside / "video.mp4").write_bytes(b"fixture")
        (outside / "validacao.json").write_text("{}", encoding="utf-8")
        items = self.client.get("/api/gameplay/revisions").json()
        self.assertEqual([item["id"] for item in items], ["2026-10-12-ready", "2026-10-11-ready"])
        self.assertEqual(items[0]["title"], "2026-10-12-ready")
        self.assertNotIn("cover_url", items[0])

    def test_non_object_metadata_is_skipped_and_invalid_dimensions_omitted(self):
        folder = self.revision("broken")
        (folder / "validacao.json").write_text("[]", encoding="utf-8")
        self.revision("ready", duration="oops", width=True, height=-1)
        item, = self.client.get("/api/gameplay/revisions").json()
        self.assertEqual(item["id"], "ready")
        self.assertTrue(all(field not in item for field in ("duration", "width", "height")))

    def test_asset_symlinks_cannot_reference_another_directory(self):
        folder = self.revision("ready")
        outside = self.home / "outside.jpg"
        outside.write_bytes(b"private fixture")
        try:
            os.symlink(outside, folder / "capa.jpg")
        except (OSError, NotImplementedError):
            self.skipTest("Criação de links simbólicos indisponível neste computador")
        item, = self.client.get("/api/gameplay/revisions").json()
        self.assertNotIn("cover_url", item)


if __name__ == "__main__":
    unittest.main()
