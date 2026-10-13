"""Isolamento dos apps e contratos de upload/legendas, sem rede externa."""
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from leonida import gameplay

try:
    from fastapi.testclient import TestClient
    from apps.gameplay import app as cuts
    with patch("leonida.gallery.build"):
        from apps.noticias import app as news
except ImportError:
    TestClient = None


@unittest.skipIf(TestClient is None, "FastAPI/httpx não disponível")
class SeparateAppsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "cortes"
        self.uploads = self.root / "uploads"
        self.home.mkdir()
        self.uploads.mkdir()
        self.patches = [patch.object(cuts, "HOME", self.home), patch.object(cuts, "UPLOADS", self.uploads)]
        for active in self.patches:
            active.start()
            self.addCleanup(active.stop)
        self.client = TestClient(cuts.app)
        self.addCleanup(self.client.close)

    def test_route_sets_have_separate_purpose(self):
        news_paths = {getattr(route, "path", "") for route in news.app.routes}
        cuts_paths = {getattr(route, "path", "") for route in cuts.app.routes}
        self.assertIn("/api/radar", news_paths)
        self.assertIn("/api/posts", news_paths)
        self.assertFalse(any(path.startswith("/api/gameplay") for path in news_paths))
        self.assertNotIn("/api/posts/{pid}/send", news_paths)
        self.assertIn("/api/gameplay/analyze", cuts_paths)
        self.assertIn("/gameplay-files", cuts_paths)
        self.assertNotIn("/api/radar", cuts_paths)
        self.assertNotIn("/api/posts", cuts_paths)
        self.assertNotIn("/prontos", cuts_paths)

    def test_gameplay_import_does_not_load_news_or_radar(self):
        script = "import sys; import apps.gameplay.app; assert 'leonida.server' not in sys.modules; assert 'leonida.radar' not in sys.modules; assert 'leonida.post' not in sys.modules"
        result = subprocess.run([sys.executable, "-B", "-c", script], cwd=cuts.ROOT,
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_project_scope_changes_urls_without_changing_legacy_paths(self):
        previous = gameplay.PROJECTS
        with gameplay.project_home(self.home):
            self.assertEqual(gameplay.project_root(), self.home)
            self.assertEqual(gameplay.url_for(self.home / "test" / "video.mp4"),
                             "/gameplay-files/test/video.mp4")
            with self.assertRaises(ValueError):
                gameplay.url_for(self.root / "news.mp4")
        self.assertEqual(gameplay.PROJECTS, previous)
        self.assertEqual(gameplay.project_root(), previous)

    def test_two_jobs_keep_separate_contexts(self):
        ready = threading.Barrier(2)
        results = []
        def observe(name):
            home = self.root / name
            with gameplay.project_home(home):
                ready.wait(timeout=3)
                results.append((name, gameplay.project_root(), gameplay.url_for(home / "video.mp4")))
        workers = [threading.Thread(target=observe, args=(name,)) for name in ("one", "two")]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=5)
            self.assertFalse(worker.is_alive())
        self.assertEqual(len(results), 2)
        for name, home, url in results:
            self.assertEqual(home, self.root / name)
            self.assertEqual(url, "/gameplay-files/video.mp4")

    def test_job_sets_project_scope_and_keeps_structured_result(self):
        finished = threading.Event()
        actual_thread = threading.Thread
        class ObservedThread(actual_thread):
            def run(self):
                try:
                    super().run()
                finally:
                    finished.set()
        def inspect(log):
            log("Projeto separado")
            return {"root": str(gameplay.project_root()), "url": gameplay.url_for(self.home / "test" / "video.mp4")}
        with patch.object(cuts.threading, "Thread", ObservedThread):
            identifier = cuts._job(inspect)
            self.assertTrue(finished.wait(5))
        result = self.client.get("/api/jobs/" + identifier).json()
        self.assertEqual(result["status"], "done")
        self.assertEqual(result["result"]["root"], str(self.home))
        self.assertEqual(result["result"]["url"], "/gameplay-files/test/video.mp4")

    def test_upload_accepts_video_then_analysis_uses_saved_file(self):
        response = self.client.post("/api/gameplay/upload", files={"file": ("meu-video.mp4", b"fixture", "video/mp4")})
        self.assertEqual(response.status_code, 200)
        record = response.json()
        self.assertEqual(record["filename"], "meu-video.mp4")
        self.assertEqual(record["bytes"], 7)
        with patch.object(cuts, "_job", return_value="analyze-test") as worker:
            result = self.client.post("/api/gameplay/analyze", json={"source": record["source"]})
        self.assertEqual(result.status_code, 200)
        source = Path(worker.call_args.args[1])
        self.assertEqual(source.parent, self.uploads)
        self.assertEqual(source.read_bytes(), b"fixture")

    def test_upload_and_source_reject_unapproved_paths(self):
        self.assertEqual(self.client.post("/api/gameplay/upload", files={"file": ("x.txt", b"fixture")}).status_code, 400)
        self.assertEqual(self.client.post("/api/gameplay/upload", files={"file": ("x.mp4", b"")}).status_code, 400)
        self.assertEqual(list(self.uploads.iterdir()), [])
        for source in ("upload:../private", "C:/private/video.mp4", "upload:" + "f" * 32):
            with patch.object(cuts, "_job") as worker:
                self.assertEqual(self.client.post("/api/gameplay/analyze", json={"source": source}).status_code, 400)
                worker.assert_not_called()

    def test_render_defaults_to_speech_subtitles_and_passes_reviewed_srt(self):
        source = self.root / "source.mp4"
        source.write_bytes(b"fixture")
        project = self.home / "test-project"
        project.mkdir()
        plan = {"version": 1, "source": {"path": str(source), "duration": 1800, "credit": "Teste"},
                "language": "pt", "title": "Teste", "max_long_seconds": 660, "short_seconds": 45,
                "long": [], "shorts": [{"id": "s1", "start": 10, "end": 55, "title": "Teste"}]}
        (project / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
        srt = "1\n00:00:12,000 --> 00:00:13,500\nFala do comentarista.\n"
        with patch.object(cuts, "_job", return_value="render-test") as worker:
            response = self.client.post("/api/gameplay/render", json={"project_id": "test-project", "creator_srt": srt})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(worker.call_args.kwargs["subtitles"])
        self.assertEqual(worker.call_args.kwargs["speech_language"], "auto")
        self.assertEqual(worker.call_args.kwargs["creator_srt"], srt)
        for invalid in ({"speech_language": "es"}, {"subtitles": "true"}, {"creator_srt": 123}, {"creator_srt": False}):
            with patch.object(cuts, "_job") as worker:
                response = self.client.post("/api/gameplay/render", json={"project_id": "test-project", **invalid})
                self.assertEqual(response.status_code, 400)
                worker.assert_not_called()


if __name__ == "__main__":
    unittest.main()
