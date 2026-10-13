"""Kanal rejimi uchun yengil SQLite saqlash va substring qidiruv.

Katta tashqi search-engine (Elasticsearch) o'rniga: transkript segmentlari
oddiy jadvalga yoziladi, qidiruv esa SQL ``LIKE`` bilan amalga oshiriladi.
Hajm katta bo'lib qolsa, keyinchalik ``pg_trgm``li Postgres'ga o'tkazish
mumkin — bu fayldagi funksiyalarning imzosi shunga moslashishi uchun
qulay (chaqiruvchi ``search.py`` faqat oddiy python tuzilmalar bilan ishlaydi).

Global (kanalsiz) qidiruv bu modulni umuman ishlatmaydi — natijalar
saqlanmaydi, faqat ``cache.py``dagi vaqtinchalik TTL kesh ishlatiladi.
"""
from __future__ import annotations

import sqlite3
import time
from collections import Counter
from contextlib import contextmanager

import paths

from . import text

_SCHEMA = """
CREATE TABLE IF NOT EXISTS transcript_segments (
    video_id      TEXT NOT NULL,
    channel_id    TEXT NOT NULL,
    channel_name  TEXT,
    video_title   TEXT,
    published_at  TEXT,
    seg_index     INTEGER NOT NULL,
    text          TEXT NOT NULL,
    start_time    REAL NOT NULL,
    end_time      REAL NOT NULL,
    PRIMARY KEY (video_id, seg_index)
);
CREATE INDEX IF NOT EXISTS idx_segments_channel ON transcript_segments(channel_id);

-- Teskari indeks: "shu so'z qaysi videolarda uchraydi". ``find_source``
-- klipning har bir so'zi uchun shu savolni beradi va javob ikki ish
-- qiladi — nomzod videolarni tanlaydi va IDF (hujjat chastotasi) beradi.
--
-- Nega alohida jadval: avval bu ``transcript_segments`` ustidan
-- ``LIKE '%so'z%'`` bilan qilinardi, ya'ni HAR BIR so'z uchun butun
-- jadvalni to'liq skanerlash. 3.9 million qatorda bitta so'rov ~1 soniya,
-- klipda ~40 ta so'z, ikki til — bitta so'rov 75 soniyaga cho'zilardi va
-- indeks o'sgani sari yomonlashardi. Bu yerda esa PRIMARY KEY indeksidan
-- foydalaniladi.
CREATE TABLE IF NOT EXISTS video_terms (
    term       TEXT NOT NULL,
    video_id   TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    count      INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (term, video_id)
);
CREATE INDEX IF NOT EXISTS idx_video_terms_video ON video_terms(video_id);

CREATE TABLE IF NOT EXISTS indexed_videos (
    video_id       TEXT PRIMARY KEY,
    channel_id     TEXT NOT NULL,
    has_transcript INTEGER NOT NULL,
    indexed_at     REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS indexed_channels (
    channel_id   TEXT PRIMARY KEY,
    video_count  INTEGER NOT NULL,
    indexed_at   REAL NOT NULL
);
"""


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    # ``published_at`` sana oralig'i bo'yicha qidiruv qo'shilganda kiritildi
    # (2026-09-03) — ``CREATE TABLE IF NOT EXISTS`` eski (allaqachon mavjud)
    # bazalarga ustun qo'shmaydi, shuning uchun bu yerda qo'lda tekshirib
    # ``ALTER TABLE`` qilinadi. Eski qatorlarda bu ustun ``NULL`` bo'lib
    # qoladi — sana filtri berilmagan qidiruvlarga ta'sir qilmaydi, sana
    # filtri berilganda esa o'sha videolar force reindex qilinmaguncha
    # natijaga chiqmaydi (xavfsiz, aralashib ketmaydi).
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(transcript_segments)")}
    if "published_at" not in columns:
        conn.execute("ALTER TABLE transcript_segments ADD COLUMN published_at TEXT")

    # ``count`` (2026-09-04) — nomzod tanlashda so'zning shunchaki "bor/yo'q"
    # ligi o'rniga necha marta uchraganini ishlatish uchun (pastdagi
    # find_videos_with_term_counts'ga qarang). Eski qatorlarda DEFAULT 1
    # bilan to'ldiriladi — bu haqiqiy chastota emas, "--rebuild-term-index"
    # bajarilgunicha eski (bor/yo'q) xatti-harakatga teng bo'lib qoladi.
    term_columns = {row["name"] for row in conn.execute("PRAGMA table_info(video_terms)")}
    if "count" not in term_columns:
        conn.execute("ALTER TABLE video_terms ADD COLUMN count INTEGER NOT NULL DEFAULT 1")


