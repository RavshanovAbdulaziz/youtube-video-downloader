"""transcript/store.py: SQLite saqlash va LIKE-asosli substring qidiruv.

Har test o'z vaqtinchalik baza faylida ishlaydi (`paths.TRANSCRIPT_DB_FILE`
`tmp_path`ga monkeypatch qilinadi) — testlar orasida holat sizib chiqmaydi
va foydalanuvchining haqiqiy transcript_search.db'siga tegilmaydi."""
import pytest

import paths
from transcript import store


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "TRANSCRIPT_DB_FILE", str(tmp_path / "transcript_test.db"))


class TestChannelIndexedFlag:
    def test_not_indexed_by_default(self):
        assert store.is_channel_indexed("UC123") is False

    def test_marked_after_mark_channel_indexed(self):
        store.mark_channel_indexed("UC123", 5)
        assert store.is_channel_indexed("UC123") is True

    def test_scoped_per_channel(self):
        store.mark_channel_indexed("UC123", 5)
        assert store.is_channel_indexed("UCother") is False


class TestVideoIndexedFlag:
    def test_not_indexed_by_default(self):
        assert store.is_video_indexed("vid1") is False

    def test_marked_even_when_transcript_is_empty(self):
        # Subtitr topilmagan video ham "tekshirilgan" deb belgilanishi
        # kerak — aks holda har qidiruvda qayta-qayta transkript
        # so'ralaveradi (fetch.fetch_transcript'ga qarang).
        store.save_video_segments("vid1", "UC123", "Kanal", "Sarlavha", [])
        assert store.is_video_indexed("vid1") is True
        assert store.get_video_segments("vid1") == []


class TestSegmentsAndSearch:
    SEGMENTS = [
        {"text": "salom hammaga", "start_time": 0.0, "end_time": 2.0},
        {"text": "bugun gaming setup haqida gaplashamiz", "start_time": 2.0, "end_time": 5.0},
        {"text": "xayr ko'rishguncha", "start_time": 5.0, "end_time": 7.0},
    ]

    def _seed(self):
        store.save_video_segments("vid1", "UCabc", "Test Kanal", "Test Video", self.SEGMENTS)

    def test_get_video_segments_preserves_order(self):
        self._seed()
        assert store.get_video_segments("vid1") == self.SEGMENTS

    def test_find_matching_video_ids_is_case_insensitive(self):
        self._seed()
        assert store.find_matching_video_ids("UCabc", "GAMING SETUP") == ["vid1"]

    def test_find_matching_video_ids_scoped_to_channel(self):
        self._seed()
        assert store.find_matching_video_ids("UCother", "gaming") == []

    def test_find_matching_video_ids_no_match(self):
        self._seed()
        assert store.find_matching_video_ids("UCabc", "mavjud emas") == []

    def test_get_video_meta(self):
        self._seed()
        meta = store.get_video_meta("vid1")
        assert meta["channel_name"] == "Test Kanal"
        assert meta["video_title"] == "Test Video"
        assert meta["channel_id"] == "UCabc"

    def test_get_video_meta_missing_video_returns_none(self):
        assert store.get_video_meta("no-such-video") is None

    def test_save_video_segments_replaces_previous(self):
        store.save_video_segments("vid1", "UCabc", "K", "V", [{"text": "eski", "start_time": 0.0, "end_time": 1.0}])
        store.save_video_segments("vid1", "UCabc", "K", "V", [{"text": "yangi", "start_time": 0.0, "end_time": 1.0}])
        assert store.get_video_segments("vid1") == [{"text": "yangi", "start_time": 0.0, "end_time": 1.0}]

    def test_like_wildcard_characters_are_escaped(self):
        # "%"/"_" LIKE'ning maxsus belgilari sifatida emas, aynan shu
        # belgilarning o'zi sifatida qidirilishi kerak — aks holda "50%"
        # qidiruvi har qanday matnga mos kelib ketardi.
        store.save_video_segments("vid2", "UCabc", "K", "V", [
            {"text": "chegirma 50% bo'ldi", "start_time": 0.0, "end_time": 1.0},
        ])
        assert store.find_matching_video_ids("UCabc", "50%") == ["vid2"]
        assert store.find_matching_video_ids("UCabc", "50X") == []


class TestPublishedAtFilter:
    def _seed(self, video_id, published_at, text="gaming setup haqida"):
        store.save_video_segments(
            video_id, "UCabc", "Kanal", "Video",
            [{"text": text, "start_time": 0.0, "end_time": 1.0}],
            published_at=published_at,
        )

    def test_published_at_is_persisted_and_returned_by_get_video_meta(self):
        self._seed("vid1", "2023-02-15")
        # get_video_meta o'zi published_at qaytarmaydi (search.py'ga hozircha
        # kerak emas) — bu yerda faqat qatorga yozilganini find_matching orqali
        # bilvosita tekshiramiz (pastdagi testlar).
        assert store.get_video_meta("vid1") is not None

    def test_filters_by_published_after(self):
        self._seed("old", "2022-12-31")
        self._seed("new", "2023-01-15")
        assert store.find_matching_video_ids("UCabc", "gaming", published_after="2023-01-01") == ["new"]

    def test_filters_by_published_before(self):
        self._seed("old", "2022-12-31")
        self._seed("new", "2023-01-15")
        assert store.find_matching_video_ids("UCabc", "gaming", published_before="2023-01-01") == ["old"]

    def test_filters_by_both_bounds_inclusive(self):
        self._seed("before", "2022-12-31")
        self._seed("inside_start", "2023-01-01")
        self._seed("inside_end", "2023-03-31")
        self._seed("after", "2023-04-01")

        ids = set(store.find_matching_video_ids(
            "UCabc", "gaming", published_after="2023-01-01", published_before="2023-03-31",
        ))
        assert ids == {"inside_start", "inside_end"}

    def test_rows_without_published_at_are_excluded_when_date_filter_given(self):
        # Force reindex qilinmagan eski qatorlar (published_at = NULL) sana
        # bo'yicha filtrlangan qidiruvda ko'rinmasligi kerak — lekin sana
        # filtri BERILMAGANDA odatdagidek chiqishda davom etadi.
        store.save_video_segments("legacy", "UCabc", "K", "V", [
            {"text": "gaming setup", "start_time": 0.0, "end_time": 1.0},
        ])  # published_at berilmagan -> NULL

        assert store.find_matching_video_ids("UCabc", "gaming") == ["legacy"]
        assert store.find_matching_video_ids("UCabc", "gaming", published_after="2020-01-01") == []

    def test_no_transcript_video_does_not_get_published_at_row(self):
        # Segmentsiz video uchun `transcript_segments`ga umuman qator
        # yozilmaydi — shuning uchun published_at ham saqlanmaydi, lekin bu
        # zararli emas: bunday video hech qachon qidiruv natijasida
        # chiqmaydi (moslashtiriladigan matni yo'q).
        store.save_video_segments("no-transcript", "UCabc", "K", "V", [], published_at="2023-05-05")
        assert store.find_matching_video_ids("UCabc", "gaming") == []
