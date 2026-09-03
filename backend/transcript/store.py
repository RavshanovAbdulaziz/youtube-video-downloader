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
from contextlib import contextmanager

import paths

_SCHEMA = """
CREATE TABLE IF NOT EXISTS transcript_segments (
    video_id      TEXT NOT NULL,
    channel_id    TEXT NOT NULL,
    channel_name  TEXT,
    video_title   TEXT,
    seg_index     INTEGER NOT NULL,
    text          TEXT NOT NULL,
    start_time    REAL NOT NULL,
    end_time      REAL NOT NULL,
    PRIMARY KEY (video_id, seg_index)
);
CREATE INDEX IF NOT EXISTS idx_segments_channel ON transcript_segments(channel_id);

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


@contextmanager
def _connect():
    """Har chaqiruvda yangi (qisqa umrli) ulanish — bir nechta thread
    (FastAPI so'rovlari) xavfsiz parallel ishlatishi uchun, ulanishni
    module darajasida umumiy holda saqlash o'rniga."""
    conn = sqlite3.connect(paths.TRANSCRIPT_DB_FILE)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(_SCHEMA)
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
) -> None:
    """``segments``dagi har bir yozuv ``{text, start_time, end_time}``
    shaklida bo'lishi kutiladi. ``segments`` bo'sh bo'lsa ham (subtitr
    topilmagan video) chaqiriladi — video "tekshirilgan" deb belgilanadi,
    shunda keyingi qidiruvlarda uni qayta-qayta tekshirib o'tirmaymiz."""
    with _connect() as conn:
        conn.execute("DELETE FROM transcript_segments WHERE video_id = ?", (video_id,))
        conn.executemany(
            "INSERT INTO transcript_segments "
            "(video_id, channel_id, channel_name, video_title, seg_index, text, start_time, end_time) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (video_id, channel_id, channel_name, video_title, i, seg["text"], seg["start_time"], seg["end_time"])
                for i, seg in enumerate(segments)
            ],
        )
        conn.execute(
            "INSERT OR REPLACE INTO indexed_videos (video_id, channel_id, has_transcript, indexed_at) "
            "VALUES (?, ?, ?, ?)",
            (video_id, channel_id, 1 if segments else 0, time.time()),
        )


def _escape_like(query: str) -> str:
    """``%``/``_`` LIKE maxsus belgilarini o'zboshimchalik bilan naqsh
    sifatida talqin qilinishining oldini oladi — foydalanuvchi qidirayotgan
    matn harfma-harf (literal substring) sifatida izlanadi."""
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def find_matching_video_ids(channel_id: str, query: str, limit: int = 50) -> list[str]:
    """``query`` kamida bitta segmentida uchraydigan videolar (SQL ``LIKE``
    orqali arzon oldindan filtr) — aniq moslik/kontekst keyin
    ``search.py``da ``get_video_segments`` natijasi ustida quriladi."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT video_id FROM transcript_segments "
            "WHERE channel_id = ? AND text LIKE ? ESCAPE '\\' LIMIT ?",
            (channel_id, _escape_like(query), limit),
        ).fetchall()
        return [row["video_id"] for row in rows]


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
            "SELECT video_id, channel_id, channel_name, video_title FROM transcript_segments "
            "WHERE video_id = ? LIMIT 1",
            (video_id,),
        ).fetchone()
        return dict(row) if row else None