@contextmanager
def _connect():
    """Har chaqiruvda yangi (qisqa umrli) ulanish — bir nechta thread
    (FastAPI so'rovlari) xavfsiz parallel ishlatishi uchun, ulanishni
    module darajasida umumiy holda saqlash o'rniga."""
    conn = sqlite3.connect(paths.TRANSCRIPT_DB_FILE)
    conn.row_factory = sqlite3.Row
    try:
        _ensure_schema(conn)
        yield conn
        conn.commit()
    finally:
        conn.close()


def is_channel_indexed(channel_id: str) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM indexed_channels WHERE channel_id = ?", (channel_id,)
        ).fetchone()
        return row is not None


def mark_channel_indexed(channel_id: str, video_count: int) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO indexed_channels (channel_id, video_count, indexed_at) "
            "VALUES (?, ?, ?)",
            (channel_id, video_count, time.time()),
        )


def is_video_indexed(video_id: str) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM indexed_videos WHERE video_id = ?", (video_id,)
        ).fetchone()
        return row is not None


def save_video_segments(
    video_id: str,
    channel_id: str,
    channel_name: str,
    video_title: str,
    segments: list[dict],
    published_at: str | None = None,
) -> None:
    """``segments``dagi har bir yozuv ``{text, start_time, end_time}``
    shaklida bo'lishi kutiladi. ``segments`` bo'sh bo'lsa ham (subtitr
    topilmagan video) chaqiriladi — video "tekshirilgan" deb belgilanadi,
    shunda keyingi qidiruvlarda uni qayta-qayta tekshirib o'tirmaymiz
    (bunda ``published_at`` hech qayerga yozilmaydi — segmentsiz videoning
    sanasi kerak emas, u qidiruv natijasida hech qachon chiqmaydi).

    ``published_at`` — video e'lon qilingan sana (``"YYYY-MM-DD"``),
    ``find_matching_video_ids``dagi sana oralig'i filtri uchun."""
    with _connect() as conn:
        conn.execute("DELETE FROM transcript_segments WHERE video_id = ?", (video_id,))
        conn.execute("DELETE FROM video_terms WHERE video_id = ?", (video_id,))
        _save_terms(conn, video_id, channel_id, segments)
        conn.executemany(
            "INSERT INTO transcript_segments "
            "(video_id, channel_id, channel_name, video_title, published_at, seg_index, text, start_time, end_time) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (video_id, channel_id, channel_name, video_title, published_at,
                 i, seg["text"], seg["start_time"], seg["end_time"])
                for i, seg in enumerate(segments)
            ],
        )
        conn.execute(
            "INSERT OR REPLACE INTO indexed_videos (video_id, channel_id, has_transcript, indexed_at) "
            "VALUES (?, ?, ?, ?)",
            (video_id, channel_id, 1 if segments else 0, time.time()),
        )


