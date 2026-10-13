"""Legendas da voz: tempos da fonte, arte segura e exportação FFmpeg sintética."""
from io import BytesIO
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from leonida import gameplay_render as gr
from leonida import speech_captions as speech
from leonida.config import ROOT


def temporary_directory():
    folder = ROOT / ".cache" / "tests"
    folder.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(prefix="voice-captions-", dir=folder)


class CaptionRenderContracts(unittest.TestCase):
    def setUp(self):
        self.temp = temporary_directory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source.mp4"
        self.source.write_bytes(b"synthetic")
        self.meta = {"format": {"duration": "8"}, "streams": [
            {"codec_type": "video", "width": 320, "height": 180},
            {"codec_type": "audio"}]}
        self.plan = {"version": 1, "language": "pt", "title": "Teste da voz",
                     "source": {"path": str(self.source), "credit": "Fixture"},
                     "max_long_seconds": 10, "short_seconds": 45,
                     "long": [{"start": .1, "end": 1.11}, {"start": 4, "end": 5.01}],
                     "shorts": []}

    def assert_rejected_without_partial_export(self, srt, message):
        final = self.root / "export"
        with patch.object(gr, "_probe", return_value=self.meta), \
                patch.object(gr, "_encode_clip") as encoder, \
                patch.object(speech, "transcribe") as transcriber:
            with self.assertRaisesRegex(ValueError, message):
                gr.render(self.plan, final, music=False, subtitles=True, creator_srt=srt,
                          log=lambda _: None)
        encoder.assert_not_called()
        transcriber.assert_not_called()
        self.assertFalse(final.exists())
        self.assertFalse(list(self.root.glob(".*staging*")))

    def test_invalid_srt_fails_before_rendering_or_creating_output(self):
        self.assert_rejected_without_partial_export(
            "1\n00:00:01,000 --> 00:00:00,500\nIntervalo invertido\n", "Intervalo")

    def test_srt_outside_source_fails_before_rendering_or_creating_output(self):
        self.assert_rejected_without_partial_export(
            "1\n00:00:07,000 --> 00:00:09,000\nAlém da origem\n", "fora da duração")

    def test_manual_cues_are_remapped_to_selected_frames_without_asr(self):
        source_cues = [
            {"start": .25, "end": .85, "text": "Fala preservada no primeiro corte."},
            {"start": 2, "end": 3, "text": "Fala em trecho removido."},
            {"start": 4.1, "end": 4.8, "text": "Fala preservada no segundo corte."},
        ]
        ass = self.root / "voice.ass"
        with patch.object(speech, "transcribe") as transcriber:
            gr._subtitles(self.source, "en", ass, vertical=False,
                          source_cues=source_cues, moments=self.plan["long"], log=lambda _: None)
        transcriber.assert_not_called()
        data = json.loads(ass.with_suffix(".json").read_text(encoding="utf-8"))
        self.assertEqual(data["review_status"], "user_supplied")
        self.assertEqual(len(data["segments"]), 2)
        first, second = data["segments"]
        self.assertAlmostEqual(first["start"], .15)
        self.assertAlmostEqual(first["end"], .75)
        # The first 1.01-second cut encodes 31 frames, not 30.3 frames.
        self.assertAlmostEqual(second["start"], 31 / 30 + .1)
        self.assertAlmostEqual(second["end"], 31 / 30 + .8)
        self.assertNotIn("removido", ass.read_text(encoding="utf-8"))

    def test_automatic_captions_use_original_base_and_requested_speech_language(self):
        ass = self.root / "voice.ass"
        cues = [{"start": .2, "end": 1, "text": "Commentary from the source audio."}]

        def transcribe(base, output, *, language, log):
            self.assertEqual(base, self.source)
            self.assertEqual(language, "en")
            result = {"segments": cues, "source_audio": True, "added_music": False}
            output.write_text(json.dumps(result), encoding="utf-8")
            return result

        with patch.object(speech, "transcribe", side_effect=transcribe) as transcriber:
            gr._subtitles(self.source, "en", ass, vertical=True, log=lambda _: None)
        transcriber.assert_called_once()
        text = ass.read_text(encoding="utf-8")
        self.assertIn("Commentary from the source audio.", text.replace(r"\N", " "))
        self.assertRegex(text, r"\\pos\(\d+,1360\)")


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg necessário")
class RealCaptionExport(unittest.TestCase):
    def test_voice_srt_export_preserves_audio_and_burns_text_below_gameplay(self):
        with temporary_directory() as temp:
            root = Path(temp)
            source, theme = root / "source.mp4", root / "theme.wav"
            ff = shutil.which("ffmpeg")
            subprocess.run([ff, "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i",
                            "color=c=0x1450B4:size=320x180:rate=5:duration=8", "-f", "lavfi", "-i",
                            "sine=frequency=500:sample_rate=48000:duration=8", "-c:v", "libx264",
                            "-preset", "ultrafast", "-threads", "2", "-c:a", "aac", "-shortest", str(source)],
                           check=True, capture_output=True)
            subprocess.run([ff, "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i",
                            "sine=frequency=150:sample_rate=48000:duration=2", str(theme)],
                           check=True, capture_output=True)
            plan = {"version": 1, "language": "en", "title": "Synthetic gameplay",
                    "source": {"path": str(source), "credit": "Synthetic fixture"},
                    "max_long_seconds": 10, "short_seconds": 45,
                    "long": [{"start": .1, "end": 1.11}, {"start": 4, "end": 5.01}],
                    "shorts": []}
            srt = ("1\n00:00:00,250 --> 00:00:00,850\n"
                   "Eu falo ao fundo durante a gameplay.\n\n"
                   "2\n00:00:02,000 --> 00:00:03,000\nTrecho removido da edição.\n\n"
                   "3\n00:00:04,100 --> 00:00:04,800\n"
                   "Minha voz está legendada abaixo do jogo.\n")
            final = root / "export"
            with patch("leonida.music.theme_path", return_value=theme), \
                    patch.object(speech, "available", return_value=False), \
                    patch.object(speech, "transcribe") as transcriber:
                result = gr.render(plan, final, subtitles=True, speech_language="pt", creator_srt=srt,
                                   log=lambda _: None)
            transcriber.assert_not_called()
            self.assertEqual(result["caption_source"], "user_srt")
            self.assertEqual(result["speech_language"], "pt")
            self.assertTrue(result["music"])
            self.assertTrue(result["long"]["qa"]["decoded_all_streams"])
            self.assertTrue(result["long"]["qa"]["audio_non_silent"])
            self.assertAlmostEqual(result["long"]["qa"]["duration"], 62 / 30, delta=.12)
            folder = final / "longo"
            for name in ("legendas.srt", "legendas.ass", "legendas.json"):
                self.assertTrue((folder / name).is_file(), name)
            self.assertEqual(Path(result["long"]["subtitles"]), folder / "legendas.srt")
            text = (folder / "legendas.srt").read_text(encoding="utf-8")
            self.assertIn("00:00:01,133 --> 00:00:01,933", text)   # 0,7 s sobe para o mínimo de 0,8 s
            self.assertIn("Minha voz está legendada", text)
            self.assertNotIn("Trecho removido", text)
            data = json.loads((folder / "legendas.json").read_text(encoding="utf-8"))
            self.assertEqual(len(data["segments"]), 2)

            def frame(at):
                raw = subprocess.run([ff, "-v", "error", "-nostdin", "-ss", str(at), "-i",
                                      str(folder / "video.mp4"), "-frames:v", "1", "-f", "image2pipe",
                                      "-vcodec", "png", "-"], check=True, capture_output=True).stdout
                with Image.open(BytesIO(raw)) as image:
                    return np.asarray(image.convert("RGB"))

            active, silent = frame(1.5), frame(.95)
            # White glyphs occupy the reserved band below the 70..920 gameplay.
            active_white = np.all(active[925:1075] > 190, axis=2)
            silent_white = np.all(silent[925:1075] > 190, axis=2)
            self.assertGreater(int(active_white.sum()), 300)
            self.assertEqual(int(silent_white.sum()), 0)
            self.assertFalse(np.any(np.all(active[1075:] > 190, axis=2)))
            self.assertTrue(np.all(np.abs(active[900, 960] - np.array([20, 80, 180])) < 12))
            # The new low-volume theme is present while the original 500 Hz audio dominates.
            raw = subprocess.run([ff, "-v", "error", "-ss", "0.2", "-t", "0.6", "-i",
                                  str(folder / "video.mp4"), "-map", "0:a", "-f", "s16le", "-ac", "1",
                                  "-ar", "16000", "-"], check=True, capture_output=True).stdout
            samples = np.frombuffer(raw, dtype="<i2").astype(float)
            spectrum = np.abs(np.fft.rfft(samples))
            frequencies = np.fft.rfftfreq(len(samples), 1 / 16000)
            original = spectrum[np.argmin(np.abs(frequencies - 500))]
            bed = spectrum[np.argmin(np.abs(frequencies - 150))]
            self.assertGreater(original, bed * 2)
            self.assertGreater(bed, 1)
            self.assertFalse(list(root.glob(".*staging*")))
            self.assertFalse((final / ".work").exists())


if __name__ == "__main__":
    unittest.main()
