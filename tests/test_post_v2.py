"""Build completo: prioridade de estilo, manifesto e preservação de entregas."""
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
import yaml

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

    def build_with(self, fn, style=None, **build_options):
        with patch.object(render, "cover", return_value=self.scene), \
             patch("leonida.publish.cfg", return_value={"formato": "video"}), \
             patch("leonida.publish.export_jpegs"), \
             patch.object(motion, "build", side_effect=fn), \
             patch.object(postvideo, "build", side_effect=fn):
            return post.build("fixture", video=False, estilo=style, **build_options,
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
        self.data["video_segundos"] = 20  # revisões preservam a duração explícita de posts antigos
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

    def test_english_only_build_and_readme_without_changing_br_defaults(self):
        self.data["en"] = {"headline": "English *news*", "caption": "Reported information."}
        del self.data["pt"]
        self.data["video_segundos"] = 40

        def encode(scenes, target_file, **kwargs):
            # Só capa, sem fotos de apoio: motion.fit_target encurta os 40 s pedidos.
            self.assertLessEqual(kwargs["target"], 40)
            self.assertEqual(target_file.parent.parent.name, "us")
            target_file.parent.mkdir(exist_ok=True)
            target_file.write_bytes(b"English delivery")
            return target_file

        self.build_with(encode, "v2", langs=("en",))
        self.assertEqual(post.LANGS, ("pt",))
        self.assertEqual(self.old.read_bytes(), b"previous valid delivery")
        self.assertEqual((self.out / "us" / "tiktok" / "post.mp4").read_bytes(), b"English delivery")
        caption = (self.out / "us" / "caption.txt").read_text(encoding="utf-8")
        self.assertIn("Reported information.", caption)
        self.assertNotIn("#gta6brasil", caption)
        readme = (self.out / "README.md").read_text(encoding="utf-8")
        self.assertTrue(readme.startswith("# English news"))
        self.assertIn("us/tiktok/post.mp4", readme)
        self.assertIn("Reported information.", readme)
        self.assertNotIn("br/tiktok/post.mp4", readme)
        # The next default build still requires the configured BR copy.
        with self.assertRaisesRegex(ValueError, "pt.headline vazio"):
            self.build_with(encode, "v2")

    def test_explicit_language_validation_rejects_missing_english_copy(self):
        self.assertEqual(post.validate(self.data), [])
        self.assertIn("en.headline vazio", post.validate(self.data, ("en",)))
        with self.assertRaisesRegex(ValueError, "en.headline vazio"):
            self.build_with(lambda *args, **kwargs: self.fail("rendered"), "v2", langs=("en",))
        self.assertEqual(self.old.read_bytes(), b"previous valid delivery")

    def assert_rejected_before_render(self, expected):
        with patch.object(render, "cover") as cover:
            with self.assertRaisesRegex(ValueError, expected):
                post.build("fixture", video=False, estilo="v2", log=lambda _: None)
        cover.assert_not_called()
        self.assertEqual(self.old.read_bytes(), b"previous valid delivery")
        self.assertEqual((self.out / "br" / "legenda.txt").read_text(encoding="utf-8"),
                         "Legenda anterior")
        self.assertFalse(list(self.out.parent.glob(".build-*")))

    def test_yaml_colon_in_list_item_rejected_before_render(self):
        self.data["pt"]["slides"] = yaml.safe_load("""
- type: list
  title: Fonte da informação
  items:
    - Game Informer: 29 de setembro
""")
        self.assert_rejected_before_render(r"pt\.slides\[0\]\.items\[0\] deve ser texto")
        self.assertTrue(any("use aspas no YAML" in error for error in post.validate(self.data)))

    def test_slide_containers_and_titles_rejected_before_render(self):
        cases = [
            ("slide como texto", r"pt\.slides deve ser uma lista"),
            ({"type": "list"}, r"pt\.slides deve ser uma lista"),
            (["slide como texto"], r"pt\.slides\[0\] deve ser um objeto"),
            ([{"type": "list", "title": {"Título": "inválido"}, "items": ["Item"]}],
             r"pt\.slides\[0\]\.title deve ser texto"),
            ([{"type": "list", "title": "Título", "items": "Não iterar letras"}],
             r"pt\.slides\[0\]\.items deve ser uma lista"),
            ([{"type": "list", "title": "Título", "items": {"Item": "inválido"}}],
             r"pt\.slides\[0\]\.items deve ser uma lista"),
            ([{"type": "list", "title": "Título", "items": [123]}],
             r"pt\.slides\[0\]\.items\[0\] deve ser texto"),
        ]
        for slides, error in cases:
            with self.subTest(slides=slides):
                self.data["pt"]["slides"] = slides
                self.assert_rejected_before_render(error)

    def test_headline_and_caption_types_rejected_before_render(self):
        for field in ("headline", "caption"):
            original = self.data["pt"][field]
            for value in (123, {"Texto": "inválido"}, ["Texto"], False):
                with self.subTest(field=field, value=value):
                    self.data["pt"][field] = value
                    self.assert_rejected_before_render(rf"pt\.{field} deve ser texto")
            self.data["pt"][field] = original

    def test_grid_objects_and_quoted_list_text_remain_valid(self):
        self.data["pt"]["slides"] = yaml.safe_load("""
- type: list
  title: Fonte da informação
  items: ["Game Informer: 29 de setembro"]
- type: grid
  title: Imagens oficiais
  items:
    - image: fixture.jpg
      label: Rockstar Games
      sub: Arte oficial
""")
        self.assertEqual(post.validate(self.data), [])
        # Explicit EN checks must ignore malformed data for an unselected locale.
        self.data["en"] = self.data.pop("pt")
        self.data["pt"] = {"headline": 123, "caption": {"malformed": True}}
        self.assertEqual(post.validate(self.data, ("en",)), [])


if __name__ == "__main__":
    unittest.main()
