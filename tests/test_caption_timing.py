"""Legendas: blocos pelo tempo das palavras, duração mínima, sem sobreposição, sem tags de SRT."""
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from leonida import gameplay_render as gr
from leonida import gfx
from leonida import speech_captions as speech


def dialogue_times(ass_text):
    def seconds(stamp):
        h, m, s = stamp.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)
    return [(seconds(a), seconds(b)) for a, b in re.findall(r"Dialogue: 0,([^,]+),([^,]+),", ass_text)]


class CaptionTiming(unittest.TestCase):
    def test_blocks_follow_word_timestamps(self):
        words = "um dois três quatro cinco seis sete oito nove dez onze doze treze catorze quinze".split()
        timed = [{"start": i * .2 + (3 if i >= 8 else 0), "end": i * .2 + .15 + (3 if i >= 8 else 0), "word": w}
                 for i, w in enumerate(words)]
        cue = {"start": 0, "end": timed[-1]["end"], "text": " ".join(words), "words": timed}
        chunks = speech._subtitle_chunks(cue, gfx.font("bold", 60), 300)
        self.assertGreater(len(chunks), 1)
        second_first_word = " ".join(chunks[1]["lines"]).split()[0]
        self.assertAlmostEqual(chunks[1]["start"], timed[words.index(second_first_word)]["start"])

    def test_edited_text_falls_back_to_proportional_timing(self):
        cue = {"start": 0, "end": 10, "text": "texto revisado diferente " * 6,
               "words": [{"start": 0, "end": 1, "word": "outra"}]}
        chunks = speech._subtitle_chunks(cue, gfx.font("bold", 60), 300)
        self.assertEqual(chunks[0]["start"], 0)
        self.assertEqual(chunks[-1]["end"], 10)

    def test_short_cues_get_minimum_and_never_overlap(self):
        rows = speech.tidy_timing([{"start": 0, "end": .2, "text": "Ah!"},
                                   {"start": .5, "end": 1.5, "text": "Corre"},
                                   {"start": 1.2, "end": 2, "text": "agora"},
                                   {"start": 5, "end": 5.1, "text": "Vai"}])
        self.assertEqual([(r["start"], r["end"]) for r in rows], [(0, .5), (.5, 1.2), (1.2, 2), (5, 5 + speech.MIN_CUE_SECONDS)])

    def test_ass_and_srt_have_no_overlapping_lines(self):
        cues = [{"start": 0, "end": 1.5, "text": "Primeira fala"}, {"start": 1, "end": 1.1, "text": "Opa"},
                {"start": 4, "end": 4.05, "text": "Curta"}]
        with tempfile.TemporaryDirectory() as temp:
            ass = speech.write_ass(cues, Path(temp) / "s.ass")
            times = dialogue_times(ass.read_text(encoding="utf-8"))
            srt = speech.write_srt(cues, Path(temp) / "s.srt").read_text(encoding="utf-8")
        for (a0, a1), (b0, _) in zip(times, times[1:]):
            self.assertLessEqual(a1, b0 + .011)
        self.assertGreaterEqual(times[-1][1] - times[-1][0], speech.MIN_CUE_SECONDS - .011)
        self.assertIn("00:00:04,000 --> 00:00:04,800", srt)

    def test_srt_markup_is_not_burned_into_the_video(self):
        cues = gr._parse_creator_srt("1\n00:00:01,000 --> 00:00:02,000\n"
                                     "<i>Olá</i> {\\an8}<font color=\"red\">mundo</font>\n")
        self.assertEqual(cues[0]["text"], "Olá mundo")

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg necessário")
    def test_music_is_capped_below_the_voice(self):
        ff = shutil.which("ffmpeg")
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp:
            root = Path(temp)
            source, theme = root / "source.mp4", root / "theme.wav"
            subprocess.run([ff, "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i",
                            "color=c=0x1450B4:size=320x180:rate=5:duration=3", "-f", "lavfi", "-i",
                            "sine=frequency=500:sample_rate=48000:duration=3", "-c:v", "libx264",
                            "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(source)], check=True, capture_output=True)
            subprocess.run([ff, "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i",
                            "sine=frequency=150:sample_rate=48000:duration=2", str(theme)], check=True, capture_output=True)
            plan = {"version": 1, "language": "pt", "title": "Volume", "source": {"path": str(source), "credit": "F"},
                    "max_long_seconds": 10, "short_seconds": 45, "long": [{"start": .5, "end": 2.5}], "shorts": []}
            logs = []
            result = gr.render(plan, root / "export", music_mode="custom", music_path=theme, music_volume=1,
                               log=logs.append)
        self.assertEqual(result["music_volume"], gr.MAX_MUSIC_UNDER_VOICE)
        self.assertEqual(result["music_volume_requested"], 1)
        self.assertTrue(any("limitada" in line for line in logs))


if __name__ == "__main__":
    unittest.main()
