"""transcript/find_source.py: klip (Shorts) qaysi streamdan olinganini
aniqlash. Tarmoqqa chiqilmaydi — `fetch.fetch_transcript` monkeypatch
qilinadi, indeks esa vaqtinchalik SQLite fayliga haqiqiy `store` orqali
yoziladi (mantiq aynan SQL qidiruv + ballash ustida ishlaydi)."""
import pytest

import paths
from transcript import fetch, find_source, store


class TestParseVideoId:
    @pytest.mark.parametrize("ref,expected", [
        ("https://youtube.com/shorts/B4uytxWGWEk?si=knCqzQp4JD9k54qS", "B4uytxWGWEk"),
        ("https://www.youtube.com/watch?v=B4uytxWGWEk", "B4uytxWGWEk"),
        ("https://youtu.be/B4uytxWGWEk", "B4uytxWGWEk"),
        ("https://www.youtube.com/live/B4uytxWGWEk", "B4uytxWGWEk"),
        ("https://www.youtube.com/embed/B4uytxWGWEk", "B4uytxWGWEk"),
        ("B4uytxWGWEk", "B4uytxWGWEk"),
    ])
    def test_parses_supported_forms(self, ref, expected):
        assert find_source.parse_video_id(ref) == expected

    @pytest.mark.parametrize("bad", ["", "   ", "https://example.com/video"])
    def test_rejects_unparseable(self, bad):
        with pytest.raises(ValueError):
            find_source.parse_video_id(bad)


class TestTerms:
    def test_drops_stopwords_and_short_words(self):
        assert find_source._terms("The bro is a marker on it") == ["marker"]

    def test_lowercases_and_splits_punctuation(self):
        assert find_source._terms("Marker, MARKER! marker?") == ["marker", "marker", "marker"]

    def test_drops_caption_artifacts(self):
        # "[Music]" nutq emas — deyarli har bir videoda uchraydi, ya'ni
        # moslikka dalil qo'shmasdan faqat ballni shishiradi.
        assert find_source._terms(
            "[Music] marker [Applause] >> sharpie (laughs)"
        ) == ["marker", "sharpie"]


class TestIdf:
    def test_word_in_every_video_is_worthless(self):
        # Eski formula bu holatda ~0.7 ball berardi va o'nlab shunday so'z
        # yig'ilib xato g'olib chiqarardi.
        assert find_source._idf(65, 65) < 0.05

    def test_rare_word_outweighs_common_one(self):
        assert find_source._idf(65, 1) > 5 * find_source._idf(65, 40)


