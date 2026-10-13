"""Música tema: arquivos de trabalho ignorados; faixa curta ou muda recusada sem apagar a anterior."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from leonida import music

FF = shutil.which("ffmpeg")


def tone(path, seconds, source="sine=frequency=330:sample_rate=44100"):
    subprocess.run([FF, "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i", source, "-t", str(seconds),
                    "-b:a", "128k", str(path)], check=True, capture_output=True)
    return path


@unittest.skipUnless(FF and shutil.which("ffprobe"), "FFmpeg necessário")
class ThemeTracks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "assets/music").mkdir(parents=True)
        for target, value in ((music, "ROOT"),):
            active = patch.object(target, value, self.root)
            active.start()
            self.addCleanup(active.stop)
        active = patch.object(music, "_cfg", return_value={"file": "assets/music/tema.mp3"})
        active.start()
        self.addCleanup(active.stop)

    def test_work_files_and_broken_cuts_are_not_themes(self):
        folder = self.root / "assets/music"
        good = tone(folder / "tema.mp3", 12)
        tone(folder / "tema.tmp.mp3", 12)
        tone(folder / "curta.mp3", 2)
        (folder / "download.mp3.part").write_bytes(b"x")
        self.assertEqual(music.themes(), [good])

    def test_short_or_silent_import_keeps_the_previous_theme(self):
        folder = self.root / "assets/music"
        previous = tone(folder / "tema.mp3", 12)
        before = previous.read_bytes()
        cases = ((tone(self.root / "curta.wav", 3), "só"),
                 (tone(self.root / "muda.wav", 15, "anullsrc=r=44100:cl=stereo"), "muda"))
        for source, message in cases:
            with self.subTest(source=source.name):
                with self.assertRaisesRegex(ValueError, message):
                    music.import_file(source, log=lambda _: None)
                self.assertEqual(previous.read_bytes(), before)
                self.assertFalse((folder / "tema.tmp.mp3").exists())

    def test_valid_import_replaces_theme(self):
        out = music.import_file(tone(self.root / "nova.wav", 14), log=lambda _: None)
        self.assertEqual(out, self.root / "assets/music/tema.mp3")
        self.assertEqual(music.themes(), [out])
        self.assertGreater(music.mean_volume(out), music.SILENT_DB)


if __name__ == "__main__":
    unittest.main()