def _save_terms(conn, video_id: str, channel_id: str, segments: list[dict]) -> None:
    """Videodagi so'zlarning takrorlanish sonini teskari indeksga yozadi.

    Shunchaki "bor/yo'q" emas, aynan SON kerak: ``find_source``dagi nomzod
    tanlash shu songa qarab ballaydi (bir marta o'tgan so'z bilan o'nlab
    marta takrorlangan so'zni farqlash uchun — soatlab davom etgan uzun
    streamda deyarli har qanday so'z KAMIDA bir marta uchraydi, shuning
    uchun oddiy "bor/yo'q" nomzodlarni bir-biridan ajrata olmay qoladi)."""
    counts: Counter = Counter()
    for seg in segments:
        counts.update(text.terms(seg["text"]))
    conn.executemany(
        "INSERT OR REPLACE INTO video_terms (term, video_id, channel_id, count) VALUES (?, ?, ?, ?)",
        [(term, video_id, channel_id, count) for term, count in counts.items()],
    )


def rebuild_term_index() -> int:
    """Teskari indeksni mavjud segmentlardan qayta quradi.

    Faqat MIGRATSIYA uchun: ``video_terms`` jadvali ``save_video_segments``
    tomonidan o'z-o'zidan yangilanadi, lekin u qo'shilishidan OLDIN
    indekslangan videolarda bo'sh qoladi. Videolar bo'yicha bo'lib
    bajariladi — butun jadvalni xotiraga olmaydi.

    Qaytaradi: qayta qurilgan videolar soni."""
    with _connect() as conn:
        video_ids = [
            row["video_id"]
            for row in conn.execute("SELECT DISTINCT video_id FROM transcript_segments")
        ]
        for video_id in video_ids:
            rows = conn.execute(
                "SELECT channel_id, text FROM transcript_segments WHERE video_id = ?",
                (video_id,),
            ).fetchall()
            if not rows:
                continue
            conn.execute("DELETE FROM video_terms WHERE video_id = ?", (video_id,))
            _save_terms(
                conn, video_id, rows[0]["channel_id"],
                [{"text": row["text"]} for row in rows],
            )
            conn.commit()
        return len(video_ids)


def _escape_like(query: str) -> str:
    """``%``/``_`` LIKE maxsus belgilarini o'zboshimchalik bilan naqsh
    sifatida talqin qilinishining oldini oladi — foydalanuvchi qidirayotgan
    matn harfma-harf (literal substring) sifatida izlanadi."""
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def find_matching_video_ids(
    channel_id: str,
    query: str,
    published_after: str | None = None,
    published_before: str | None = None,
    limit: int = 50,
) -> list[str]:
    """``query`` kamida bitta segmentida uchraydigan videolar (SQL ``LIKE``
    orqali arzon oldindan filtr) — aniq moslik/kontekst keyin
    ``search.py``da ``get_video_segments`` natijasi ustida quriladi.

    ``published_after``/``published_before`` (``"YYYY-MM-DD"``) berilsa,
    faqat o'sha oraliqda e'lon qilingan videolar qaytadi — bu shart
    (``index_channel``dagi sana oralig'i bilan bir xil) qidiruv natijasi
    faqat SO'RALGAN oraliqni qamrab olishini kafolatlaydi, hatto kanal
    boshqa (masalan "eng so'nggi N video") chaqiruvda ham indexlangan bo'lsa.
    Sana yozilmagan (eski, ``published_at IS NULL``) qatorlar sana filtri
    berilganda avtomatik chiqarib tashlanadi — ular force reindex
    qilinmaguncha sana bo'yicha filtrlangan natijada ko'rinmaydi.

    To'rtta kombinatsiya (hech biri/faqat ``after``/faqat ``before``/
    ikkalasi) uchun ATAYLAB alohida, TO'LIQ statik SQL satrlari yozilgan
    (dinamik ``WHERE`` qurish o'rniga) — barcha qiymatlar ``?``
    parametrlari orqali uzatiladi, satr birlashtirish orqali emas."""
    base = "SELECT DISTINCT video_id FROM transcript_segments WHERE channel_id = ? AND text LIKE ? ESCAPE '\\'"
    needle = _escape_like(query)

    with _connect() as conn:
        if published_after and published_before:
            rows = conn.execute(
                base + " AND published_at >= ? AND published_at <= ? LIMIT ?",
                (channel_id, needle, published_after, published_before, limit),
            ).fetchall()
        elif published_after:
            rows = conn.execute(
                base + " AND published_at >= ? LIMIT ?",
                (channel_id, needle, published_after, limit),
            ).fetchall()
        elif published_before:
            rows = conn.execute(
                base + " AND published_at <= ? LIMIT ?",
                (channel_id, needle, published_before, limit),
            ).fetchall()
        else:
            rows = conn.execute(base + " LIMIT ?", (channel_id, needle, limit)).fetchall()
        return [row["video_id"] for row in rows]


