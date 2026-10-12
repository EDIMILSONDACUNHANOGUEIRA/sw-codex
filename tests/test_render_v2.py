"""Regressões de layout/composição sem rede, modelo de recorte ou codificação de vídeo."""
import datetime as dt
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from leonida import gfx, render


TODAY = dt.date(2026, 10, 11)
POST = {
    "image": "fixture", "date": "2026-10-11", "tag": "oficial", "cutout": False,
    "source": {"name": "Rockstar Games"},
    "pt": {"headline": "GTA VI recebe classificação para *18 anos*",
           "summary": "Novos detalhes para PS5 e Xbox Series X|S.", "kicker": "OFICIAL"},
}


def core_box(layer, threshold=220):
    return layer.image.split()[-1].point(lambda v: 255 if v >= threshold else 0).getbbox()


class RenderV2Tests(unittest.TestCase):
    def setUp(self):
        self.src = Image.new("RGB", (960, 540), (84, 44, 72))
        self.media = patch.object(render, "load_image", side_effect=lambda *a: self.src.copy())
        self.media.start()
        self.face = patch.object(render.cut, "face_focus", return_value=None)
        self.face.start()
        self.upscale = patch.object(render.upscale, "ensure_min", side_effect=lambda im, *a: im)
        self.upscale.start()

    def tearDown(self):
        self.upscale.stop()
        self.face.stop()
        self.media.stop()

    def assert_composition(self, result):
        self.assertIsInstance(result, render.Render)
        self.assertTrue(np.array_equal(np.asarray(result.image), np.asarray(render.compose(result.layers).convert("RGB"))))
        self.assertEqual(result.image.size, (1080, 1920))

    def assert_safe(self, result, excluded=()):
        for layer in result.layers:
            if layer.name in {"bg", "frame", "shade", "subject", "subject_shadow", "subject_glow", "kicker", "card", "photo", "handle", *excluded}:
                continue
            box = core_box(layer)
            if box:
                with self.subTest(layer=layer.name):
                    self.assertLessEqual(box[2], 930)
                    self.assertLessEqual(box[3], 1540)

    def test_cover_layers_are_the_finished_art(self):
        with patch.object(gfx, "finish", wraps=gfx.finish) as finish:
            result = render.cover(POST, "pt", today=TODAY)
            self.assertEqual(finish.call_count, 1)
        self.assert_composition(result)
        self.assert_safe(result)
        self.assertEqual(result.meta["kind"], "cover")
        self.assertTrue(any(layer.extra.get("hot") is not None for layer in result.layers))

    def test_cutout_and_contact_shadow_are_part_of_the_same_composition(self):
        post = {**POST, "cutout": True}
        mask = Image.new("L", self.src.size, 0)
        from PIL import ImageDraw
        ImageDraw.Draw(mask).ellipse((250, 40, 670, 520), fill=255)
        with patch.object(render.cut, "available", return_value=True), \
                patch.object(render.cut, "subject_mask", return_value=mask), \
                patch.object(render.gfx, "refine_mask", side_effect=lambda im, m: m), \
                patch.object(render.cut, "mask_centroid", return_value=(0.5, 0.5)):
            result = render.cover(post, "pt", today=TODAY)
        self.assertTrue(result.meta["has_cutout"])
        self.assertIn("subject_shadow", {layer.name for layer in result.layers})
        self.assert_composition(result)
        self.assert_safe(result)

    def controlled_cutout(self, alpha, zoom=1.0):
        """Isola a composição da máscara de grading, exposição e iluminação."""
        post = {**POST, "cutout": True, "zoom": zoom, "focus": (0.5, 0.5),
                "pt": {**POST["pt"], "kicker": None}}
        mask = Image.new("L", self.src.size, alpha)
        look = {**gfx.look(), "light_wrap": False, "neon": False, "scanlines": False}
        with patch.object(render.cut, "available", return_value=True), \
                patch.object(render.cut, "subject_mask", return_value=mask), \
                patch.object(gfx, "refine_mask", side_effect=lambda im, m: m), \
                patch.object(render.upscale, "sharpen", side_effect=lambda im, *a: im.copy()), \
                patch.object(gfx, "vice_grade", side_effect=lambda im, *a: im.copy()), \
                patch.object(gfx, "finish", side_effect=lambda im, *a, **k: im.copy()), \
                patch.object(gfx, "look", return_value=look), \
                patch.object(render, "lift_dark_subject", side_effect=lambda im, *a: im):
            return render.cover(post, "pt", today=TODAY)

    def test_partial_cutout_alpha_does_not_darken_source_rgb(self):
        self.src = Image.new("RGB", (960, 540), (200, 160, 120))
        for zoom in (1.0, 0.76):
            with self.subTest(zoom=zoom):
                result = self.controlled_cutout(128, zoom)
                subject = next(layer.image for layer in result.layers if layer.name == "subject")
                pixel = subject.getpixel((540, 1000))
                self.assertEqual(pixel, (200, 160, 120, 128))
                composite = Image.alpha_composite(Image.new("RGBA", (1, 1), (100, 100, 100, 255)),
                                                  Image.new("RGBA", (1, 1), pixel))
                self.assertEqual(composite.getpixel((0, 0)), (150, 130, 110, 255))

    def test_background_top_fade_does_not_alter_opaque_subject(self):
        self.src = Image.new("RGB", (960, 540), (200, 160, 120))
        result = self.controlled_cutout(255)
        subject = next(layer.image for layer in result.layers if layer.name == "subject")
        background = next(layer.image for layer in result.layers if layer.name == "bg")
        self.assertEqual(subject.getpixel((540, 10)), (200, 160, 120, 255))
        self.assertLess(background.getpixel((540, 10))[0], 200)

    def test_countdown_and_logo_have_safe_gap_for_zero_and_three_digits(self):
        release = dt.date(2026, 11, 19)
        for days in (0, 1, 39, 365):
            layers = render.top_layers((1080, 1920), "pt", 150, 154, release - dt.timedelta(days=days))
            logo, chip = next(l for l in layers if l.name == "brand"), next(l for l in layers if l.name == "countdown")
            with self.subTest(days=days):
                self.assertLessEqual(core_box(chip)[2], 930)
                self.assertLessEqual(core_box(logo)[2] + 18, core_box(chip)[0])

    def test_protected_names_and_orphans(self):
        f = gfx.font("body", 36)
        text = "Saiba tudo sobre GTA VI para maiores de 18 anos no Xbox Series X|S"
        lines = render._wrap_text(text, f, 400)
        merged = " ".join(lines).replace("\u00a0", " ")
        self.assertEqual(merged, text)
        for phrase in ("GTA VI", "18 anos", "Xbox Series X|S"):
            self.assertTrue(any(phrase in line.replace("\u00a0", " ") for line in lines))
        plain = render._wrap_text("Um novo detalhe oficial muito esperado", f, 470)
        self.assertGreaterEqual(len(plain[-1].split()), 2)
        self.assertGreaterEqual(render._line_height(f, 1.16), f.getbbox("ÁÉÇgjpq")[3] - f.getbbox("ÁÉÇgjpq")[1] + 10)

    def test_long_list_safe_steps_and_legacy_image_api(self):
        slide = {"title": "O que sabemos sobre *GTA VI*", "items": [
            "GTA VI está confirmado para PS5 e Xbox Series X|S.",
            "A classificação indicativa contempla conteúdo para maiores de 18 anos.",
            "A Rockstar Games é a fonte oficial para os detalhes confirmados.",
            "Este item tem palavras com acentuação e descendentes: ação, jogabilidade e opções.",
            "Não há versão para computador anunciada no material oficial.",
            "O texto permanece dentro dos limites da interface do TikTok.",
            "Todos os dados são exemplos de teste de composição visual.",
        ]}
        result = render.slide_list(POST, "pt", slide, today=TODAY, with_layers=True)
        self.assert_composition(result)
        self.assert_safe(result)
        self.assertEqual(result.meta["steps"], 7)
        self.assertEqual({l.step for l in result.layers if l.step}, set(range(1, 8)))
        legacy = render.slide_list(POST, "pt", slide, today=TODAY, upto=2)
        self.assertIsInstance(legacy, Image.Image)

    def test_grid_safe_and_legacy_image_api(self):
        slide = {"title": "As seis *rádios*", "items": [
            {"image": "fixture", "label": f"RÁDIO OFICIAL {i}", "sub": "Programação e músicas"} for i in range(6)
        ], "note": "Exemplos de composição para GTA VI."}
        result = render.slide_grid(POST, "pt", slide, today=TODAY, with_layers=True)
        self.assert_composition(result)
        self.assert_safe(result)
        self.assertEqual(result.meta["steps"], 6)

    def test_portrait_photo_and_multiline_credit_fit_above_caption(self):
        self.src = Image.new("RGB", (540, 960), (84, 44, 72))
        credit = "Rockstar Games / LOVE Magazine / uma identificação extensa da imagem oficial para testar o crédito completo"
        result = render.slide_foto(POST, "pt", credit=credit, with_layers=True)
        self.assert_composition(result)
        self.assert_safe(result)
        photo = next(l for l in result.layers if l.name == "photo")
        self.assertLessEqual(core_box(photo)[3], 1540)
        credit_layer = next(l for l in result.layers if l.name == "credit")
        self.assertGreater(core_box(credit_layer)[1], core_box(photo)[3])

    def test_cta_has_safe_text_and_exact_composition(self):
        result = render.slide_cta(POST, "pt", today=TODAY, with_layers=True)
        self.assert_composition(result)
        self.assert_safe(result)


if __name__ == "__main__":
    unittest.main()
