"""Cortes sem fala saem sem legenda; legenda automática só com reconhecimento de voz instalado."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from leonida import gameplay_render as gr
from leonida import speech_captions as speech
from leonida.config import ROOT

try:
    from fastapi.testclient import TestClient
    from apps.gameplay import app as cuts
except ImportError:
    TestClient = None


def temporary_directory():
    folder = ROOT / ".cache" / "tests"
    folder.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(prefix="no-speech-", dir=folder)


class NoSpeechContracts(unittest.TestCase):
    def setUp(self):
        self.temp = temporary_directory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)

    def test_transcription_without_speech_returns_empty_result(self):
        source = self.path / "source.mp4"
        source.write_bytes(b"localfixture")
        output = self.path / "captions.json"

        def fake_run(command, **kwargs):
            if "--stt-worker" in command:
                request = json.loads(Path(command[-1]).read_text(encoding="utf-8"))
                self.assertEqual(request["language"], "auto")
                Path(request["output"]).write_text(json.dumps({"language": "en", "segments": []}),
                                                   encoding="utf-8")
            return type("Result", (), {"returncode": 0, "stdout": b"", "stderr": b""})()

        logs = []
        with patch.object(speech, "_external_runtime", return_value=(Path("python312.exe"), self.path)), \
                patch.object(speech.shutil, "which", return_value="ffmpeg"), \
                patch.object(speech.subprocess, "run", side_effect=fake_run), \
                patch("leonida.config.CACHE_DIR", self.path):
            result = speech.transcribe(source, output, log=logs.append)
        self.assertEqual(result["segments"], [])
        self.assertTrue(result["no_speech"])
        self.assertTrue(output.is_file())
        self.assertTrue(any("sem legenda" in line for line in logs))

    def test_subtitles_return_none_for_a_clip_without_speech(self):
        def transcribe(base, output, *, language, log):
            result = {"segments": [], "no_speech": True}
            output.write_text(json.dumps(result), encoding="utf-8")
            return result

        with patch.object(speech, "transcribe", side_effect=transcribe):
            self.assertIsNone(gr._subtitles(self.path / "base.mp4", "auto", self.path / "s.ass",
                                            vertical=True, log=lambda _: None))
        self.assertIsNone(gr._subtitles(self.path / "base.mp4", "auto", self.path / "m.ass", vertical=True,
                                        source_cues=[{"start": 50, "end": 51, "text": "fora do corte"}],
                                        moments=[{"start": 1, "end": 2}], log=lambda _: None))


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg necessário")
class RealNoSpeechExport(unittest.TestCase):
    def test_clip_without_speech_is_exported_without_subtitles(self):
        with temporary_directory() as temp:
            root = Path(temp)
            source = root / "source.mp4"
            subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i",
                            "color=c=0x1450B4:size=320x180:rate=5:duration=8", "-f", "lavfi", "-i",
                            "sine=frequency=500:sample_rate=48000:duration=8", "-c:v", "libx264",
                            "-preset", "ultrafast", "-threads", "2", "-c:a", "aac", "-shortest", str(source)],
                           check=True, capture_output=True)
            plan = {"version": 1, "language": "pt", "title": "Sem fala",
                    "source": {"path": str(source), "credit": "Fixture"},
                    "max_long_seconds": 10, "short_seconds": 45,
                    "long": [{"start": 6, "end": 7.01}], "shorts": []}
            srt = "1\n00:00:00,250 --> 00:00:00,850\nFala fora do trecho escolhido.\n"
            result = gr.render(plan, root / "export", music=False, subtitles=True, creator_srt=srt,
                               log=lambda _: None)
            self.assertTrue(result["long"]["no_speech"])
            self.assertNotIn("subtitles", result["long"])
            self.assertTrue((root / "export" / "longo" / "video.mp4").is_file())
            self.assertFalse((root / "export" / "longo" / "legendas.srt").exists())


@unittest.skipIf(TestClient is None, "FastAPI/httpx não disponível")
class CaptionDefaultsAPI(unittest.TestCase):
    def setUp(self):
        self.temp = temporary_directory()
        self.addCleanup(self.temp.cleanup)
        home = Path(self.temp.name)
        source = home / "source.mp4"
        source.write_bytes(b"fixture")
        project = home / "test-project"
        project.mkdir()
        self.plan = {"version": 1, "source": {"path": str(source), "duration": 1800, "credit": "Teste",
                     "has_audio": True, "url": "", "title": "Teste"},
                     "language": "pt", "title": "Teste", "max_long_seconds": 660, "short_seconds": 45,
                     "long": [], "candidates": [], "analysis": {},
                     "shorts": [{"id": "s1", "start": 100, "end": 145, "title": "Teste", "peak": 120}]}
        (project / "plan.json").write_text(json.dumps(self.plan), encoding="utf-8")
        active = patch.object(cuts, "HOME", home)
        active.start()
        self.addCleanup(active.stop)
        self.client = TestClient(cuts.app, base_url="http://127.0.0.1")
        self.addCleanup(self.client.close)

    def render(self, available, **body):
        with patch.object(speech, "available", return_value=available), \
                patch.object(cuts, "_job", return_value="job") as worker:
            response = self.client.post("/api/gameplay/render", json={"project_id": "test-project", **body})
        self.assertEqual(response.status_code, 200, response.text)
        return worker.call_args.kwargs

    def test_subtitles_default_follows_installed_speech_recognition(self):
        self.assertFalse(self.render(False)["subtitles"])
        self.assertTrue(self.render(True)["subtitles"])
        self.assertTrue(self.render(False, creator_srt="1\n00:00:01,000 --> 00:00:02,000\nOi\n")["subtitles"])
        self.assertFalse(self.render(True, subtitles=False)["subtitles"])

    def test_speech_language_defaults_to_automatic(self):
        self.assertEqual(self.render(True)["speech_language"], "auto")
        with patch.object(speech, "available", return_value=False):
            self.assertFalse(self.client.get("/api/status").json()["captions"])


if __name__ == "__main__":
    unittest.main()
