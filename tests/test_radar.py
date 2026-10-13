"""Radar: classificação editorial, agrupamento, pontuação, datas e estado — sem rede."""
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from leonida import radar, writer


def item(title, *, source="IGN", official=False, kind=None, weight=1.0, aggregator=False, hours=1):
    text = title
    return {"title": title, "url": f"https://example.test/{abs(hash(title))}", "summary": "",
            "published": time.time() - hours * 3600, "source": source, "feed": source,
            "kind": kind or radar.classify_text(text), "lang": "en", "weight": weight,
            "official": official, "community": False, "aggregator": aggregator, "video": False,
            "thumb": None, "kw_score": 0}


def stories(items):
    return [radar._story(c) for c in radar.merge_by_topic(radar.cluster(items))]


class ClassificationTests(unittest.TestCase):
    def test_leaks_and_rumors(self):
        self.assertEqual(radar.classify_text("GTA 6 leaker Cyberleek posts 25 minutes"), "vazamento")
        self.assertEqual(radar.classify_text("Vazamento de GTA 6 mostra primeira pessoa"), "vazamento")
        self.assertEqual(radar.classify_text("GTA 6 delay rumor resurfaces"), "rumor")
        self.assertEqual(radar.classify_text("Insider says trailer 3 is coming"), "vazamento")
        self.assertEqual(radar.classify_text("Rockstar reveals six radio stations"), "noticia")
        self.assertEqual(radar.classify_text("Insider Gaming: Rockstar reveals the album"), "noticia")

    def test_rumor_never_becomes_official_by_merging(self):
        out = stories([item("Rockstar releases GTA 6 trailer 3", official=True),
                       item("GTA 6 trailer 3 coming soon says insider", source="Kotaku")])
        kinds = sorted(s["kind"] for s in out)
        self.assertEqual(kinds, ["oficial", "vazamento"])
        leak = next(s for s in out if s["kind"] == "vazamento")
        self.assertTrue(leak["blocked"])
        self.assertFalse(leak["official"])

    def test_different_leaks_do_not_become_one_mega_story(self):
        titles = ["GTA 6 leak shows first person camera", "GTA 6 leak reveals GameStop map",
                  "GTA 6 leak shows banking system", "GTA 6 leak lists cheats", "Cyberleek GTA 6 nude scene leak"]
        out = stories([item(t, source=f"S{i}") for i, t in enumerate(titles)])
        self.assertGreaterEqual(len(out), 4)

    def test_confirmed_needs_two_outlets(self):
        one = stories([item("Rockstar North head talks about Leonida wildlife")])
        two = stories([item("Rockstar North head talks about Leonida wildlife"),
                       item("Rockstar North head talks about Leonida wildlife species", source="Eurogamer")])
        self.assertEqual(one[0]["kind"], "noticia")
        self.assertEqual(two[0]["kind"], "confirmada")


class ScoringTests(unittest.TestCase):
    KW = {"boost": {"official": 15, "oficial": 15}, "penalty": {"deal": -25, "review": -10}}

    def test_whole_words_only(self):
        self.assertEqual(radar._score_item("Rockstar official screenshots", self.KW), 15)
        self.assertEqual(radar._score_item("unofficial GTA 6 map", self.KW), 0)
        self.assertEqual(radar._score_item("mapa não oficial de GTA 6", self.KW), 0)
        self.assertEqual(radar._score_item("the ideal dealer for GTA 6 preview", self.KW), 0)
        self.assertEqual(radar._score_item("best GTA 6 deal today", self.KW), -25)

    def test_clean_title_keeps_content(self):
        self.assertEqual(radar._clean_title("GTA 6 - Trailer 3"), "GTA 6 - Trailer 3")
        self.assertEqual(radar._clean_title("GTA 6 ganha rádios - IGN Brasil", "IGN Brasil"), "GTA 6 ganha rádios")


