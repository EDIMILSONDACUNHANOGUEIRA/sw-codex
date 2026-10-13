"""Cortes: cancelar tarefa, limpar sobras, QA que reprova preto/mudo e títulos únicos."""
import os
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from leonida import gameplay, gameplay_analysis
from leonida import gameplay_render as gr
from leonida.config import ROOT

try:
    from fastapi.testclient import TestClient
    from apps.gameplay import app as cuts
except ImportError:
    TestClient = None


def temporary_directory():
    folder = ROOT / ".cache" / "tests"
    folder.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(prefix="gameplay-jobs-", dir=folder)


@unittest.skipIf(TestClient is None, "FastAPI/httpx não disponível")
class CancelJob(unittest.TestCase):
    def test_running_job_stops_at_next_step(self):
        started = threading.Event()

        def slow(log):
            for step in range(400):
                log(f"passo {step}")
                started.set()
                time.sleep(.01)
            return "terminou"

        with TestClient(cuts.app, base_url="http://127.0.0.1") as client:
            identifier = cuts._job(slow)
            self.assertTrue(started.wait(5))
            response = client.post(f"/api/jobs/{identifier}/cancel")
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()["cancelling"])
            for _ in range(300):
                if cuts.JOBS[identifier]["status"] != "running":
                    break
                time.sleep(.01)
            self.assertEqual(cuts.JOBS[identifier]["status"], "cancelled")
            self.assertIsNone(cuts.JOBS[identifier]["result"])
            self.assertEqual(client.post("/api/jobs/nao-existe/cancel").status_code, 404)


class Cleanup(unittest.TestCase):
    def test_only_old_leftovers_created_by_the_app_are_removed(self):
        with temporary_directory() as temp:
            root = Path(temp)
            old = time.time() - 7200
            orphan = root / "2026-10-12-gameplay-abcdef12"
            finished = root / "2026-10-12-pronto-abcdef34"
            fresh = root / "2026-10-13-rodando-abcdef56"
            staging = finished / "exports" / ".export-1234567890.staging-abcdef1234"
            export = finished / "exports" / "export-1234567890"
            keep = root / "revisoes"
            for folder in (orphan, fresh, staging, export, keep):
                folder.mkdir(parents=True)
            (finished / "project.json").write_text("{}", encoding="utf-8")
            for folder in (orphan, staging, export, keep, finished):
                os.utime(folder, (old, old))
            self.assertEqual(gameplay.cleanup_orphans(root, log=lambda _: None), 2)
            self.assertFalse(orphan.exists())
            self.assertFalse(staging.exists())
            for folder in (fresh, export, keep, finished):
                self.assertTrue(folder.exists(), folder)

    def test_failed_analysis_leaves_no_half_project(self):
        with temporary_directory() as temp, gameplay.project_home(Path(temp)):
            with patch.object(gameplay_analysis, "analyze", side_effect=RuntimeError("falhou")):
                with self.assertRaises(RuntimeError):
                    gameplay.analyze("https://example.com/video", log=lambda _: None)
            self.assertEqual(list(Path(temp).iterdir()), [])


class Titles(unittest.TestCase):
    def test_automatic_moments_have_unique_titles(self):
        times = np.arange(0, 1800, 2.0) + 1
        scores = (np.sin(times / 37) + 1) / 2
        candidates, long, shorts = gameplay_analysis.select_moments(times, scores, 1800, short_count=3)
        titles = [c["title"] for c in candidates]
        self.assertEqual(len(titles), len(set(titles)))
        self.assertTrue(all(t.startswith("Momento ") for t in titles))
        self.assertEqual(len({s["title"] for s in shorts}), len(shorts))


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg necessário")
class QualityGate(unittest.TestCase):
    def make(self, root, color, audio):
        source = root / "source.mp4"
        subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i",
                        f"color=c={color}:size=320x180:rate=5:duration=4", "-f", "lavfi", "-i", audio,
                        "-c:v", "libx264", "-preset", "ultrafast", "-threads", "2", "-c:a", "aac",
                        "-shortest", str(source)], check=True, capture_output=True)
        return {"version": 1, "language": "pt", "title": "QA",
                "source": {"path": str(source), "credit": "Fixture"},
                "max_long_seconds": 10, "short_seconds": 45,
                "long": [{"start": .5, "end": 2.5}], "shorts": []}

    def test_black_export_is_rejected(self):
        with temporary_directory() as temp:
            root = Path(temp)
            plan = self.make(root, "black", "sine=frequency=400:sample_rate=48000:duration=4")
            with patch.object(gr, "_overlay", side_effect=lambda size, *a, **k: gr.Image.new("RGBA", size, (0, 0, 0, 0))):
                with self.assertRaisesRegex(RuntimeError, "preto"):
                    gr.render(plan, root / "export", music=False, log=lambda _: None)
            self.assertFalse((root / "export").exists())

    def test_silent_export_with_music_is_rejected(self):
        with temporary_directory() as temp:
            root = Path(temp)
            plan = self.make(root, "0x1450B4", "anullsrc=r=48000:cl=stereo")
            theme = root / "silencio.wav"
            subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i",
                            "anullsrc=r=48000:cl=stereo", "-t", "3", str(theme)], check=True, capture_output=True)
            with self.assertRaisesRegex(RuntimeError, "mudo"):
                gr.render(plan, root / "export", music_mode="custom", music_path=theme, log=lambda _: None)
            self.assertFalse((root / "export").exists())


if __name__ == "__main__":
    unittest.main()
