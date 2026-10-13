"""API local: erros antes dos jobs, resultados estruturados e fonte imutável."""
import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from leonida import gameplay

try:
    from fastapi.testclient import TestClient
    with patch("leonida.gallery.build"):
        from leonida import server
except ImportError:
    TestClient = None


@unittest.skipIf(TestClient is None, "FastAPI/httpx não disponível")
class GameplayAPITest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source.mp4"
        self.source.write_bytes(b"fixture")
        self.project = self.root / "gameplay" / "test-project"
        self.project.mkdir(parents=True)
        self.plan = {"version": 1, "source": {"path": str(self.source), "duration": 1800,
                     "credit": "Teste", "has_audio": True, "url": "", "title": "Teste"},
                     "language": "pt", "title": "Teste", "max_long_seconds": 660,
                     "short_seconds": 45, "long": [], "candidates": [], "analysis": {},
                     "shorts": [{"id": "s1", "start": 100, "end": 145, "title": "Teste", "peak": 120}]}
        (self.project / "plan.json").write_text(json.dumps(self.plan), encoding="utf-8")
        self.patch = patch.object(gameplay, "PROJECTS", self.root / "gameplay")
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.client = TestClient(server.app, base_url="http://127.0.0.1")
        self.addCleanup(self.client.close)

    def test_analysis_returns_structured_job_with_defaults(self):
        with patch.object(server, "_job", return_value="job-test") as worker:
            response = self.client.post("/api/gameplay/analyze", json={"source": "https://example.com/video"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"job": "job-test"})
        self.assertTrue(worker.call_args.kwargs["structured"])
        self.assertEqual(worker.call_args.kwargs["lang"], "pt")
        self.assertEqual(worker.call_args.kwargs["max_long"], 660)

    def test_invalid_analysis_does_not_launch_job(self):
        for body in ({"source": "C:/private.mp4"}, {"source": "https://example.com/video", "max_long_minutes": 12},
                     {"source": "https://example.com/video", "short_seconds": 15}):
            with patch.object(server, "_job") as worker:
                self.assertEqual(self.client.post("/api/gameplay/analyze", json=body).status_code, 400)
                worker.assert_not_called()

    def test_revision_and_strict_flags(self):
        with patch.object(server, "_job", return_value="render-test") as worker:
            response = self.client.post("/api/gameplay/render", json={"project_id": "test-project", "plan": self.plan})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(worker.call_args.kwargs["music"])
        revised = copy.deepcopy(self.plan)
        revised["source"]["path"] = str(self.root / "private.mp4")
        for body in ({"project_id": "test-project", "plan": revised},
                     {"project_id": "test-project", "music": "false"}, {"project_id": "../outside"}):
            with patch.object(server, "_job") as worker:
                self.assertEqual(self.client.post("/api/gameplay/render", json=body).status_code, 400)
                worker.assert_not_called()

    def test_worker_preserves_dictionary_results(self):
        finished = threading.Event()
        actual = threading.Thread
        class ObservedThread(actual):
            def run(self):
                try:
                    super().run()
                finally:
                    finished.set()
        with patch.object(server.threading, "Thread", ObservedThread):
            job_id = server._job(lambda log: {"project_id": "test-project", "plan": {"version": 1}}, structured=True)
            self.assertTrue(finished.wait(5), "Job não terminou")
        job = self.client.get(f"/api/jobs/{job_id}").json()
        self.assertEqual(job["status"], "done")
        self.assertIsInstance(job["result"], dict)
        self.assertEqual(job["result"]["plan"]["version"], 1)


if __name__ == "__main__":
    unittest.main()