class FeedTests(unittest.TestCase):
    def feed(self, entries):
        parsed = MagicMock()
        parsed.entries = entries
        return parsed

    def test_missing_and_future_dates_are_skipped(self):
        now = time.gmtime()
        future = time.gmtime(time.time() + 86400 * 365)
        entries = [{"title": "GTA 6 com data", "link": "https://a.test/1", "published_parsed": now},
                   {"title": "GTA 6 sem data", "link": "https://a.test/2"},
                   {"title": "GTA 6 no futuro", "link": "https://a.test/3", "published_parsed": future}]
        resp = MagicMock(content=b"")
        with patch.object(radar.requests, "get", return_value=resp), \
                patch.object(radar.feedparser, "parse", return_value=self.feed(entries)):
            got = radar._fetch_feed({"name": "X", "url": "https://x.test"})
        self.assertEqual([g["title"] for g in got], ["GTA 6 com data"])

    def test_flaky_feed_is_retried(self):
        ok = MagicMock(content=b"")
        bad = MagicMock()
        bad.raise_for_status.side_effect = RuntimeError("500")
        entries = [{"title": "GTA 6 ok", "link": "https://a.test/1", "published_parsed": time.gmtime()}]
        with patch.object(radar.requests, "get", side_effect=[bad, ok]), patch.object(radar.time, "sleep"), \
                patch.object(radar.feedparser, "parse", return_value=self.feed(entries)):
            got = radar._fetch_feed({"name": "YT", "url": "https://yt.test"})
        self.assertEqual(got[0]["title"], "GTA 6 ok")

    def test_google_news_uses_real_outlet_and_official_needs_gta6(self):
        now = time.gmtime()
        entries = [{"title": "Grand Theft Auto VI: The Album - Rockstar Games", "link": "https://news.google.com/a",
                    "published_parsed": now, "source": {"title": "Rockstar Games"}},
                   {"title": "Grand Theft Auto V Official Cover Art - Rockstar Games", "link": "https://news.google.com/b",
                    "published_parsed": now, "source": {"title": "Rockstar Games"}}]
        resp = MagicMock(content=b"")
        with patch.object(radar.requests, "get", return_value=resp), \
                patch.object(radar.feedparser, "parse", return_value=self.feed(entries)):
            got = radar._fetch_feed({"name": "Rockstar Newswire (via Google News)", "url": "https://x.test",
                                     "official": True, "aggregator": True})
        self.assertEqual(got[0]["title"], "Grand Theft Auto VI: The Album")
        self.assertEqual(got[0]["source"], "Rockstar Games")
        self.assertTrue(got[0]["official"])
        self.assertFalse(got[1]["official"])


class StateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.patches = [patch.object(radar, "SEEN_FILE", d / "seen.json"),
                        patch.object(radar, "RADAR_FILE", d / "radar.json")]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_corrupted_files_do_not_crash(self):
        radar.SEEN_FILE.write_text("{trunc", encoding="utf-8")
        radar.RADAR_FILE.write_text("", encoding="utf-8")
        self.assertEqual(radar.load_seen(), {})
        self.assertEqual(radar.load_radar(), {"stories": []})

    def test_concurrent_mark_seen_keeps_every_id(self):
        def worker(n):
            for i in range(15):
                radar.mark_seen([f"w{n}-{i}"])
        threads = [threading.Thread(target=worker, args=(n,)) for n in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(json.loads(radar.SEEN_FILE.read_text(encoding="utf-8"))), 90)

    def test_seen_leak_does_not_hide_official_confirmation(self):
        leak = stories([item("GTA 6 first person camera leak footage revealed online")])[0]
        radar._write_json(radar.RADAR_FILE, {"stories": [leak]})
        radar.mark_seen([leak["id"]])
        official = stories([item("Rockstar confirms GTA 6 first person camera footage revealed", official=True)])[0]
        self.assertFalse(radar.is_seen(official))


class WriterBlockTests(unittest.TestCase):
    def test_writer_refuses_leaks_and_rumors(self):
        for kind in ("vazamento", "rumor"):
            with self.assertRaises(writer.BlockedStory):
                writer.story_to_post({"id": "x", "kind": kind, "title": "t", "sources": []}, use_llm=False)

    def test_writer_classifies_old_radar_entries(self):
        with self.assertRaises(writer.BlockedStory):
            writer.check_publishable({"title": "Cyberleek threatens to leak GTA 6 build", "sources": []})

    def test_template_never_tags_leak(self):
        draft = writer.draft_template({"id": "x", "title": "Rockstar reveals radios", "summary": "",
                                       "sources": [{"title": "Rockstar reveals radios", "url": "u", "name": "IGN"}]})
        self.assertIn(draft["tag"], ("oficial", "analise"))


if __name__ == "__main__":
    unittest.main()