class TestFindSource:
    @pytest.fixture(autouse=True)
    def _isolated_db(self, tmp_path, monkeypatch):
        monkeypatch.setattr(paths, "TRANSCRIPT_DB_FILE", str(tmp_path / "find_source_test.db"))

    def _seed_stream(self, video_id, title, segments, channel_id="UCWsDFcIhY2DBi3GB5uykGXA", published_at="2025-10-21"):
        store.save_video_segments(
            video_id, channel_id, "IShowSpeed", title,
            [{"text": t, "start_time": float(s), "end_time": float(s) + 3.0} for s, t in segments],
            published_at,
        )

    def _clip(self, monkeypatch, text, languages_with_transcript=("en",)):
        """Klip transkriptini soxtalashtiradi — faqat berilgan tillarda mavjud."""
        def fake_fetch(video_id, languages=None):
            lang = (languages or ["en"])[0]
            if lang not in languages_with_transcript:
                return None
            return [{"text": text, "start": 0.0, "duration": 5.0}]

        monkeypatch.setattr(fetch, "fetch_transcript", fake_fetch)

    def test_finds_the_stream_containing_the_clip_words(self, monkeypatch):
        # Ikkita stream: biri klipdagi xarakterli so'zlarni o'z ichiga oladi.
        self._seed_stream("stream_wrong", "Gaming stream", [
            (10, "we are playing minecraft today chat"),
            (20, "this boss fight is really hard"),
        ])
        self._seed_stream("stream_right", "45 million in Thailand", [
            (5900, "why did he give me these shoes"),
            (5950, "whose shoes are these bro"),
            (6060, "can you sign it please i do not have a marker"),
            (6070, "marker marker marker give it to me"),
        ])
        self._clip(monkeypatch, "why do he give me his shoes i don't have a marker marker marker sign")

        res = find_source.find_source("B4uytxWGWEk", channel_id="UCWsDFcIhY2DBi3GB5uykGXA")

        assert res["found"] is True
        assert res["match"]["video_id"] == "stream_right"
        assert res["match"]["video_title"] == "45 million in Thailand"
        assert res["match"]["published_at"] == "2025-10-21"

    def test_reports_timestamp_of_the_best_window(self, monkeypatch):
        self._seed_stream("stream_right", "Stream", [
            (100, "totally unrelated chatter about food"),
            (6000, "shoes marker sign please"),
            (6030, "marker marker shoes"),
        ])
        self._clip(monkeypatch, "shoes marker marker sign")

        res = find_source.find_source("B4uytxWGWEk", channel_id="UCWsDFcIhY2DBi3GB5uykGXA")

        # Moslik 6000s atrofidagi oynada bo'lishi kerak, boshidagi shovqinda emas.
        assert 5940 <= res["match"]["start_time"] <= 6030
        assert res["match"]["url"].endswith(f"&t={int(res['match']['start_time'])}s")

    def test_rare_words_outweigh_common_ones(self, monkeypatch):
        # "speed" hamma videoda bor (foydasiz), "marker" faqat bittasida.
        for i in range(4):
            self._seed_stream(f"noise{i}", f"Noise {i}", [
                (10, "speed speed speed speed speed"),
            ])
        self._seed_stream("target", "Target", [
            (500, "speed marker"),
        ])
        self._clip(monkeypatch, "speed marker")

        res = find_source.find_source("B4uytxWGWEk", channel_id="UCWsDFcIhY2DBi3GB5uykGXA")

        assert res["match"]["video_id"] == "target"

    def test_not_found_when_index_has_nothing_similar(self, monkeypatch):
        self._seed_stream("stream", "Stream", [(10, "completely different subject matter")])
        self._clip(monkeypatch, "marker shoes autograph")

        res = find_source.find_source("B4uytxWGWEk", channel_id="UCWsDFcIhY2DBi3GB5uykGXA")

        assert res["found"] is False
        assert res["match"] is None

    def test_weak_but_real_match_is_found_but_not_confident(self, monkeypatch):
        # Bir nechta xarakterli so'z mos keldi va raqibidan ancha ustun —
        # natija qaytadi, lekin "confident" bo'lish uchun dalil yetarli emas.
        self._seed_stream("weak_target", "Target", [(100, "autograph marker sharpie")])
        self._seed_stream("other", "Other", [(50, "helicopter")])
        self._clip(monkeypatch, "autograph marker sharpie helicopter")

        res = find_source.find_source("B4uytxWGWEk", channel_id="UCWsDFcIhY2DBi3GB5uykGXA")

        assert res["found"] is True
        assert res["match"]["video_id"] == "weak_target"
        assert res["confident"] is False

    def test_single_common_word_is_not_reported_as_a_match(self, monkeypatch):
        # Bitta so'zning ustma-tushligi dalil emas — avval bu "topildi"
        # deb qaytardi va foydalanuvchini chalg'itardi.
        self._seed_stream("stream", "Stream", [(10, "shoes")])
        self._clip(monkeypatch, "shoes")

        res = find_source.find_source("B4uytxWGWEk", channel_id="UCWsDFcIhY2DBi3GB5uykGXA")

        assert res["found"] is False
        assert res["match"] is None

    def test_no_match_when_winner_barely_beats_runner_up(self, monkeypatch):
        # ASOSIY REGRESSIYA TESTI: manba stream indekslanmagan bo'lsa,
        # algoritm baribir "eng yaxshi" videoni topadi — lekin u raqiblaridan
        # ajralib turmaydi. Bunday holatda javob qaytarilmasligi kerak
        # (avval aynan shu sabab bir xil uzun stream har safar javob bo'lardi).
        for i in range(6):
            self._seed_stream(f"stream{i}", f"Stream {i}", [
                (10, "airport luggage passport terminal"),
            ])
        self._clip(monkeypatch, "airport luggage passport terminal")

        res = find_source.find_source("B4uytxWGWEk", channel_id="UCWsDFcIhY2DBi3GB5uykGXA")

        assert res["found"] is False
        assert res["match"] is None

    def test_one_near_duplicate_rival_does_not_hide_a_real_match(self, monkeypatch):
        # Nega margin 2-o'ringa emas, MEDIANAGA nisbatan o'lchanadi: bitta
        # yaqin raqib ("Day 18 of 35" kabi qo'shni stream) 2-o'rinni egallab,
        # to'g'ri javobni ko'rinmas qilib qo'yishi mumkin edi.
        self._seed_stream("true_source", "Manba", [
            (600, "sharpie autograph helicopter trombone kayak"),
        ])
        self._seed_stream("near_duplicate", "Qo'shni qism", [
            (600, "sharpie autograph helicopter"),
        ])
        for i in range(5):
            self._seed_stream(f"unrelated{i}", f"Boshqa {i}", [(10, "sharpie")])
        self._clip(monkeypatch, "sharpie autograph helicopter trombone kayak")

        res = find_source.find_source("B4uytxWGWEk", channel_id="UCWsDFcIhY2DBi3GB5uykGXA")

        assert res["found"] is True
        assert res["match"]["video_id"] == "true_source"

    def test_repeated_word_cannot_dominate_the_score(self, monkeypatch):
        # Klipda 8 marta takrorlangan bitta so'z, uchta har xil so'zdan
        # ustun kelmasligi kerak.
        self._seed_stream("repeat_only", "Repeat", [
            (10, "banana banana banana banana banana banana banana banana"),
        ])
        self._seed_stream("varied", "Varied", [(10, "banana trombone kayak")])
        self._clip(monkeypatch, "banana banana banana banana banana banana banana banana trombone kayak")

        res = find_source.find_source("B4uytxWGWEk", channel_id="UCWsDFcIhY2DBi3GB5uykGXA")

        assert res["found"] is True
        assert res["match"]["video_id"] == "varied"

    def test_falls_back_to_second_language_when_index_is_in_it(self, monkeypatch):
        # Indeks o'zbekcha (eski yozuvlar), klipning inglizchasi mos kelmaydi
        # — modul o'zbekcha variantni ham sinab ko'rishi kerak.
        self._seed_stream("uz_stream", "Tailand", [
            (6060, "imzo qo'ya olasizmi menda marker yo'q"),
            (6070, "marker marker marker menga bering"),
        ])

        def fake_fetch(video_id, languages=None):
            lang = (languages or ["en"])[0]
            text = ("i don't have a marker sign for me" if lang == "en"
                    else "imzo qo'ya olasizmi menda marker yo'q marker marker")
            return [{"text": text, "start": 0.0, "duration": 5.0}]

        monkeypatch.setattr(fetch, "fetch_transcript", fake_fetch)

        res = find_source.find_source("B4uytxWGWEk", channel_id="UCWsDFcIhY2DBi3GB5uykGXA")

        assert res["found"] is True
        assert res["clip_language"] == "uz"
        assert res["match"]["video_id"] == "uz_stream"

    def test_raises_blocked_when_clip_transcript_is_blocked_in_all_languages(self, monkeypatch):
        def fake_fetch(video_id, languages=None):
            raise fetch.TranscriptFetchBlocked("HTTP Error 429")

        monkeypatch.setattr(fetch, "fetch_transcript", fake_fetch)

        with pytest.raises(fetch.TranscriptFetchBlocked):
            find_source.find_source("B4uytxWGWEk", channel_id="UCWsDFcIhY2DBi3GB5uykGXA")

    def test_search_is_scoped_to_channel_when_given(self, monkeypatch):
        self._seed_stream("other_channel", "Boshqa kanal", [
            (10, "shoes marker sign please give"),
        ], channel_id="UCq3d1qBH7Ow9U8VtLwUn0aA")
        self._clip(monkeypatch, "shoes marker sign please give")

        res = find_source.find_source("B4uytxWGWEk", channel_id="UCWsDFcIhY2DBi3GB5uykGXA")

        assert res["found"] is False

    def test_resolves_handle_to_channel_id(self, monkeypatch):
        # UI'da kanal maydoni qidiruv bloki bilan umumiy — u yerga
        # "@handle" kiritish tabiiy. Indeks esa xom UC... ID bo'yicha
        # filtrlanadi, ya'ni handle avval ID'ga aylantirilishi kerak,
        # aks holda javob aldamchi "manba topilmadi" bo'lardi.
        self._seed_stream("stream_right", "Tailand", [
            (6060, "shoes marker sign please give"),
        ])
        self._clip(monkeypatch, "shoes marker sign please give")
        monkeypatch.setattr(fetch, "resolve_channel", lambda ref: {
            "channel_id": "UCWsDFcIhY2DBi3GB5uykGXA", "title": "IShowSpeed",
            "uploads_playlist_id": "UUWsDFcIhY2DBi3GB5uykGXA",
        })

        res = find_source.find_source("B4uytxWGWEk", channel_id="@IShowSpeed")

        assert res["found"] is True
        assert res["match"]["video_id"] == "stream_right"

    def test_raw_channel_id_is_not_resolved_over_the_network(self, monkeypatch):
        # Xom ID berilganda kvota sarflanmasligi kerak.
        self._seed_stream("stream_right", "Tailand", [(6060, "shoes marker sign please give")])
        self._clip(monkeypatch, "shoes marker sign please give")

        def boom(ref):
            raise AssertionError("xom ID uchun resolve_channel chaqirilmasligi kerak")

        monkeypatch.setattr(fetch, "resolve_channel", boom)

        res = find_source.find_source("B4uytxWGWEk", channel_id="UCWsDFcIhY2DBi3GB5uykGXA")

        assert res["found"] is True

    def test_searches_all_channels_when_channel_not_given(self, monkeypatch):
        self._seed_stream("other_channel", "Boshqa kanal", [
            (10, "shoes marker sign please give"),
        ], channel_id="UCq3d1qBH7Ow9U8VtLwUn0aA")
        self._clip(monkeypatch, "shoes marker sign please give")

        res = find_source.find_source("B4uytxWGWEk")

        assert res["found"] is True
        assert res["match"]["video_id"] == "other_channel"
