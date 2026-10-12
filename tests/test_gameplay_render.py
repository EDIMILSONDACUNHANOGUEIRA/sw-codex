"""Contratos e exportação real do renderer de gameplay; apenas material sintético."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw

from leonida import gameplay_render as gr
from leonida.config import ROOT


def temporary_directory():
    folder = ROOT / ".cache" / "tests"
    folder.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(prefix="gameplay-render-", dir=folder)


class RenderContracts(unittest.TestCase):
    def setUp(self):
        self.temp = temporary_directory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source.mp4"
        self.source.write_bytes(b"fixture")
        self.meta = {"format": {"duration": "1800"}, "streams": [
            {"codec_type": "video", "width": 1920, "height": 1080}, {"codec_type": "audio"}]}
        self.plan = {"version": 1, "language": "pt", "title": "Os melhores momentos",
                     "source": {"path": str(self.source), "credit": "Fixture"},
                     "max_long_seconds": 660, "short_seconds": 45,
                     "long": [{"start": 10, "end": 670}],
                     "shorts": [{"start": 1000, "end": 1045}]}
        self.probe = patch.object(gr, "_probe", return_value=self.meta)
        self.probe.start()
        self.addCleanup(self.probe.stop)

    def test_accepts_half_hour_sources_and_exact_eleven_minute_budget(self):
        source, meta = gr._validate(self.plan)
        self.assertEqual(source, self.source.resolve())
        self.assertEqual(meta["format"]["duration"], "1800")

    def test_excess_long_budget_rejected(self):
        self.plan["long"][0]["end"] = 670.1
        with self.assertRaisesRegex(ValueError, "soma"):
            gr._validate(self.plan)

    def test_frame_rounding_is_part_of_budget(self):
        self.plan["max_long_seconds"] = 1.04
        self.plan["long"] = [{"start": 0, "end": 1.01}, {"start": 10, "end": 10.03}]
        with self.assertRaisesRegex(ValueError, "soma"):
            gr._validate(self.plan)

    def test_short_duration_limits(self):
        for duration in (29.9, 60.1):
            self.plan["shorts"][0]["end"] = 1000 + duration
            with self.subTest(duration=duration), self.assertRaisesRegex(ValueError, "Cada short"):
                gr._validate(self.plan)

    def test_nonfinite_and_outside_ranges(self):
        for start, end in ((-1, 45), (0, float("nan")), (1700, 1900)):
            self.plan["long"] = [{"start": start, "end": end}]
            with self.subTest(start=start), self.assertRaisesRegex(ValueError, "intervalo"):
                gr._validate(self.plan)

    def test_existing_output_is_never_replaced(self):
        final = self.root / "export"
        final.mkdir()
        old = final / "old.mp4"
        old.write_bytes(b"preserve")
        with self.assertRaises(FileExistsError):
            gr.render(self.plan, final)
        self.assertEqual(old.read_bytes(), b"preserve")

    def test_music_missing_fails_before_creating_output(self):
        with patch("leonida.music.theme_path", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "Música tema"):
                gr.render(self.plan, self.root / "export")
        self.assertFalse((self.root / "export").exists())
        self.assertFalse(list(self.root.glob(".*staging*")))

    def test_encoding_failure_never_promotes_partial_export(self):
        with patch.object(gr, "_encode_clip", side_effect=RuntimeError("fixture encoding failure")):
            with self.assertRaisesRegex(RuntimeError, "fixture"):
                gr.render(self.plan, self.root / "export", music=False, log=lambda x: None)
        self.assertFalse((self.root / "export").exists())
        self.assertFalse(list(self.root.glob(".*staging*")))

    def test_vertical_cover_keeps_source_corners_and_aspect(self):
        # Four corner colors expose accidental center-cropping or geometric distortion.
        actual = Image.new("RGB", (1600, 900), (110, 110, 110))
        actual.paste((230, 10, 10), (0, 0, 160, 90))
        actual.paste((10, 230, 10), (1440, 0, 1600, 90))
        actual.paste((10, 10, 230), (0, 810, 160, 900))
        actual.paste((230, 230, 10), (1440, 810, 1600, 900))
        source = self.root / "real.png"
        out = self.root / "cover.jpg"
        actual.save(source)
        gr._cover(source, gr._overlay(gr.SHORT_SIZE, "Capa de teste", "Fixture", "pt"),
                  "Capa de teste", gr.SHORT_SIZE, out)
        with Image.open(out) as image:
            self.assertEqual(image.size, (1080, 1920))
            colors = [image.getpixel(p) for p in ((30, 640), (1040, 640), (30, 1205), (1040, 1205))]
        self.assertTrue(colors[0][0] > 200 and colors[0][1] < 30)
        self.assertTrue(colors[1][1] > 200 and colors[1][0] < 30)
        self.assertTrue(colors[2][2] > 200 and colors[2][0] < 30)
        self.assertTrue(colors[3][0] > 200 and colors[3][1] > 200)

    def test_unbroken_title_and_credit_fit_with_ellipsis(self):
        draw = ImageDraw.Draw(Image.new("RGB", (1080, 1920)))
        for text, width, kind in (("W" * 100, 866, "display"),
                                  ("W" * 160, 234, "body"),
                                  ("Gameplay " + "W" * 100 + " final", 420, "display")):
            with self.subTest(kind=kind, width=width):
                font, lines = gr._fit_text(draw, text, width, size=72, minimum=36,
                                           lines=3 if kind == "display" else 1, kind=kind)
                self.assertTrue(any(line.endswith("…") for line in lines))
                self.assertTrue(all(draw.textlength(line, font=font) <= width for line in lines))


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg necessário")
class RealExport(unittest.TestCase):
    def test_real_long_short_audio_and_complete_qa(self):
        with temporary_directory() as temp:
            root = Path(temp)
            source = root / "gameplay-fixture.mp4"
            theme = root / "tema-fixture.wav"
            ff = shutil.which("ffmpeg")
            subprocess.run([ff, "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i",
                            "testsrc2=size=320x180:rate=5:duration=32", "-f", "lavfi", "-i",
                            "sine=frequency=500:sample_rate=48000:duration=32", "-c:v", "libx264",
                            "-preset", "ultrafast", "-threads", "2", "-c:a", "aac", "-shortest", str(source)],
                           check=True, capture_output=True)
            subprocess.run([ff, "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i",
                            "sine=frequency=150:sample_rate=48000:duration=2", str(theme)], check=True, capture_output=True)
            plan = {"version": 1, "language": "pt", "title": "Momentos de teste",
                    "source": {"path": str(source.resolve()), "url": "", "title": "Fixture",
                               "credit": "Material sintético de teste", "duration": 32, "has_audio": True},
                    "max_long_seconds": 660, "short_seconds": 30,
                    "long": [{"id": "a", "start": 0, "end": 1.5, "score": .8, "peak": .7},
                             {"id": "b", "start": 2, "end": 3.5, "score": .9, "peak": 2.8}],
                    "shorts": [{"id": "c", "start": 0, "end": 30, "title": "Momento vertical", "score": .9, "peak": 2.8}]}
            final = root / "export"
            with patch("leonida.music.theme_path", return_value=theme):
                result = gr.render(plan, final, log=lambda x: None)
            self.assertTrue(final.is_dir())
            self.assertFalse(list(final.glob(".work")))
            self.assertFalse(list(root.glob(".*staging*")))
            self.assertTrue(result["music"])
            self.assertFalse(result["published"])
            self.assertFalse(result["visual_review"])
            self.assertEqual(result["long"]["qa"]["width"], 1920)
            self.assertEqual(result["long"]["qa"]["height"], 1080)
            self.assertAlmostEqual(result["long"]["qa"]["duration"], 3, delta=.12)
            short = result["shorts"][0]
            self.assertEqual((short["qa"]["width"], short["qa"]["height"]), (1080, 1920))
            self.assertAlmostEqual(short["qa"]["duration"], 30, delta=.1)
            self.assertTrue(short["qa"]["decoded_all_streams"])
            self.assertTrue(short["qa"]["audio_non_silent"])
            for video in [result["long"], short]:
                self.assertTrue(Path(video["video"]).is_file())
                self.assertTrue(Path(video["cover"]).is_file())
                self.assertTrue(Path(video["preview"]).is_file())
                self.assertIn("Crédito: Material sintético", Path(video["caption"]).read_text(encoding="utf-8"))
            self.assertEqual(json.loads((final / "plano.json").read_text(encoding="utf-8")), plan)
            # The original 500 Hz gameplay tone must remain stronger than the 150 Hz theme.
            raw = subprocess.run([ff, "-v", "error", "-ss", "1", "-t", "1", "-i", short["video"],
                                  "-map", "0:a", "-f", "s16le", "-ac", "1", "-ar", "16000", "-"],
                                 check=True, capture_output=True).stdout
            samples = np.frombuffer(raw, dtype="<i2").astype(float)
            spectrum = np.abs(np.fft.rfft(samples))
            frequencies = np.fft.rfftfreq(len(samples), 1 / 16000)
            original = spectrum[np.argmin(np.abs(frequencies - 500))]
            bed = spectrum[np.argmin(np.abs(frequencies - 150))]
            self.assertGreater(original, bed * 2)
            self.assertGreater(bed, 1)


if __name__ == "__main__":
    unittest.main()
