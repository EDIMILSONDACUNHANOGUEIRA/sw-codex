"""Escolha de música no editor de cortes; arquivos e áudios exclusivamente sintéticos."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from leonida import gameplay_render as gr
from leonida.config import ROOT


def temporary_directory():
    folder = ROOT / ".cache" / "tests"
    folder.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(prefix="gameplay-music-", dir=folder)


class GameplayMusicValidation(unittest.TestCase):
    def setUp(self):
        self.temp = temporary_directory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source.mp4"
        self.source.write_bytes(b"synthetic source")
        self.custom = self.root / "my-track.wav"
        self.custom.write_bytes(b"synthetic track")
        self.source_meta = {"format": {"duration": "4"}, "streams": [
            {"codec_type": "video", "width": 320, "height": 180}, {"codec_type": "audio"}]}
        self.music_meta = {"format": {"duration": "4"}, "streams": [{"codec_type": "audio"}]}
        self.plan = {"version": 1, "language": "pt", "title": "Música de teste",
                     "source": {"path": str(self.source), "credit": "Fixture"},
                     "max_long_seconds": 4, "short_seconds": 45,
                     "long": [{"start": 0, "end": 2}], "shorts": []}

    def assert_rejected_before_output(self, **kwargs):
        final = self.root / "export"

        def probe(path):
            return self.source_meta if Path(path).resolve() == self.source.resolve() else self.music_meta

        with patch.object(gr, "_probe", side_effect=probe), \
                patch.object(gr, "_encode_clip") as encoder, \
                patch("leonida.music.theme_path", return_value=self.custom):
            with self.assertRaises((ValueError, RuntimeError, FileNotFoundError)):
                gr.render(self.plan, final, subtitles=False, log=lambda _: None, **kwargs)
        encoder.assert_not_called()
        self.assertFalse(final.exists())
        self.assertFalse(list(self.root.glob(".*staging*")))

    def test_unknown_music_mode_is_rejected_before_output(self):
        self.assert_rejected_before_output(music_mode="random")

    def test_custom_mode_requires_a_local_existing_file(self):
        for path in (None, self.root / "missing.wav"):
            with self.subTest(path=path):
                self.assert_rejected_before_output(music_mode="custom", music_path=path)

    def test_custom_track_requires_an_audio_stream(self):
        self.music_meta["streams"] = [{"codec_type": "video", "width": 320, "height": 180}]
        self.assert_rejected_before_output(music_mode="custom", music_path=self.custom)

    def test_music_volume_must_be_finite_and_between_zero_and_one(self):
        for volume in (-.01, 1.01, float("nan"), float("inf")):
            with self.subTest(volume=volume):
                self.assert_rejected_before_output(music_mode="custom", music_path=self.custom,
                                                   music_volume=volume)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg necessário")
class GameplayMusicRealExport(unittest.TestCase):
    def test_custom_track_wins_over_default_and_none_preserves_original_audio(self):
        with temporary_directory() as temp:
            root = Path(temp)
            source, custom, default = root / "source.mp4", root / "custom.wav", root / "default.wav"
            ff = shutil.which("ffmpeg")
            subprocess.run([ff, "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i",
                            "color=c=0x1450B4:size=320x180:rate=5:duration=4", "-f", "lavfi", "-i",
                            "sine=frequency=500:sample_rate=48000:duration=4", "-c:v", "libx264",
                            "-preset", "ultrafast", "-threads", "2", "-c:a", "aac", "-shortest", str(source)],
                           check=True, capture_output=True)
            for track, frequency in ((custom, 150), (default, 170)):
                subprocess.run([ff, "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i",
                                f"sine=frequency={frequency}:sample_rate=48000:duration=4", str(track)],
                               check=True, capture_output=True)
            plan = {"version": 1, "language": "pt", "title": "Escolha de música",
                    "source": {"path": str(source), "credit": "Material sintético de teste"},
                    "max_long_seconds": 4, "short_seconds": 45,
                    "long": [{"start": 0, "end": 2}], "shorts": []}
            with patch("leonida.music.theme_path", return_value=default) as default_theme:
                selected = gr.render(plan, root / "custom-export", music=False, music_mode="custom", music_path=custom,
                                     music_volume=.1, log=lambda _: None)
                louder = gr.render(plan, root / "louder-export", music_mode="custom", music_path=custom,
                                   music_volume=.3, log=lambda _: None)
                none = gr.render(plan, root / "none-export", music_mode="none", log=lambda _: None)
            default_theme.assert_not_called()
            self.assertTrue(selected["music"])
            self.assertFalse(none["music"])
            self.assertEqual(selected["music_mode"], "custom")
            self.assertEqual(none["music_mode"], "none")
            self.assertEqual(selected["music_volume"], .1)
            saved = json.loads((root / "custom-export" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["music_mode"], "custom")

            def frequencies(video):
                raw = subprocess.run([ff, "-v", "error", "-nostdin", "-ss", "0.5", "-t", "1",
                                      "-i", str(video), "-map", "0:a", "-f", "s16le", "-ac", "1",
                                      "-ar", "16000", "-"], check=True, capture_output=True).stdout
                samples = np.frombuffer(raw, dtype="<i2").astype(float)
                spectrum = np.abs(np.fft.rfft(samples * np.hanning(len(samples))))
                bins = np.fft.rfftfreq(len(samples), 1 / 16000)
                return {hz: spectrum[np.argmin(np.abs(bins - hz))] for hz in (150, 170, 500)}

            chosen_audio = frequencies(selected["long"]["video"])
            louder_audio = frequencies(louder["long"]["video"])
            original_audio = frequencies(none["long"]["video"])
            self.assertGreater(louder_audio[150], chosen_audio[150] * 2)
            self.assertAlmostEqual(louder_audio[500] / chosen_audio[500], 1, delta=.05)
            self.assertGreater(chosen_audio[150], original_audio[150] * 20)
            self.assertGreater(chosen_audio[150], chosen_audio[170] * 20)
            self.assertGreater(chosen_audio[500], chosen_audio[150] * 2)
            self.assertGreater(original_audio[500], original_audio[150] * 100)
            self.assertGreater(original_audio[500], 1000)
            for result in (selected, louder, none):
                self.assertTrue(result["long"]["qa"]["decoded_all_streams"])
                self.assertTrue(result["long"]["qa"]["audio_non_silent"])
                self.assertAlmostEqual(result["long"]["qa"]["duration"], 2, delta=.12)
            self.assertFalse(list(root.glob(".*staging*")))


if __name__ == "__main__":
    unittest.main()
