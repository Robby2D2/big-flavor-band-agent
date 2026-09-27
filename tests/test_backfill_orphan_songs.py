"""The orphan-song back-fill picks the right id, the right title, and the right scrape (issue #107).

74 playable files had no `songs` row, so they were invisible to search, the DJ,
lyrics and embeddings. What makes the back-fill correct is not the insert -- that
is the scraper's own code path -- but three judgements ahead of it, each of which
a plausible edit would get wrong:

* **which files are songs.** `audio_library/` also holds `produced/` and
  `sessions/` subtrees. Only a top-level `{song_id}_*.mp3` name is a catalog song;
  treating a stem preview as one is how the radio came to show nothing playing
  over audible audio.
* **which scrape to believe.** Only `scraped_songs_20251106_173012.json` still
  describes these songs, and it keys records by slug with the numeric id buried in
  `audio_url`. The 2025-11-10 scrape -- the one the catalog was loaded from, and
  the one a "just use the newest data" change would reach for -- describes none of
  them. A later scrape must never shadow an earlier record for the same id.
* **what to call a song with no scrape record.** 14 of the 74 are named from their
  own ID3 tag, and the filename is only the last resort.
"""
import json

import pytest

from scripts.backfill_orphan_songs import (
    build_scrape_index,
    build_song_data,
    catalog_files,
    find_orphans,
    scraped_record_id,
    song_id_from_name,
    title_from_filename,
    usable_scrape_record,
)


class TestWhichFilesAreSongs:
    @pytest.mark.parametrize("name, expected", [
        ("890_KWE_Lull_Me_Away.mp3", 890),
        ("1063_So_Tired.mp3", 1063),
        ("2538_Aeroplane.MP3", 2538),          # extension case is not identity
        ("guitar.opus", None),                  # a stem preview, not a catalog song
        ("Bury Me Deep.mp3", None),             # pre-id naming, no catalog id
        ("_1063_So_Tired.mp3", None),           # id must lead the name
        ("1063.mp3", None),                     # needs the "{id}_" separator
    ])
    def test_song_id_is_only_read_from_a_top_level_catalog_name(self, name, expected):
        assert song_id_from_name(name) == expected

    def test_non_catalog_names_are_dropped_entirely(self):
        names = ["890_A.mp3", "guitar.opus", "notes.txt", "Bury Me Deep.mp3"]
        assert catalog_files(names) == {890: "890_A.mp3"}

    def test_a_duplicated_id_resolves_the_same_way_whatever_the_listing_order(self):
        forward = catalog_files(["890_A_take.mp3", "890_B_take.mp3"])
        reverse = catalog_files(["890_B_take.mp3", "890_A_take.mp3"])
        assert forward == reverse == {890: "890_A_take.mp3"}

    def test_orphans_are_the_files_the_catalog_has_no_row_for(self, tmp_path):
        for name in ("890_Orphan.mp3", "1752_In_Catalog.mp3", "guitar.opus"):
            (tmp_path / name).write_bytes(b"")
        (tmp_path / "produced").mkdir()
        (tmp_path / "produced" / "2274_Derived.mp3").write_bytes(b"")

        orphans = find_orphans(tmp_path, catalog_ids={1752})

        # 1752 has a row; the subdirectory is not scanned; the .opus is not a song.
        assert orphans == {890: "890_Orphan.mp3"}


