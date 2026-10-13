"""Contrato do motor v2, com cenas/áudio sintéticos restritos aos testes."""
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import wave

import numpy as np
from PIL import Image

from leonida import motion


TEST_SIZE = (180, 320)


def scene(kind="cover", items=0, notes=0):
    bg = Image.new("RGB", TEST_SIZE, (29, 14, 42))
    sprites = [motion.Sprite("brand", "static", 2, Image.new("RGBA", (45, 8), (210, 100, 30)), 10, 12),
               motion.Sprite("headline_0" if kind == "cover" else "title_0", "line", 10,
                             Image.new("RGBA", (100, 9), (10, 245, 60)), 42, 55)]
    for i in range(items):
        y = 80 + i * 12
        sprites.extend([motion.Sprite(f"badge_{i}", "pop", 30 + i * 2,
                                      Image.new("RGBA", (10, 10), (220, 95, 20)), 10, y, i),
                        motion.Sprite(f"item_{i}", "slide", 31 + i * 2,
                                      Image.new("RGBA", (100, 8), (10, 245, 60)), 35, y, i)])
    for i in range(notes):
        sprites.append(motion.Sprite(f"note_{i}", "up", 80 + i,
                                     Image.new("RGBA", (100, 5), (180, 100, 70)), 20, 270 + i * 8))
    return motion.Scene(kind, bg, sprites, enters=kind != "cover")


def photo_scene(color):
    sc = scene("foto")
    sc.sprites.append(motion.Sprite("photo", "photo", 1,
                                    Image.new("RGBA", (130, 160), color), 25, 80))
    return sc


class SmallCanvas(unittest.TestCase):
    def setUp(self):
        for name, value in (("W", TEST_SIZE[0]), ("H", TEST_SIZE[1]), ("CAM_ANCHOR", (90, 144))):
            p = patch.object(motion, name, value)
            p.start()
            self.addCleanup(p.stop)


