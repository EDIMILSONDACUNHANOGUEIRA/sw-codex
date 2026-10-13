"""Entrega MP4 em subpastas: galeria, compatibilidade e caminhos locais."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from leonida import gallery


class GalleryDeliveryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / "prontos"
        self.folder = self.output / "2026-10-12" / "noticia"
        self.br = self.folder / "br"
        (self.br / "tiktok").mkdir(parents=True)
        self.manifest = {"id": "noticia", "date": "2026-10-12", "files": {"br": [
            "01_capa.png", "legenda.txt", "tiktok/post.mp4"]}}

    def write(self, ref, content=b"fixture"):
        path = self.br / ref
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path.resolve()

    def build_page(self):
        (self.folder / "post.json").write_text(json.dumps(self.manifest), encoding="utf-8")
        with patch.object(gallery, "OUT_DIR", self.output):
            return Path(gallery.build()).read_text(encoding="utf-8")

    def test_nested_publication_video_is_visible_before_images(self):
        self.write("tiktok/post.mp4")
        self.write("01_capa.png")
        self.write("legenda.txt", "Legenda da publicação".encode("utf-8"))
        page = self.build_page()
        url = "2026-10-12/noticia/br/tiktok/post.mp4"
        self.assertIn(f'<video src="{url}" controls', page)
        self.assertIn(f'href="{url}" download>Baixar MP4</a>', page)
        self.assertLess(page.index("Vídeo completo pronto"), page.index('<div class="strip">'))
        self.assertEqual(page.count(f'<video src="{url}"'), 1)
        self.assertIn("Legenda da publicação", page)

    def test_root_videos_still_display_but_final_has_priority(self):
        final = self.write("tiktok/post.mp4")
        intro = self.write("video.mp4")
        self.assertEqual(gallery.video_files(self.folder, self.manifest, "br"), [final, intro])
        page = self.build_page()
        self.assertLess(page.index('src="2026-10-12/noticia/br/tiktok/post.mp4"'),
                        page.index('src="2026-10-12/noticia/br/video.mp4"'))

    def test_legacy_root_export_remains_available(self):
        video = self.write("video.mp4")
        self.assertEqual(gallery.video_files(self.folder, self.manifest, "br"), [video])
        result = gallery.delivery(self.folder, self.manifest, self.output)
        self.assertEqual(result, [{"lang": "pt", "video_url": "/prontos/2026-10-12/noticia/br/video.mp4"}])

    def test_missing_video_does_not_produce_broken_links(self):
        self.write("01_capa.png")
        self.assertEqual(gallery.delivery(self.folder, self.manifest, self.output), [])
        page = self.build_page()
        self.assertNotIn("<video ", page)
        self.assertNotIn("Baixar MP4", page)

    def test_duplicates_and_outside_paths_are_ignored(self):
        final = self.write("tiktok/post.mp4")
        outside = self.root / "private.mp4"
        outside.write_bytes(b"private")
        self.manifest["files"]["br"] += ["tiktok/post.mp4", "./tiktok/post.mp4",
                                            str(outside), "../../../private.mp4", "missing.mp4", "01_capa.png"]
        self.assertEqual(gallery.video_files(self.folder, self.manifest, "br"), [final])
        self.assertEqual(gallery.delivery(self.root, self.manifest, self.output), [])

    def test_both_profiles_have_their_own_downloads(self):
        self.write("tiktok/post.mp4")
        self.write("01_capa.png")
        self.write("legenda.txt")
        us = self.folder / "us"
        (us / "tiktok").mkdir(parents=True)
        (us / "tiktok/post.mp4").write_bytes(b"fixture")
        (us / "01_cover.png").write_bytes(b"fixture")
        (us / "caption.txt").write_bytes(b"fixture")
        result = gallery.delivery(self.folder, self.manifest, self.output)
        self.assertEqual([entry["lang"] for entry in result], ["pt", "en"])
        self.assertTrue(result[0]["cover_url"].endswith("br/01_capa.png"))
        self.assertTrue(result[1]["caption_url"].endswith("us/caption.txt"))

    def test_manifest_video_names_are_url_encoded(self):
        self.write("outra pasta/final #1.mp4")
        self.manifest["files"]["br"] = ["outra pasta/final #1.mp4"]
        result = gallery.delivery(self.folder, self.manifest, self.output)
        self.assertTrue(result[0]["video_url"].endswith("outra%20pasta/final%20%231.mp4"))
        page = self.build_page()
        self.assertIn("outra%20pasta/final%20%231.mp4", page)

    def test_malformed_manifest_file_list_does_not_hide_existing_final(self):
        final = self.write("tiktok/post.mp4")
        for files in (None, [], {"br": "bad"}, {"br": None}):
            self.assertEqual(gallery.video_files(self.folder, {"files": files}, "br"), [final])


if __name__ == "__main__":
    unittest.main()
