"""Build completo: prioridade de estilo, manifesto e preservação de entregas."""
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from leonida import motion, post, postvideo, render


class PostV2Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = {"id": "fixture", "date": "2026-10-11", "image": "fixture.jpg",
                     "tag": "oficial", "foto_limpa": False,
                     "pt": {"headline": "Teste de *composição*", "caption": "Texto fictício."}}
        bg = Image.new("RGBA", (32, 48), "#352245")
        self.scene = render.Render(bg.convert("RGB"), [render.Layer("bg", bg)], {"kind": "cover"})
        self.out = self.root / "2026-10-11" / "fixture"
        (self.out / "br" / "tiktok").mkdir(parents=True)
        self.old = self.out / "br" / "tiktok" / "post.mp4"
        self.old.write_bytes(b"previous valid delivery")
        (self.out / "br" / "legenda.txt").write_text("Legenda anterior", encoding="utf-8")
        for target, value in [("leonida.post.OUT_DIR", self.root),
                              ("leonida.post.load", lambda _: (self.data, self.root))]:
            p = patch(target, value)
            p.start()
            self.addCleanup(p.stop)

    def build_with(self, fn, style=None):
        with patch.object(render, "cover", return_value=self.scene), \
             patch("leonida.publish.cfg", return_value={"formato": "video"}), \
             patch("leonida.publish.export_jpegs"), \
             patch.object(motion, "build", side_effect=fn), \
             patch.object(postvideo, "build", side_effect=fn):
            return post.build("fixture", video=False, langs=("pt",), estilo=style,
                              today=dt.date(2026, 10, 11), log=lambda _: None)

    def test_failure_preserves_all_styles_and_missing_music(self):
        for style in ("v2", "dinamico", "classico"):
            for error in (RuntimeError("encode interrompido"), postvideo.MusicMissing("música ausente")):
                with self.subTest(style=style, error=type(error).__name__):
                    def fail(*args, **kwargs):
                        raise error
                    with self.assertRaises(type(error)):
                        self.build_with(fail, style)
                    self.assertEqual(self.old.read_bytes(), b"previous valid delivery")
                    self.assertEqual((self.out / "br" / "legenda.txt").read_text(encoding="utf-8"),
                                     "Legenda anterior")
                    self.assertFalse(list(self.out.parent.glob(".build-*")))

    def test_v2_override_manifest_and_no_hyperframes(self):
        self.data["estilo"] = "classico"
        def encode(scenes, target_file, **kwargs):
            self.assertIsInstance(scenes[0], motion.Scene)
            self.assertEqual(kwargs["target"], 20)
            target_file.parent.mkdir(exist_ok=True)
            target_file.write_bytes(b"new delivery")
            return target_file
        with patch("leonida.video.render_video", side_effect=AssertionError("HyperFrames chamado")):
            self.assertEqual(self.build_with(encode, "v2"), self.out)
        manifest = json.loads((self.out / "post.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["publication_video_engine"], "v2")
        self.assertTrue(manifest["music"])
        self.assertIn("tiktok/post.mp4", manifest["files"]["br"])
        self.assertEqual(self.old.read_bytes(), b"new delivery")
        self.assertFalse(list(self.out.parent.glob(".build-*")))

    def test_explicit_legacy_style_is_kept(self):
        self.data["estilo"] = "classico"
        def encode(folder, **kwargs):
            self.assertEqual(kwargs["estilo"], "classico")
            target = folder / "tiktok" / "post.mp4"
            target.parent.mkdir(exist_ok=True)
            target.write_bytes(b"classic delivery")
            return target
        self.build_with(encode)

    def test_unknown_style_rejected_before_output_changes(self):
        with self.assertRaisesRegex(ValueError, "estilo desconhecido"):
            self.build_with(lambda *args, **kwargs: None, "invalido")
        self.assertEqual(self.old.read_bytes(), b"previous valid delivery")


if __name__ == "__main__":
    unittest.main()