class PlanTests(unittest.TestCase):
    def test_exact_target_even_with_two_scenes(self):
        scenes = [scene(), scene("cta")]
        with patch.object(motion, "beat_grid", return_value=np.arange(0, 30, 0.49).tolist()):
            starts = motion.plan(scenes, 20, None)
        self.assertAlmostEqual(starts[-1] + scenes[-1].dur, 20, places=8)
        self.assertEqual(round((starts[-1] + scenes[-1].dur) * motion.FPS), 600)

    def test_list_reading_precedes_text_outro(self):
        for period in (0.375, 0.5, 0.68, 0.75):
            scenes = [scene(), scene("list", 9, notes=2), scene("cta")]
            with patch.object(motion, "beat_grid", return_value=np.arange(0.08, 35, period).tolist()):
                starts = motion.plan(scenes, 25, None)
            listing = scenes[1]
            self.assertAlmostEqual(starts[-1] + scenes[-1].dur, 25)
            self.assertGreaterEqual(listing.dur - motion.T - motion.OUTRO - listing.settle + 1e-8, 2.5)
            for left, right in zip(listing.times, listing.times[1:]):
                self.assertGreaterEqual(right - left + 1e-8, 0.45)
                self.assertLessEqual(right - left - 1e-8, 0.7)

    def test_short_and_nonframe_targets_rejected_before_beat_io(self):
        with patch.object(motion, "beat_grid") as beats:
            with self.assertRaisesRegex(ValueError, "mínimo"):
                motion.plan([scene(), scene("list", 15), scene("cta")], 10, None)
            with self.assertRaisesRegex(ValueError, "quadros inteiros"):
                motion.plan([scene()], 4.01, None)
            beats.assert_not_called()

    def test_snap_never_moves_more_than_quarter_second(self):
        self.assertEqual(motion._snap(2, [2.20], 0.25), 2.20)
        self.assertEqual(motion._snap(2, [2.26], 0.25), 2)

    def test_list_entries_use_nearby_real_beats(self):
        sc = scene("list", 3)
        motion._plan_entries(sc)
        first = sc.times[0]
        beats = [first + .2 + .55*i for i in range(3)]
        motion._plan_entries(sc, beats)
        np.testing.assert_allclose(sc.times, beats)

    def test_randomized_plans_keep_exact_target_and_minimum_hold(self):
        rng = np.random.default_rng(28)
        for _ in range(70):
            scenes = [scene("list", int(n), notes=1) for n in rng.integers(1, 12, int(rng.integers(1, 5)))]
            for sc in scenes:
                motion._plan_entries(sc)
            required = sum(sc.settle + 2.5 + motion.OUTRO + motion.T for sc in scenes) - motion.T * (len(scenes) - 1)
            target = math.ceil((required + rng.random() * 4) * 30) / 30
            beats = sorted(rng.uniform(0, target, round(target * 2)))
            with patch.object(motion, "beat_grid", return_value=beats):
                starts = motion.plan(scenes, target, None)
            self.assertAlmostEqual(starts[-1] + scenes[-1].dur, target)
            for sc in scenes:
                self.assertGreaterEqual(sc.dur - motion.T - motion.OUTRO - sc.settle + 1e-8, 2.5)
                self.assertTrue(all(.45 - 1e-8 <= b-a <= .7 + 1e-8 for a,b in zip(sc.times,sc.times[1:])))

    def test_news_targets_reuse_only_distinct_supporting_photos_and_cap_holds(self):
        for target in (30, 35, 40, 45, 60):
            scenes = [scene(), photo_scene((190, 90, 20)), photo_scene((30, 80, 210)),
                      photo_scene((30, 180, 70)), scene("cta")]
            original_images = [(sc.bg.tobytes(), [sp.img.tobytes() for sp in sc.sprites]) for sc in scenes]
            originals = scenes.copy()
            rng = np.random.default_rng(target)
            beats = sorted(rng.uniform(0, target + 1, target * 2))
            with patch.object(motion, "beat_grid", return_value=beats):
                starts = motion.plan(scenes, target, None, log=lambda _: None, max_scene_seconds=7)
            self.assertAlmostEqual(starts[-1] + scenes[-1].dur, target, places=8)
            self.assertEqual(sum(sc.kind == "cover" for sc in scenes), 1)
            self.assertEqual(sum(sc.kind == "cta" for sc in scenes), 1)
            for sc in scenes:
                self.assertLessEqual(sc.dur, 7 + 1e-7)
                self.assertGreaterEqual(sc.dur + 1e-7, motion._scene_minimum(sc))
            for left, right in zip(scenes, scenes[1:]):
                if left.kind == right.kind == "foto":
                    self.assertNotEqual(motion._photo_key(left), motion._photo_key(right))
            for original, pixels in zip(originals, original_images):
                self.assertEqual((original.bg.tobytes(), [sp.img.tobytes() for sp in original.sprites]), pixels)
            # Retakes have independent timing objects, with shared original media.
            for sc in scenes:
                self.assertTrue(any(sc.bg is source.bg for source in originals))
            self.assertEqual(len({id(sp) for sc in scenes for sp in sc.sprites}),
                             sum(len(sc.sprites) for sc in scenes))

    def test_long_cover_and_duplicate_supporting_images_fail_before_beat_io(self):
        for scenes in ([scene()], [scene(), scene("cta")],
                       [scene(), photo_scene((190, 90, 20)), photo_scene((190, 90, 20)), scene("cta")]):
            with patch.object(motion, "beat_grid") as beats:
                with self.assertRaisesRegex(ValueError, "mais imagens ou slides"):
                    motion.plan(scenes, 40, None, log=lambda _: None, max_scene_seconds=7)
                beats.assert_not_called()

    def test_different_labels_on_same_photo_do_not_count_as_new_images(self):
        a, b = photo_scene((190, 90, 20)), photo_scene((190, 90, 20))
        b.sprites[1].img = Image.new("RGBA", (100, 9), (255, 255, 255))
        with patch.object(motion, "beat_grid") as beats:
            with self.assertRaisesRegex(ValueError, "mais imagens ou slides"):
                motion.plan([scene(), a, b, scene("cta")], 40, None,
                            log=lambda _: None, max_scene_seconds=7)
            beats.assert_not_called()

    def test_fit_target_shortens_posts_without_supporting_photos(self):
        for scenes in ([scene()], [scene(), scene("list", 4), scene("cta")],
                       [scene(), photo_scene((190, 90, 20)), photo_scene((190, 90, 20)), scene("cta")]):
            logs = []
            fitted = motion.fit_target(scenes, 45, logs.append, max_scene_seconds=7)
            self.assertLess(fitted, 45)
            self.assertAlmostEqual(fitted * motion.FPS, round(fitted * motion.FPS), places=6)
            self.assertIn("faltam fotos", logs[0])
            with patch.object(motion, "beat_grid", return_value=[]):
                starts = motion.plan(scenes, fitted, None, log=lambda _: None, max_scene_seconds=7)
            self.assertAlmostEqual(starts[-1] + scenes[-1].dur, fitted, places=8)

    def test_fit_target_keeps_request_when_photos_can_fill_it(self):
        scenes = [scene(), photo_scene((190, 90, 20)), photo_scene((30, 80, 210)), scene("cta")]
        logs = []
        self.assertEqual(motion.fit_target(scenes, 45, logs.append, max_scene_seconds=7), 45)
        self.assertEqual(logs, [])

    def test_fit_target_raises_too_short_request_to_reading_minimum(self):
        scenes = [scene(), scene("list", 10)]
        logs = []
        fitted = motion.fit_target(scenes, 5, logs.append)
        self.assertGreater(fitted, 5)
        self.assertIn("precisa desse tempo", logs[0])
        with patch.object(motion, "beat_grid", return_value=[]):
            starts = motion.plan(scenes, fitted, None, log=lambda _: None)
        self.assertAlmostEqual(starts[-1] + scenes[-1].dur, fitted, places=8)

    def test_long_list_retains_reading_and_reports_duration_exception(self):
        scenes = [scene(), photo_scene((190, 90, 20)), scene("list", 12, notes=2),
                  photo_scene((30, 80, 210)), scene("cta")]
        logs = []
        with patch.object(motion, "beat_grid", return_value=[]):
            starts = motion.plan(scenes, 40, None, log=logs.append, max_scene_seconds=7)
        listing = next(sc for sc in scenes if sc.kind == "list")
        self.assertGreater(listing.dur, 7)
        self.assertGreaterEqual(listing.dur - motion.T - motion.OUTRO - listing.settle + 1e-8, 2.5)
        self.assertTrue(any("leitura: cena list" in line for line in logs))
        self.assertAlmostEqual(starts[-1] + scenes[-1].dur, 40)


