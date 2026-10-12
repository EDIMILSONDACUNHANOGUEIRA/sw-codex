"""Limites de seleção e análise de mídia local sintética, sem downloads."""
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from leonida import gameplay_analysis as gameplay


class SelectionTests(unittest.TestCase):
    def samples(self, duration=3600):
        times = np.arange(1, duration, 2, dtype=float)
        scores = np.zeros(len(times))
        for peak in (120, 670, 1700, 2850, 3380):
            scores += np.maximum(0, 1 - np.abs(times - peak) / 15)
        return times, np.clip(scores, 0, 1)

    def assert_ranges(self, items, duration):
        for item in items:
            self.assertGreaterEqual(item["start"], 0)
            self.assertGreater(item["end"], item["start"])
            self.assertLessEqual(item["end"], duration + .001)
            self.assertGreaterEqual(item["peak"], item["start"] - .001)
            self.assertLessEqual(item["peak"], item["end"] + .001)
        for previous, following in zip(items, items[1:]):
            self.assertLessEqual(previous["end"], following["start"] + .001)

    def test_hour_source_budget_full_shorts_and_diversity(self):
        candidates, long, shorts = gameplay.select_moments(*self.samples(), 3600,
                max_long=660, short_count=3, short_seconds=45)
        self.assertGreater(len(candidates), len(shorts))
        self.assertLessEqual(sum(item["end"] - item["start"] for item in long), 660 + .001)
        self.assertEqual(len(shorts), 3)
        self.assertTrue(all(abs(item["end"] - item["start"] - 45) < .001 for item in shorts))
        self.assertGreater(shorts[-1]["peak"] - shorts[0]["peak"], 2000)
        for items in (candidates, long, shorts):
            self.assert_ranges(items, 3600)

    def test_quiet_source_distributes_review_examples(self):
        times = np.arange(1, 7200, 2)
        _, long, shorts = gameplay.select_moments(times, np.zeros(len(times)), 7200)
        self.assertGreater(shorts[-1]["peak"] - shorts[0]["peak"], 4000)
        self.assertTrue(all("sinais baixos" in item["reason"] for item in shorts))
        self.assertLessEqual(sum(item["end"] - item["start"] for item in long), 660 + .001)

    def test_editor_marker_priority_and_timestamp_parsing(self):
        marker = {"start": "0:08:00", "end": "0:09:40", "title": "Missão comentada"}
        candidates, long, shorts = gameplay.select_moments(*self.samples(), 3600,
                max_long=120, short_count=1, markers=[marker])
        manual = next(item for item in candidates if item.get("manual"))
        self.assertEqual((manual["start"], manual["end"]), (480, 580))
        self.assertEqual(long[0]["id"], "manual-01")
        self.assertEqual(shorts[0]["id"], "manual-01")
        self.assertGreaterEqual(shorts[0]["start"], 480)
        self.assertLessEqual(shorts[0]["end"], 580)
        self.assertEqual(shorts[0]["title"], "Missão comentada")

    def test_source_shorter_than_30_seconds_is_not_stretched(self):
        candidates, long, shorts = gameplay.select_moments(np.arange(1, 18, 2), np.ones(9), 18)
        self.assertEqual(shorts, [])
        self.assertAlmostEqual(sum(item["end"] - item["start"] for item in long), 18)
        self.assert_ranges(candidates, 18)

    def test_short_source_produces_available_complete_duration(self):
        _, long, shorts = gameplay.select_moments(np.arange(1, 37, 2), np.ones(18), 37)
        self.assertEqual(len(shorts), 1)
        self.assertAlmostEqual(shorts[0]["end"] - shorts[0]["start"], 37)
        self.assertAlmostEqual(sum(item["end"] - item["start"] for item in long), 37)

    def test_final_long_excerpt_respects_budget(self):
        _, long, _ = gameplay.select_moments(*self.samples(), 3600, max_long=80)
        self.assertLessEqual(sum(item["end"] - item["start"] for item in long), 80 + .001)
        self.assertGreater(sum(item["end"] - item["start"] for item in long), 70)

    def test_fractional_markers_fit_eleven_minute_encoded_budget(self):
        markers = [{"start": 0, "end": 330.01, "title": "Parte A"},
                   {"start": 400, "end": 729.99, "title": "Parte B"}]
        _, long, _ = gameplay.select_moments(*self.samples(), 3600, max_long=660,
                                             short_count=0, markers=markers)
        frames = sum(math.ceil((item["end"] - item["start"]) * 30 - 1e-7) for item in long)
        self.assertLessEqual(frames, math.floor(660 * 30))
        self.assertEqual(len(long), 2)
        self.assertTrue(any(item["end"] == markers[int(item["id"][-2:]) - 1]["end"] for item in long))
        self.assertTrue(any("encurtado" in item["reason"] for item in long))
        self.assert_ranges(long, 3600)

    def test_last_endpoint_keeps_precision_and_budget_floors_to_frames(self):
        marker = {"start": .01, "end": 100.01, "title": "Trecho indicado"}
        _, long, _ = gameplay.select_moments(*self.samples(), 3600, max_long=80.07,
                                             short_count=0, markers=[marker])
        self.assertEqual(len(long), 1)
        duration = long[0]["end"] - long[0]["start"]
        frames = math.ceil(duration * 30 - 1e-7)
        self.assertEqual(frames, math.floor(80.07 * 30))
        self.assertLessEqual(frames / 30, 80.07)
        # Millisecond rounding would produce 80.067 s and accidentally cost 2403 frames.
        self.assertNotEqual(long[0]["end"], round(long[0]["end"], 3))

    def test_fractional_marker_is_unchanged_when_encoded_cost_fits(self):
        marker = {"start": .012345, "end": 79.012345, "title": "Trecho exato"}
        _, long, _ = gameplay.select_moments(*self.samples(), 3600, max_long=79.01,
                                             short_count=0, markers=[marker])
        self.assertEqual(len(long), 1)
        self.assertEqual((long[0]["start"], long[0]["end"]), (marker["start"], marker["end"]))
        self.assertNotIn("encurtado", long[0]["reason"])

    def test_automatic_fractional_windows_reserve_cost_per_excerpt(self):
        for maximum in (659.99, 660):
            with self.subTest(maximum=maximum):
                _, long, _ = gameplay.select_moments(*self.samples(), 3600, max_long=maximum,
                                                     short_count=0, short_seconds=45.067)
                frames = sum(math.ceil((item["end"] - item["start"]) * 30 - 1e-7) for item in long)
                self.assertLessEqual(frames, math.floor(maximum * 30))
                self.assertGreater(frames / 30, maximum - 1)

    def test_bad_markers_do_not_silently_change_requested_intervals(self):
        for markers in ([{"start": -1, "end": 5}], [{"start": 10, "end": 10}],
                        [{"start": 0, "end": 3601}], [{"start": "nan", "end": 3}],
                        [{"start": 1}], [{"start": 1, "end": 40}, {"start": 20, "end": 60}]):
            with self.subTest(markers=markers), self.assertRaises(ValueError):
                gameplay.select_moments(*self.samples(), 3600, markers=markers)

    def test_invalid_options_fail_before_downloading(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(gameplay.clips, "download") as download:
            for options in ({"max_long": 661}, {"max_long": float("nan")}, {"short_seconds": 29},
                            {"short_seconds": float("inf")}, {"short_count": -1},
                            {"short_count": 2.5}, {"lang": "xx"}):
                with self.subTest(options=options), self.assertRaises(ValueError):
                    gameplay.analyze("https://example.invalid/video", Path(directory), **options)
            download.assert_not_called()


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg indisponível")
class MediaTests(unittest.TestCase):
    def make_source(self, path, duration, audio=False, fps=2):
        command = ["ffmpeg", "-v", "error", "-nostdin", "-f", "lavfi", "-i",
                   f"testsrc2=size=160x90:rate={fps}:duration={duration}"]
        if audio:
            command += ["-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=8000:duration={duration}"]
        command += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]
        command += ["-c:a", "aac"] if audio else ["-an"]
        subprocess.run(command + [str(path)], capture_output=True, check=True)

    def test_actual_silent_video_plan_and_storyboard(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "silent.mp4"
            self.make_source(source, 37)
            output = root / "edition"
            logs = []
            plan = gameplay.analyze(str(source), output, max_long=660, short_count=3,
                                    title="Teste de análise", credit="Fixture sintética", log=logs.append)
            self.assertFalse(plan["source"]["has_audio"])
            self.assertTrue(plan["analysis"]["requires_review"])
            self.assertEqual(len(plan["shorts"]), 1)
            self.assertAlmostEqual(plan["shorts"][0]["end"] - plan["shorts"][0]["start"], 37, places=1)
            self.assertEqual(json.loads((output / "plan.json").read_text(encoding="utf-8")), plan)
            with Image.open(output / "storyboard.jpg") as image:
                self.assertEqual(image.width, 1280)
                self.assertGreater(image.height, 200)
            before = (output / "plan.json").read_bytes()
            with self.assertRaises(FileExistsError):
                gameplay.analyze(str(source), output, log=lambda message: None)
            self.assertEqual((output / "plan.json").read_bytes(), before)

    def test_real_audio_energy_and_probe(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "audio.mp4"
            self.make_source(source, 8, audio=True)
            info = gameplay.probe(source)
            self.assertTrue(info["has_audio"])
            self.assertAlmostEqual(info["duration"], 8, places=1)
            energy = gameplay._energy(source, 2, 4, lambda message: None)
            self.assertEqual(len(energy), 4)
            self.assertTrue(np.all(np.isfinite(energy)))
            self.assertGreater(float(energy.min()), .02)

    def test_actual_thirty_minute_source_has_no_input_cap(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "thirty-minutes.mp4"
            # Sparse video is an actual 30-minute file, small enough for CPU-only CI.
            self.make_source(source, 1800, fps="1/10")
            info = gameplay.probe(source)
            self.assertAlmostEqual(info["duration"], 1800, places=1)
            motion = gameplay._motion(source, info["duration"], 2, lambda message: None)
            self.assertGreaterEqual(len(motion), 899)
            candidates, long, shorts = gameplay.select_moments(
                (np.arange(len(motion)) + .5) * 2, gameplay._normalise(motion, .025), info["duration"])
            self.assertEqual(len(shorts), 3)
            self.assertLessEqual(sum(item["end"] - item["start"] for item in long), 660 + .001)
            self.assertGreater(max(item["end"] for item in candidates), 1750)


if __name__ == "__main__":
    unittest.main()