def find_videos_with_term(
    term: str, channel_id: str | None = None, limit: int | None = None,
) -> list[str]:
    """``term`` uchraydigan videolarning ID'lari — ``find_source.py``dagi
    nomzod tanlash uchun.

    ``find_matching_video_ids``dan farqi: ``channel_id`` IXTIYORIY (berilmasa
    butun baza bo'yicha qidiriladi) va sana filtri yo'q — bu yerda maqsad
    "shu so'z qaysi videolarda bor" degan arzon oldindan filtr, aniq moslik
    keyin ``find_source``da segment darajasida hisoblanadi.

    Qaytgan ro'yxat uzunligi shu so'zning kanal bo'yicha "hujjat chastotasi"
    sifatida ham ishlatiladi (kam videoda uchragan so'z = xarakterliroq).

    ``video_terms`` teskari indeksidan o'qiydi — ya'ni moslik BUTUN SO'Z
    bo'yicha, avvalgi ``LIKE '%so'z%'`` kabi so'z ichidagi tasodifiy
    ustma-tushlik bo'yicha emas (bu chastotani ham aniqroq qiladi).
    Teskari indeks hali qurilmagan eski bazalarda avtomatik ravishda eski
    usulga qaytiladi (``rebuild_term_index``ga qarang).

    ``limit`` STANDART HOLATDA YO'Q (SQLite'da manfiy ``LIMIT`` = cheksiz):
    ro'yxat uzunligi hujjat chastotasi sifatida ishlatilgani uchun uni
    kesish IDF'ni buzadi — masalan 1000 videoda uchraydigan ommaviy so'z
    200da kesilsa, u "nodir" bo'lib ko'rinib, ballni noto'g'ri shishirardi."""
    limit = -1 if limit is None else limit
    with _connect() as conn:
        if not conn.execute("SELECT 1 FROM video_terms LIMIT 1").fetchone():
            return _find_videos_with_term_scan(conn, term, channel_id, limit)
        if channel_id:
            rows = conn.execute(
                "SELECT video_id FROM video_terms WHERE term = ? AND channel_id = ? LIMIT ?",
                (term, channel_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT video_id FROM video_terms WHERE term = ? LIMIT ?",
                (term, limit),
            ).fetchall()
        return [row["video_id"] for row in rows]


def _find_videos_with_term_scan(conn, term: str, channel_id: str | None, limit: int) -> list[str]:
    """Teskari indekssiz eski yo'l — butun jadvalni skanerlaydi (sekin)."""
    needle = _escape_like(term)
    if channel_id:
        rows = conn.execute(
            "SELECT DISTINCT video_id FROM transcript_segments "
            "WHERE channel_id = ? AND text LIKE ? ESCAPE '\\' LIMIT ?",
            (channel_id, needle, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT DISTINCT video_id FROM transcript_segments "
            "WHERE text LIKE ? ESCAPE '\\' LIMIT ?",
            (needle, limit),
        ).fetchall()
    return [row["video_id"] for row in rows]


def find_videos_with_term_counts(
    term: str, channel_id: str | None = None,
) -> dict[str, int]:
    """``find_videos_with_term`` bilan bir xil, lekin har bir video uchun
    so'z NECHA MARTA uchraganini ham qaytaradi (``{video_id: count}``).

    ``find_source.py``dagi nomzod tanlash uchun: so'zning shunchaki
    "bor/yo'q"ligi soatlab davom etgan streamda deyarli hech narsani
    ajratmaydi (deyarli har qanday so'z KAMIDA bir marta albatta uchraydi)
    — chastota esa haqiqiy moslikni tasodifiy ustma-tushlikdan ajratadi.

    Teskari indeks qurilmagan eski bazada ``_find_videos_with_term_scan``ga
    qaytadi va o'sha video ichida so'z UCHRAGAN SEGMENTLAR sonini chastota
    o'rnida ishlatadi (aniq so'z chastotasi emas, lekin oqilona taxmin —
    bu yo'l ``--rebuild-term-index`` bajarilgunicha vaqtinchalik)."""
    with _connect() as conn:
        if not conn.execute("SELECT 1 FROM video_terms LIMIT 1").fetchone():
            needle = _escape_like(term)
            if channel_id:
                rows = conn.execute(
                    "SELECT video_id, COUNT(*) c FROM transcript_segments "
                    "WHERE channel_id = ? AND text LIKE ? ESCAPE '\\' GROUP BY video_id",
                    (channel_id, needle),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT video_id, COUNT(*) c FROM transcript_segments "
                    "WHERE text LIKE ? ESCAPE '\\' GROUP BY video_id",
                    (needle,),
                ).fetchall()
            return {row["video_id"]: row["c"] for row in rows}
        if channel_id:
            rows = conn.execute(
                "SELECT video_id, count FROM video_terms WHERE term = ? AND channel_id = ?",
                (term, channel_id),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT video_id, count FROM video_terms WHERE term = ?",
                (term,),
            ).fetchall()
        return {row["video_id"]: row["count"] for row in rows}


def count_indexed_videos(channel_id: str | None = None) -> int:
    """Bazada segmentlari bor videolar soni (IDF hisobi uchun maxraj)."""
    with _connect() as conn:
        if channel_id:
            row = conn.execute(
                "SELECT COUNT(DISTINCT video_id) c FROM transcript_segments WHERE channel_id = ?",
                (channel_id,),
            ).fetchone()
        else:
            row = conn.execute("SELECT COUNT(DISTINCT video_id) c FROM transcript_segments").fetchone()
        return int(row["c"]) if row else 0


def list_indexed_channel_ids() -> list[str]:
    """Segmentlari bor kanallarning ID'lari — kanal ko'rsatilmaganda ham
    indeksni yangilab turish uchun (``search.catch_up``ga qarang)."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT channel_id FROM transcript_segments"
        ).fetchall()
        return [row["channel_id"] for row in rows]


def get_latest_indexed_date(channel_id: str) -> str | None:
    """Kanalda indekslangan ENG YANGI videoning sanasi (``"YYYY-MM-DD"``).

    Indeksni "shu sanadan keyingi videolar"ni olib yangilash uchun ishlatiladi.
    ``published_at`` yozilmagan eski qatorlar hisobga olinmaydi (``MAX``
    ``NULL``larni o'tkazib yuboradi) — bu xavfsiz tomonga xato: eng yomoni
    biroz ko'proq video qayta ko'rib chiqiladi, lekin ular ``is_video_indexed``
    tekshiruvida o'tkazib yuboriladi."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT MAX(published_at) AS latest FROM transcript_segments WHERE channel_id = ?",
            (channel_id,),
        ).fetchone()
        return row["latest"] if row and row["latest"] else None


def get_video_segments(video_id: str) -> list[dict]:
    """Videoning barcha segmentlari, ``seg_index`` tartibida —
    ``[{text, start_time, end_time}, ...]``."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT text, start_time, end_time FROM transcript_segments "
            "WHERE video_id = ? ORDER BY seg_index",
            (video_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def get_video_meta(video_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT video_id, channel_id, channel_name, video_title, published_at "
            "FROM transcript_segments WHERE video_id = ? LIMIT 1",
            (video_id,),
        ).fetchone()
        return dict(row) if row else None