class DrawingTests(SmallCanvas):
    def test_bounded_news_has_real_visual_changes_and_preserves_loop(self):
        scenes = [scene(), photo_scene((190, 90, 20)), photo_scene((30, 80, 210)), scene("cta")]
        with patch.object(motion, "beat_grid", return_value=[]):
            starts = motion.plan(scenes, 40, None, log=lambda _: None, max_scene_seconds=7)
        first = np.asarray(motion.frame_at(scenes, starts, 0))
        last = np.asarray(motion.frame_at(scenes, starts, 1199))
        np.testing.assert_array_equal(first, last)
        photos = [np.asarray(motion.frame_at(scenes, starts, round((st + sc.settle + 1) * 30)))[110:200, 40:140]
                  for sc, st in zip(scenes, starts) if sc.kind == "foto"]
        self.assertGreaterEqual(len(photos), 4)
        for left, right in zip(photos, photos[1:]):
            self.assertGreater(np.abs(left.astype(int) - right.astype(int)).mean(), 35)

    def test_source_loop_and_actual_hold_equal_static_layers(self):
        scenes = [scene(), scene("list", 5), scene("cta")]
        with patch.object(motion, "beat_grid", return_value=[]):
            starts = motion.plan(scenes, 20, None)
        np.testing.assert_array_equal(np.asarray(motion.frame_at(scenes, starts, 0)),
                                      np.asarray(motion.frame_at(scenes, starts, 599)))
        for sc, start in zip(scenes, starts):
            f = math.floor((start + sc.dur - motion.T - motion.OUTRO) * 30) - 1
            np.testing.assert_array_equal(np.asarray(motion.frame_at(scenes, starts, f)),
                                          np.asarray(motion.static_frame(sc)))
        for f in range(0, 600, 15):
            self.assertGreater(np.asarray(motion.frame_at(scenes, starts, f)).mean(), 10)

    def test_public_frame_at_is_used_by_encoder_iterator(self):
        scenes = [scene()]
        with patch.object(motion, "beat_grid", return_value=[]):
            starts = motion.plan(scenes, 4, None)
        for number, frame in enumerate(motion.render_frames(scenes, starts)):
            np.testing.assert_array_equal(np.asarray(frame), np.asarray(motion.frame_at(scenes, starts, number)))

    def test_punch_scales_media_but_does_not_move_text(self):
        sc = scene()
        sc.dur = 5
        normal = np.asarray(motion._content(sc, 1.3, punch=1).convert("RGB"))
        punch = np.asarray(motion._content(sc, 1.3, punch=1.35).convert("RGB"))
        def text_mask(a):
            return (a[:,:,1] > a[:,:,0].astype(int) + 80) & (a[:,:,1] > a[:,:,2].astype(int) + 80)
        np.testing.assert_array_equal(text_mask(normal), text_mask(punch))

    def test_countdown_pop_keeps_its_right_edge_fixed(self):
        sc = scene()
        sc.dur = 5
        sc.sprites = [motion.Sprite("countdown", "pop", 6, Image.new("RGBA",(50,15),(255,255,255)), 90, 10)]
        for t in np.arange(.46,.95,.025):
            box = motion._hud(sc, float(t), float(t)).getbbox()
            self.assertLessEqual(box[2],140)

    def test_live_countdown_and_signature_remain_pixel_stable(self):
        sc = scene()
        sc.dur = 5
        sc.sprites.extend([
            motion.Sprite("live", "static", 3, Image.new("RGBA", (8, 8), (255, 70, 30, 160)), 60, 12),
            motion.Sprite("countdown", "pop", 6, Image.new("RGBA", (45, 12), (255, 255, 255, 190)), 90, 10),
            motion.Sprite("handle", "static", 90, Image.new("RGBA", (70, 9), (220, 220, 220, 180)), 15, 290),
        ])
        expected = np.asarray(motion._hud(sc, 0, 0))
        for t in (0.3, 0.46, 0.7, 0.94, 1.1, 2.3, 4.9):
            np.testing.assert_array_equal(np.asarray(motion._hud(sc, t, t)), expected)

    def test_dissolve_does_not_carry_text_across_right_safe_area(self):
        scenes = [scene(), scene("list", 3), scene("list", 2)]
        with patch.object(motion, "beat_grid", return_value=[]):
            starts = motion.plan(scenes, 20, None)
        for start in starts[1:]:
            for f in range(math.ceil(start * 30), math.ceil((start + motion.T) * 30)):
                a = np.asarray(motion.frame_at(scenes, starts, f)).astype(int)
                text = (a[:,:,1] > a[:,:,0] + 80) & (a[:,:,1] > a[:,:,2] + 80)
                self.assertFalse(text[:,143:].any(), (start, f))

    def test_dissolve_endpoints_and_midpoint_never_flash_or_blank(self):
        a = Image.new("RGB", TEST_SIZE, (25, 20, 80))
        b = Image.new("RGB", TEST_SIZE, (160, 90, 40))
        np.testing.assert_array_equal(np.asarray(motion._transition("dissolve", a, b, -0.1)), np.asarray(a))
        np.testing.assert_array_equal(np.asarray(motion._transition("dissolve", a, b, 1.1)), np.asarray(b))
        previous = None
        for p in np.linspace(0, 1, round(motion.T * motion.FPS) + 1):
            actual = np.asarray(motion._transition("dissolve", a, b, float(p))).astype(int)
            self.assertTrue(np.all(actual >= np.minimum(np.asarray(a), np.asarray(b))))
            self.assertTrue(np.all(actual <= np.maximum(np.asarray(a), np.asarray(b))))
            if previous is not None:
                self.assertLessEqual(np.abs(actual - previous).max(), 15)
            previous = actual

    def test_transition_retains_title_and_fixed_hud_in_every_frame(self):
        scenes = [scene(), scene("list", 3), scene("list", 2), scene("cta")]
        with patch.object(motion, "beat_grid", return_value=[]):
            starts = motion.plan(scenes, 30, None)
        brand = np.asarray(motion.static_frame(scenes[0]))[12:20, 10:55]
        for start in starts[1:]:
            # Covers the former blank outro as well as all dissolve frames.
            for f in range(math.ceil((start - motion.OUTRO) * 30), math.ceil((start + motion.T) * 30)):
                actual = np.asarray(motion.frame_at(scenes, starts, f)).astype(int)
                title = (actual[55:64,:,1] > actual[55:64,:,0] + 50)
                self.assertGreater(title.sum(), 35, (start, f))
                np.testing.assert_array_equal(actual[12:20, 10:55], brand)

    def test_short_form_targets_keep_exact_loop_and_settled_composition(self):
        for target in (30, 40, 60):
            scenes = [scene(), scene("list", 3), scene("cta")]
            with patch.object(motion, "beat_grid", return_value=[]):
                starts = motion.plan(scenes, target, None)
            np.testing.assert_array_equal(np.asarray(motion.frame_at(scenes, starts, 0)),
                                          np.asarray(motion.frame_at(scenes, starts, target * 30 - 1)))
            for sc, start in zip(scenes, starts):
                f = math.floor((start + sc.dur - motion.T - motion.OUTRO) * 30) - 1
                np.testing.assert_array_equal(np.asarray(motion.frame_at(scenes, starts, f)),
                                              np.asarray(motion.static_frame(sc)))

    def test_music_pulse_has_continuous_attack_and_return(self):
        sc = scene()
        sc.pulses = [1.0]
        self.assertEqual(motion._pulse(sc, 1.0), 0)
        self.assertAlmostEqual(motion._pulse(sc, 1.4), 0)
        self.assertLess(motion._pulse(sc, 1.0 + 1e-4), 1e-8)
        self.assertLess(motion._pulse(sc, 1.4 - 1e-4), 1e-8)
        self.assertAlmostEqual(motion._pulse(sc, 1.2), 0.004)

    def test_scene_from_uses_finished_background_without_reprocessing(self):
        bg = Image.new("RGBA", TEST_SIZE, (40, 25, 60))
        layer = SimpleNamespace(name="bg", image=bg, order=0, extra={}, step=None, anim="kenburns")
        with patch.object(motion.gfx, "finish", side_effect=AssertionError("double finish")):
            actual = motion.scene_from(SimpleNamespace(layers=[layer]), "cover")
        np.testing.assert_array_equal(np.asarray(actual.bg), np.asarray(bg.convert("RGB")))


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg/ffprobe necessários")
class BuildTests(SmallCanvas):
    def audio(self, folder):
        path = Path(folder) / "test-tone.wav"
        rate = 11025
        samples = (np.sin(np.arange(rate * 5) * 2*np.pi*330/rate) * 12000).astype("<i2")
        with wave.open(str(path), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(rate)
            audio.writeframes(samples.tobytes())
        return path

    def test_real_encode_exact_duration_audio_and_fades(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            path = Path(folder) / "test.mp4"
            audio = self.audio(folder)
            with patch.object(motion.music, "theme_path", return_value=audio), \
                    patch.object(motion, "beat_grid", return_value=[]):
                motion.build([scene()], path, target=4, log=lambda _:None)
            meta = json.loads(subprocess.check_output([shutil.which("ffprobe"), "-v", "error", "-show_streams",
                                                      "-show_format", "-of", "json", str(path)], text=True))
            video = next(s for s in meta["streams"] if s["codec_type"] == "video")
            sound = next(s for s in meta["streams"] if s["codec_type"] == "audio")
            self.assertEqual((video["codec_name"],video["profile"],video["r_frame_rate"],int(video["nb_frames"])),
                             ("h264","High","30/1",120))
            self.assertEqual(sound["codec_name"],"aac")
            self.assertAlmostEqual(float(meta["format"]["duration"]),4,places=3)
            raw = subprocess.check_output([shutil.which("ffmpeg"),"-v","error","-i",str(path),"-vn","-ac","1",
                                           "-ar","8000","-f","f32le","-"])
            pcm = np.frombuffer(raw,dtype="<f4")
            rms = lambda x: np.sqrt(np.mean(x*x))
            self.assertLess(rms(pcm[:800]),rms(pcm[8000:8800])*.3)
            self.assertLess(rms(pcm[31200:32000]),rms(pcm[8000:8800])*.3)

    def test_midrender_failure_preserves_old_video_and_other_work(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            path = Path(folder)/"test.mp4"
            path.write_bytes(b"previous-valid-output")
            unrelated = Path(folder)/".work"
            unrelated.mkdir()
            keep = unrelated/"another-build.txt"
            keep.write_text("preserve")
            audio = self.audio(folder)
            with patch.object(motion.music,"theme_path",return_value=audio), \
                    patch.object(motion,"beat_grid",return_value=[]), \
                    patch.object(motion,"render_frames",side_effect=RuntimeError("injected render failure")):
                with self.assertRaisesRegex(RuntimeError,"injected render failure"):
                    motion.build([scene()],path,target=4,log=lambda _:None)
            self.assertEqual(path.read_bytes(),b"previous-valid-output")
            self.assertEqual(keep.read_text(),"preserve")
            self.assertEqual(list(Path(folder).glob(".motion-*")),[])

    def test_short_target_leaves_output_untouched(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            path = Path(folder)/"test.mp4"
            path.write_bytes(b"old")
            with patch.object(motion.music,"theme_path",return_value=self.audio(folder)), \
                    patch.object(motion.subprocess,"Popen") as encoder:
                with self.assertRaises(ValueError):
                    motion.build([scene(),scene("list",10)],path,target=5,log=lambda _:None)
                encoder.assert_not_called()
            self.assertEqual(path.read_bytes(),b"old")

    def test_long_cover_cannot_replace_existing_export(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            path = Path(folder) / "test.mp4"
            path.write_bytes(b"previous-valid-output")
            with patch.object(motion.music, "theme_path", return_value=self.audio(folder)), \
                    patch.object(motion.subprocess, "Popen") as encoder:
                with self.assertRaisesRegex(ValueError, "mais imagens ou slides"):
                    motion.build([scene()], path, target=40, log=lambda _: None, max_scene_seconds=7)
                encoder.assert_not_called()
            self.assertEqual(path.read_bytes(), b"previous-valid-output")


if __name__ == "__main__":
    unittest.main()
