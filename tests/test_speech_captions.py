"""Contratos de legendas faladas; testes sem baixar modelos ou enviar áudio."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from leonida import speech_captions as speech
from leonida.config import ROOT


class SpeechCaptionContracts(unittest.TestCase):
    def setUp(self):
        folder = ROOT / ".cache/tests"
        folder.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="speech-", dir=folder)
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)

    def test_cue_validation_rejects_malformed_times_or_text(self):
        for cue in ({"start": 0, "end": float("nan"), "text": "fala"},
                    {"start": -1, "end": 2, "text": "fala"},
                    {"start": 1, "end": 1, "text": "fala"},
                    {"start": 0, "end": 1, "text": {"invented": "text"}},
                    {"start": 0, "end": 1, "text": "  "}):
            with self.subTest(cue=cue), self.assertRaises(ValueError):
                speech.normalize_cues([cue])
        with self.assertRaises(ValueError):
            speech.normalize_cues([{"start": 0, "end": 5, "text": "fala"}], duration=3)

    def test_remap_respects_removed_and_repeated_intervals(self):
        cues = [{"start": 4, "end": 6, "text": "primeira"},
                {"start": 11, "end": 13, "text": "segunda"}]
        remapped = speech.remap_cues(cues, [{"start": 5, "end": 8}, {"start": 10, "end": 14},
                                           {"start": 5, "end": 8}])
        self.assertEqual([(r["start"], r["end"], r["text"]) for r in remapped],
                         [(0, 1, "primeira"), (4, 6, "segunda"), (7, 8, "primeira")])

    def test_word_times_remove_excluded_words(self):
        cues = [{"start": 1, "end": 4, "text": "um dois três", "words": [
            {"start": 1, "end": 2, "word": "um"}, {"start": 2, "end": 3, "word": "dois"},
            {"start": 3, "end": 4, "word": "três"}]}]
        rows = speech.remap_cues(cues, [{"start": 2, "end": 4}])
        self.assertEqual(rows[0]["text"], "dois três")
        self.assertEqual(rows[0]["words"][0]["start"], 0)

    def test_word_time_validation_rejects_corrupt_editable_transcript(self):
        for word in ({"start": 0, "end": float("inf"), "word": "fala"},
                     {"start": 0, "end": 4, "word": "fora"},
                     {"start": 0, "end": 1, "word": {"not": "text"}}):
            with self.subTest(word=word), self.assertRaises(ValueError):
                speech.normalize_cues([{"start": 0, "end": 2, "text": "fala", "words": [word]}])

    def test_frame_rounding_keeps_concat_sync(self):
        cues = [{"start": 10, "end": 11, "text": "fala"}]
        rows = speech.remap_cues(cues, [{"start": 0, "end": 1.01}, {"start": 10, "end": 11}], frame_rate=30)
        self.assertAlmostEqual(rows[0]["start"], 31 / 30)

    def test_ass_two_lines_and_safe_position(self):
        out = self.path / "fala.ass"
        speech.write_ass([{"start": 0, "end": 8, "text": " ".join(["Palavra"] * 45)}], out,
                         y=1346, max_width=866)
        dialogues = [line for line in out.read_text(encoding="utf-8").splitlines() if line.startswith("Dialogue:")]
        self.assertGreater(len(dialogues), 1)
        self.assertTrue(all(line.count(r"\N") <= 1 for line in dialogues))
        self.assertTrue(all(r"\pos(540,1346)" in line for line in dialogues))

    def test_editable_text_cannot_inject_ass_overrides(self):
        out = self.path / "safe.ass"
        speech.write_ass([{"start": 0, "end": 2, "text": r"{\move(0,0,50,50)} fala"}], out)
        content = out.read_text(encoding="utf-8")
        self.assertNotIn(r"{\move", content)
        self.assertIn("fala", content)

    def test_unbroken_word_cannot_overflow_the_safe_area(self):
        out = self.path / "too-wide.ass"
        with self.assertRaisesRegex(ValueError, "área segura"):
            speech.write_ass([{"start":0,"end":2,"text":"W"*100}],out)
        self.assertFalse(out.exists())

    def test_srt_preserves_fala_exactly_and_rollover(self):
        out = self.path / "fala.srt"
        speech.write_srt({"segments": [{"start": 59.9997, "end": 61.2, "text": "Ah, caraca!"}]}, out)
        content = out.read_text(encoding="utf-8")
        self.assertIn("00:01:00,000 --> 00:01:01,200", content)
        self.assertIn("Ah, caraca!", content)

    def test_language_is_independent_and_source_audio_is_used(self):
        source = self.path / "source.mp4"
        source.write_bytes(b"localfixture")
        output = self.path / "captions.json"
        commands = []

        def fake_run(command, **kwargs):
            commands.append(command)
            if "--stt-worker" in command:
                request = json.loads(Path(command[-1]).read_text(encoding="utf-8"))
                self.assertEqual(request["language"], "pt")
                Path(request["output"]).write_text(json.dumps({"language": "pt", "segments": [
                    {"start": 0, "end": 1, "text": "fala do criador"}]}), encoding="utf-8")
            return type("Result", (), {"returncode": 0, "stdout": b"", "stderr": b""})()

        with patch.object(speech, "_external_runtime", return_value=(Path("python312.exe"), self.path)), \
                patch.object(speech.shutil, "which", return_value="ffmpeg"), \
                patch.object(speech.subprocess, "run", side_effect=fake_run), \
                patch("leonida.config.CACHE_DIR", self.path):
            result = speech.transcribe(source, output, language="pt", audio_stream=1, log=lambda _: None)
        self.assertIn(str(source.resolve()), commands[0])
        self.assertIn("0:a:1", commands[0])
        self.assertEqual(commands[0].count("-i"), 1)
        self.assertTrue(result["source_audio"])
        self.assertFalse(result["added_music"])
        self.assertEqual(result["subtitle_source"], "spoken_audio")
        self.assertFalse(result["reviewed"])
        self.assertTrue(output.with_suffix(".srt").is_file())

    def test_missing_engine_fails_before_encoding(self):
        source = self.path / "source.mp4"
        source.write_bytes(b"localfixture")
        with patch.object(speech, "_external_runtime", return_value=None), \
                patch.object(speech, "available", return_value=False), \
                patch.object(speech.shutil, "which", return_value="ffmpeg"), \
                patch.object(speech.subprocess, "run") as run:
            with self.assertRaisesRegex(RuntimeError, "requirements-speech"):
                speech.transcribe(source, self.path / "out.json")
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
