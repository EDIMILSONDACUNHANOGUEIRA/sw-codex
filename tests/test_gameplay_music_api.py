"""Upload de trilha e escolha do usuário chegam à exportação real do app."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from apps.gameplay import app as cuts
from leonida.config import ROOT


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg necessário")
class MusicAPI(unittest.TestCase):
    def setUp(self):
        folder = ROOT / ".cache/tests"
        folder.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="music-api-", dir=folder)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home, self.uploads = self.root / "projects", self.root / "uploads"
        self.home.mkdir()
        self.uploads.mkdir()
        for name, value in (("HOME", self.home), ("UPLOADS", self.uploads), ("JOBS", {})):
            setting = patch.object(cuts, name, value)
            setting.start()
            self.addCleanup(setting.stop)
        self.client = TestClient(cuts.app, base_url="http://127.0.0.1")
        self.addCleanup(self.client.close)
        self.source = self.root / "source.mp4"
        subprocess.run([shutil.which("ffmpeg"),"-v","error","-nostdin","-y",
                        "-f","lavfi","-i","color=c=blue:size=320x180:rate=5:duration=4",
                        "-f","lavfi","-i","sine=frequency=500:sample_rate=48000:duration=4",
                        "-c:v","libx264","-preset","ultrafast","-threads","2",
                        "-c:a","aac","-shortest",str(self.source)],check=True,capture_output=True)
        project = self.home / "fixture"
        project.mkdir()
        self.plan = {"version":1,"source":{"path":str(self.source),"duration":4,"credit":"Fixture"},
                     "language":"pt","title":"Teste local", "max_long_seconds":10,"short_seconds":45,
                     "long":[{"id":"one","start":0,"end":2,"title":"Teste"}],"shorts":[]}
        (project / "plan.json").write_text(json.dumps(self.plan),encoding="utf-8")

    def music_upload(self):
        music = self.root / "custom.wav"
        subprocess.run([shutil.which("ffmpeg"),"-v","error","-nostdin","-y","-f","lavfi","-i",
                        "sine=frequency=150:sample_rate=48000:duration=1",str(music)],check=True,capture_output=True)
        response = self.client.post("/api/gameplay/music-upload",files={"file":("custom.wav",music.read_bytes(),"audio/wav")})
        self.assertEqual(response.status_code,200,response.text)
        return response.json()["source"]

    def test_rejects_invalid_audio_and_private_paths(self):
        for filename, content in (("bad.txt",b"data"),("bad.mp3",b"not audio"),("empty.wav",b"")):
            response = self.client.post("/api/gameplay/music-upload",files={"file":(filename,content)})
            self.assertEqual(response.status_code,400,response.text)
        self.assertEqual(list((self.uploads / "music").glob("*")),[])
        for body in ({"music_mode":"custom","music_source":str(self.source)},
                     {"music_mode":"custom","music_source":"music-upload:../private"},
                     {"music_mode":"other"},{"music_volume":True},{"music_volume":2}):
            with patch.object(cuts,"_job") as worker:
                response = self.client.post("/api/gameplay/render",json={"project_id":"fixture",**body})
            self.assertEqual(response.status_code,400,response.text)
            worker.assert_not_called()

    def test_uploaded_track_is_passed_and_none_needs_no_theme(self):
        music_source = self.music_upload()
        with patch.object(cuts,"_job",return_value="fixture") as worker:
            response = self.client.post("/api/gameplay/render",json={"project_id":"fixture",
                "music_mode":"custom","music_source":music_source,"music_volume":.25})
        self.assertEqual(response.status_code,200)
        self.assertEqual(worker.call_args.kwargs["music_mode"],"custom")
        self.assertEqual(worker.call_args.kwargs["music_volume"],.25)
        self.assertEqual(Path(worker.call_args.kwargs["music_path"]).parent,self.uploads / "music")
        with patch.object(cuts,"_job",return_value="fixture") as worker:
            response = self.client.post("/api/gameplay/render",json={"project_id":"fixture","music_mode":"none"})
        self.assertEqual(response.status_code,200)
        self.assertIsNone(worker.call_args.kwargs["music_path"])

    def test_real_api_job_exports_selected_music_with_voice_srt(self):
        music_source = self.music_upload()
        with patch("leonida.music.theme_path",side_effect=AssertionError("Custom não usa tema")):
            response = self.client.post("/api/gameplay/render",json={"project_id":"fixture",
                "music_mode":"custom","music_source":music_source,"music_volume":.2,
                "creator_srt":"1\n00:00:00,200 --> 00:00:01,600\nFala da pessoa ao fundo.\n"})
            self.assertEqual(response.status_code,200,response.text)
            identifier = response.json()["job"]
            deadline = time.monotonic()+45
            while time.monotonic()<deadline:
                job = self.client.get("/api/jobs/"+identifier).json()
                if job["status"]!="running":
                    break
                time.sleep(.05)
            self.assertEqual(job["status"],"done",job)
        result = job["result"]
        self.assertEqual(result["music_mode"],"custom")
        self.assertEqual(result["music_volume"],.2)
        self.assertTrue(result["long"]["video_url"].startswith("/gameplay-files/fixture/exports/"))
        output = Path(result["output"])
        self.assertTrue(output.is_relative_to(self.home))
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        self.assertTrue(manifest["long"]["qa"]["decoded_all_streams"])
        self.assertIn("Fala da pessoa",(output / "longo/legendas.srt").read_text(encoding="utf-8"))
        self.assertTrue((output / "longo/video.mp4").is_file())


if __name__=="__main__":
    unittest.main()
