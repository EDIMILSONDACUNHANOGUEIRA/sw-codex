"""Contratos de projetos e revisão dos intervalos, sem rede."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import hashlib

from leonida import gameplay, clips


class GameplayProjectsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source.mp4"
        self.source.write_bytes(b"fixture")
        self.plan = {"version": 1, "source": {"path": str(self.source), "duration": 1800,
                     "credit": "Canal de teste", "url": "", "title": "Fonte", "has_audio": True},
                     "language": "pt", "title": "Melhores momentos", "max_long_seconds": 660,
                     "short_seconds": 45, "candidates": [], "analysis": {"requires_review": True},
                     "long": [self.moment("l1", 20, 90), self.moment("l2", 130, 210)],
                     "shorts": [self.moment("s1", 30, 75)]}

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def moment(identifier, start, end):
        return {"id": identifier, "start": start, "end": end, "title": "Momento de teste",
                "reason": "Marcador", "score": 1, "peak": (start + end) / 2}

    def test_defaults_and_numeric_limits(self):
        self.assertEqual(gameplay.options()["lang"], "pt")
        self.assertEqual(gameplay.options()["max_long"], 660)
        for params in ({"max_long": 661}, {"short_count": 3.5}, {"short_seconds": 29},
                       {"short_seconds": float("nan")}, {"short_count": True}, {"lang": "es"}):
            with self.subTest(params=params), self.assertRaises(ValueError):
                gameplay.options(**params)

    def test_source_replacement_is_rejected(self):
        revised = copy.deepcopy(self.plan)
        revised["source"]["path"] = "other.mp4"
        with self.assertRaisesRegex(ValueError, "fonte não pode"):
            gameplay.validate_plan(revised, original=self.plan)

    def test_budget_bounds_overlap_and_duplicate(self):
        for change in (lambda p: p["long"][0].update(end=900),
                       lambda p: p["shorts"][0].update(end=95),
                       lambda p: p["long"][1].update(start=40),
                       lambda p: p["long"][0].update(start=float("nan")),
                       lambda p: p["long"].append(copy.deepcopy(p["long"][0]))):
            plan = copy.deepcopy(self.plan)
            change(plan)
            with self.assertRaises(ValueError):
                gameplay.validate_plan(plan)

    def test_revision_moves_cover_peak_and_keeps_original_evidence(self):
        revised = copy.deepcopy(self.plan)
        revised["shorts"][0].update(start=100, end=145, peak=44)
        revised["analysis"] = {"requires_review": False, "semantic": "invented"}
        verified = gameplay.validate_plan(revised, original=self.plan)
        self.assertEqual(verified["shorts"][0]["peak"], 100)
        self.assertEqual(verified["analysis"], self.plan["analysis"])
        self.assertEqual(self.plan["shorts"][0]["start"], 30)

    def test_frame_rounding_matches_renderer_budget(self):
        self.plan["long"] = [self.moment("l1", 0, 330.01), self.moment("l2", 400, 729.99)]
        with self.assertRaisesRegex(ValueError, "limite"):
            gameplay.validate_plan(self.plan)

    def test_web_source_and_path_traversal(self):
        self.assertEqual(gameplay.source_url("https://example.com/gameplay"), "https://example.com/gameplay")
        for value in ("file:///c:/secret", "C:/video.mp4", "https://user:token@example.com/video", "javascript:bad"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                gameplay.source_url(value)
        for value in ("../other", "C:/windows", "test/../../other"):
            with self.assertRaises(ValueError):
                gameplay.project_path(value)

    def test_download_cache_ignores_unfinished_files(self):
        url = "https://example.com/video"
        key = hashlib.sha1(url.encode()).hexdigest()[:14]
        cache = self.root / "cache"
        folder = cache / "videos"
        folder.mkdir(parents=True)
        for suffix in ("mp4.part", "ytdl", "info.json"):
            (folder / f"{key}.{suffix}").write_bytes(b"unfinished")
        complete = folder / f"{key}.webm"
        complete.write_bytes(b"complete")
        with patch.object(clips, "CACHE_DIR", cache):
            self.assertEqual(clips.download(url), complete)

    def test_versioned_delivery_does_not_replace_prior_export(self):
        root = self.root / "prontos"
        project = root / "gameplay" / "test-project"
        project.mkdir(parents=True)
        (project / "plan.json").write_text(json.dumps(self.plan), encoding="utf-8")

        def renderer(plan, output, **kwargs):
            output.mkdir(parents=True)
            for name in ("video.mp4", "cover.jpg", "manifest.json"):
                (output / name).write_text("original", encoding="utf-8")
            return {"long": {"video": str(output / "video.mp4"), "cover": str(output / "cover.jpg"), "duration": 150},
                    "shorts": [], "manifest": str(output / "manifest.json")}

        with patch.object(gameplay, "OUT_DIR", root), patch.object(gameplay, "PROJECTS", root / "gameplay"), \
             patch("leonida.gameplay_render.render", side_effect=renderer):
            first = gameplay.render_project("test-project")
            second = gameplay.render_project("test-project")
            self.assertNotEqual(first["output"], second["output"])
            self.assertEqual((Path(first["output"]) / "video.mp4").read_text(), "original")
            self.assertTrue(second["long"]["video_url"].startswith("/prontos/gameplay/"))
            self.assertTrue((Path(second["output"]) / "selection.json").is_file())


if __name__ == "__main__":
    unittest.main()
