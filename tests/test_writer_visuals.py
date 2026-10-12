"""Seleção editorial de imagens oficiais, sem rede, modelos ou arquivos pessoais."""
import unittest
from unittest.mock import MagicMock, patch

from leonida import writer


def screen(group, number):
    return {"group": group, "name": f"{group}_{number:02d}",
            "url": f"https://www.rockstargames.com/VI/_next/static/media/{group}_{number:02d}.jpg"}


def story(title="Lucia ganha novas imagens em GTA VI"):
    return {"id": "a1", "title": title, "title_pt": title, "title_en": title,
            "summary": "Detalhes da matéria precisam de revisão.",
            "sources": [{"url": "https://example.test/article", "name": "Fonte", "lang": "pt"}]}


class WriterVisualTests(unittest.TestCase):
    def test_library_precedes_article_image_and_infers_lucia(self):
        lucia = screen("Lucia_Caminos", 1)
        with patch.object(writer.media, "sync_rockstar_library", return_value=[screen("Jason_Duval", 1), lucia]), \
                patch.object(writer.media, "page_meta") as metadata:
            self.assertEqual(writer.pick_image(story(), "Vice_City"), lucia["url"])
            metadata.assert_not_called()

    def test_topic_groups_do_not_pick_unrelated_characters(self):
        vice = screen("Vice_City", 1)
        with patch.object(writer.media, "sync_rockstar_library", return_value=[screen("Jason_Duval", 1), vice]):
            self.assertEqual(writer.pick_image(story(), "Lucia_Caminos"), vice["url"])
        with patch.object(writer.media, "sync_rockstar_library", return_value=[screen("Jason_Duval", 1)]), \
                patch.object(writer.media, "page_meta", return_value={}):
            self.assertEqual(writer.pick_image(story(), "Lucia_Caminos"), "")

    def test_large_external_og_image_is_not_accepted(self):
        with patch.object(writer.media, "sync_rockstar_library", return_value=[]), \
                patch.object(writer.media, "page_meta", return_value={"image": "https://cdn.test/lucia.png"}), \
                patch.object(writer.media, "fetch") as fetch:
            self.assertEqual(writer.pick_image(story(), "Lucia_Caminos"), "")
            fetch.assert_not_called()

    def test_official_article_image_is_a_fallback(self):
        official = screen("Lucia_Caminos", 1)["url"]
        image = MagicMock(width=1920, height=1080)
        image.__enter__.return_value = image
        with patch.object(writer.media, "sync_rockstar_library", side_effect=RuntimeError("offline")), \
                patch.object(writer.media, "page_meta", return_value={"image": official}), \
                patch.object(writer.media, "fetch", return_value="unused"), \
                patch("PIL.Image.open", return_value=image):
            self.assertEqual(writer.pick_image(story(), "Lucia_Caminos"), official)

    def test_small_official_article_image_is_rejected(self):
        official = screen("Lucia_Caminos", 1)["url"]
        image = MagicMock(width=1920, height=240)
        image.__enter__.return_value = image
        with patch.object(writer.media, "sync_rockstar_library", return_value=[]), \
                patch.object(writer.media, "page_meta", return_value={"image": official}), \
                patch.object(writer.media, "fetch", return_value="unused"), \
                patch("PIL.Image.open", return_value=image):
            self.assertEqual(writer.pick_image(story(), "Lucia_Caminos"), "")

    def test_official_host_cannot_be_spoofed_by_url_substring(self):
        self.assertFalse(writer._official_image("https://rockstargames.com.evil.test/VI/photo.jpg"))
        self.assertFalse(writer._official_image("https://evil.test/VI/photo.jpg?rockstargames.com"))
        self.assertFalse(writer._official_image("http://www.rockstargames.com/VI/photo.jpg"))
        self.assertFalse(writer._official_image("https://media-rockstargames-com.akamaized.net.evil.test/photo.jpg"))
        self.assertFalse(writer._official_image("https://user:password@media.rockstargames.com/photo.jpg"))

    def test_gta_online_uses_official_newswire_image_without_vi_path(self):
        official = "https://media-rockstargames-com.akamaized.net/newswire/halloween.jpg"
        image = MagicMock(width=1920, height=1080)
        image.__enter__.return_value = image
        source = story("GTA Online recebe novidades de Halloween")
        with patch.object(writer.media, "sync_rockstar_library") as library, \
                patch.object(writer.media, "page_meta", return_value={"image": official}), \
                patch.object(writer.media, "fetch", return_value="unused"), \
                patch("PIL.Image.open", return_value=image):
            self.assertEqual(writer.pick_image(source, "Vice_City"), official)
            self.assertEqual(writer.pick_visuals(source, "Vice_City", official), [])
            library.assert_not_called()

    def test_gta_online_and_v_never_fall_back_to_gta_vi_screenshots(self):
        for title in ("GTA Online recebe novidades", "GTA V ganha atualização", "Novo mod de GTA5"):
            with self.subTest(title=title), \
                    patch.object(writer.media, "sync_rockstar_library", return_value=[screen("Vice_City", 1)]) as library, \
                    patch.object(writer.media, "page_meta", return_value={}):
                self.assertEqual(writer.pick_image(story(title), "Vice_City"), "")
                library.assert_not_called()

    def test_explicit_gta_vi_takes_priority_over_online_reference(self):
        self.assertEqual(writer._game_topic(story("GTA VI terá novidades inspiradas em GTA Online")), "GTA VI")
        self.assertEqual(writer._game_topic(story("GTA6: o que veio de GTA5")), "GTA VI")
        self.assertEqual(writer.draft_template(story("GTA Online recebe novidades"))["pt"]["kicker"], "GTA Online")

    def test_visuals_are_distinct_and_exclude_the_cover(self):
        items = [screen("Lucia_Caminos", n) for n in range(1, 4)] + [screen("Vice_City", n) for n in range(1, 3)]
        with patch.object(writer.media, "sync_rockstar_library", return_value=[*items, items[0]]):
            cover = writer.pick_image(story(), "Vice_City")
            visuals = writer.pick_visuals(story(), "Vice_City", cover)
        urls = [item["image"] for item in visuals]
        self.assertEqual(len(urls), 3)
        self.assertEqual(len(set(urls)), 3)
        self.assertNotIn(cover, urls)
        self.assertTrue(all(item["credit"] == "Rockstar Games" for item in visuals))
        self.assertTrue(all(item["label"] == "Imagem oficial ilustrativa" for item in visuals))

    def test_inference_covers_two_characters_and_places(self):
        self.assertEqual(writer.image_hint(story("Jason e Lucia em GTA VI")), "Jason_and_Lucia")
        self.assertEqual(writer.image_hint(story("Detalhes de Jason em GTA VI")), "Jason_Duval")
        self.assertEqual(writer.image_hint(story("Novidades em Port Gellhorn")), "Port_Gellhorn")
        self.assertEqual(writer.image_hint(story("Detalhes de GTA VI"), "Grassrivers"), "Grassrivers")

    def test_fallback_shortens_on_word_boundaries(self):
        title = "Lucia aparece em uma nova sequência oficial com detalhes interessantes para os jogadores brasileiros"
        result = writer.draft_template({**story(title), "summary": "uma palavra " * 30})
        for lang in ("pt", "en"):
            self.assertLessEqual(len(result[lang]["headline"]), 70)
            self.assertLessEqual(len(result[lang]["summary"]), 115)
            self.assertTrue(result[lang]["headline"].endswith("…"))
            original_words = title.split()
            shortened_words = result[lang]["headline"].removesuffix("…").split()
            self.assertEqual(shortened_words, original_words[:len(shortened_words)])
        self.assertTrue(result["needs_review"])
        self.assertEqual(result["pt"]["facts"], [])

    def test_fallback_explicit_feed_is_neutral_in_all_output_text(self):
        result = writer.draft_template(story("Latest leaked GTA 6 video shows Lucia fully naked"))
        self.assertEqual(result["pt"]["headline"], "Relato não confirmado sobre GTA VI")
        self.assertEqual(result["en"]["headline"], "Unconfirmed GTA VI report")
        self.assertEqual(result["tag"], "vazamento")
        for lang in ("pt", "en"):
            self.assertNotIn("naked", str(result[lang]).lower())
        self.assertEqual(result["image_hint"], "Lucia_Caminos")

    def test_portuguese_leaked_and_rumor_labels_require_review(self):
        self.assertEqual(writer.draft_template(story("Novo vídeo vazado de GTA VI"))["tag"], "vazamento")
        self.assertEqual(writer.draft_template(story("Rumores sobre GTA VI"))["tag"], "rumor")

    def test_new_draft_preserves_full_image_and_has_three_extra_scenes(self):
        items = [screen("Lucia_Caminos", n) for n in range(1, 5)]
        with patch.object(writer.media, "sync_rockstar_library", return_value=items), \
                patch.object(writer, "save") as save:
            result = writer.story_to_post(story(), use_llm=False)
        self.assertEqual(result["layout"], "card")
        self.assertFalse(result["cutout"])
        self.assertFalse(result["foto_limpa"])
        self.assertEqual(len(result["visuals"]), 3)
        self.assertTrue(result["needs_review"])
        self.assertNotIn("slides", result["pt"])
        save.assert_called_once_with(result)

    def test_post_collision_creates_a_new_revision_instead_of_overwriting(self):
        directory = MagicMock()
        directory.__truediv__.return_value.exists.side_effect = [True, True, False]
        with patch.object(writer, "post_dir", return_value=directory) as post_dir:
            self.assertEqual(writer._available_post_id("2026-10-12-draft"), "2026-10-12-draft-v3")
        self.assertEqual([call.args[0] for call in post_dir.call_args_list],
                         ["2026-10-12-draft", "2026-10-12-draft-v2", "2026-10-12-draft-v3"])


if __name__ == "__main__":
    unittest.main()