class TestWhichScrapeToBelieve:
    @pytest.mark.parametrize("record, expected", [
        ({"id": 838}, 838),
        ({"id": "838"}, 838),
        ({"id": "slug", "audio_url": "https://bigflavorband.com/audio/838/X.mp3"}, 838),
        ({"id": "slug"}, None),
        ({"id": "slug", "audio_url": "https://bigflavorband.com/other/838/X.mp3"}, None),
    ])
    def test_numeric_id_comes_from_the_id_field_or_the_audio_url(self, record, expected):
        assert scraped_record_id(record) == expected

    @pytest.mark.parametrize("record, usable", [
        ({"title": "So Tired"}, True),
        ({"title": "So Tired", "skipped": True}, False),   # a skip marker is not metadata
        ({"title": ""}, False),
        ({}, False),
    ])
    def test_a_record_must_be_named_and_not_a_skip_marker(self, record, usable):
        assert usable_scrape_record(record) is usable

    def test_the_older_scrape_wins_because_the_newer_one_dropped_these_songs(self, tmp_path):
        # Mirrors the real files: the 11-06 scrape describes song 838 by slug, and
        # the 11-10 scrape (which the catalog was loaded from) only marks it skipped.
        (tmp_path / "scraped_songs_20251106_173012.json").write_text(json.dumps([
            {"id": "me_and_bobby", "title": "MeandBobbyMcGee", "session": "Helpless Helped",
             "audio_url": "https://bigflavorband.com/audio/838/x.mp3"}
        ]), encoding="utf-8")
        (tmp_path / "scraped_songs_20251110_113612.json").write_text(json.dumps([
            {"id": 838, "title": "MeandBobbyMcGee", "skipped": True}
        ]), encoding="utf-8")

        index = build_scrape_index(tmp_path)

        assert index[838]["session"] == "Helpless Helped"

    def test_a_later_scrape_cannot_shadow_an_earlier_record_for_the_same_id(self, tmp_path):
        (tmp_path / "scraped_songs_20251106_173012.json").write_text(json.dumps([
            {"id": 838, "title": "Real Title", "session": "Helpless Helped"}
        ]), encoding="utf-8")
        (tmp_path / "scraped_songs_20251110_113612.json").write_text(json.dumps([
            {"id": 838, "title": "Later Title"}
        ]), encoding="utf-8")

        assert build_scrape_index(tmp_path)[838]["title"] == "Real Title"

    def test_an_unreadable_or_unexpected_scrape_does_not_stop_the_run(self, tmp_path):
        (tmp_path / "scraped_songs_broken.json").write_text("{not json", encoding="utf-8")
        (tmp_path / "scraped_songs_object.json").write_text('{"id": 1}', encoding="utf-8")
        (tmp_path / "scraped_songs_20251106_173012.json").write_text(json.dumps([
            {"id": 838, "title": "Real Title"}
        ]), encoding="utf-8")

        assert build_scrape_index(tmp_path) == {838: {"id": 838, "title": "Real Title"}}


class TestWhatToCallASong:
    @pytest.mark.parametrize("name, expected", [
        ("890_KWE_Lull_Me_Away.mp3", "KWE Lull Me Away"),
        ("1063_So_Tired.mp3", "So Tired"),
        ("1600_Here_s_to_You.mp3", "Here s to You"),
    ])
    def test_the_filename_title_drops_the_id_and_the_underscores(self, name, expected):
        assert title_from_filename(name) == expected

    def test_a_scrape_record_wins_and_brings_its_metadata(self):
        scraped = {
            "title": "MeandBobbyMcGee",
            "session": "Helpless Helped",
            "recorded_on": "2/26/04",
            "audio_url": "https://bigflavorband.com/audio/838/x.mp3",
            "instruments": [{"musician": "Rob", "instrument": "Guitar"}],
        }
        data, source = build_song_data(838, "838_MeandBobby.mp3", scraped, tag_title="ID3 Title")

        assert source == "scrape"
        assert data["title"] == "MeandBobbyMcGee"
        assert data["session"] == "Helpless Helped"
        assert data["recorded_on"] == "2/26/04"       # insert_song parses this itself
        assert data["instruments"] == [{"musician": "Rob", "instrument": "Guitar"}]

    def test_a_scrape_record_without_instruments_still_inserts(self):
        data, _ = build_song_data(838, "838_X.mp3", {"title": "X"}, tag_title=None)
        assert data["instruments"] == []

    def test_the_id3_tag_is_used_when_no_scrape_record_exists(self):
        data, source = build_song_data(1162, "1162_Ohio_live.mp3", None, tag_title="Ohio")
        assert (source, data["title"]) == ("id3", "Ohio")

    def test_the_filename_is_the_last_resort(self):
        data, source = build_song_data(1162, "1162_Ohio_live.mp3", None, tag_title=None)
        assert (source, data["title"]) == ("filename", "Ohio live")

    def test_every_payload_carries_the_id_the_file_is_named_for(self):
        for scraped, tag in (({"title": "X"}, None), (None, "X"), (None, None)):
            data, _ = build_song_data(890, "890_X.mp3", scraped, tag)
            assert data["id"] == 890
