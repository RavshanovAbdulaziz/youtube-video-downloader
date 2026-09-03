"""Qidiruv logikasi — kanal va global rejimlarni bir xil natija shakliga
(`{video_id, video_title, channel_name, text, start_time, url}`) birlashtiradi.

Asosiy kirish nuqtasi: `search()`. Ichki `_extract_matches()` — aniq
so'z/ibora (substring) moslikni topadigan yagona joy; kelajakda semantik
(embedding) qidiruv kerak bo'lsa, shu funksiyani bir xil signature
(`segments, query -> matches`) bilan almashtirish kifoya — `search()`ning
qolgan qismi (video ro'yxati olish, saqlash, natija formatlash) o'zgarmaydi.
"""
from __future__ import annotations

from . import cache, fetch, store

DEFAULT_CONTEXT_SIZE = 1  # moslikdan oldin/keyin nechta segment kontekstga qo'shiladi
MAX_MATCHES_PER_VIDEO = 5  # bitta videoda bir xil ibora ko'p marta uchrasa, natija sonini cheklaydi
DEFAULT_INDEX_MAX_VIDEOS = 25  # kanal birinchi marta indexlanganda tekshiriladigan video soni
DEFAULT_SEARCH_MAX_VIDEOS = 15  # global rejimda tekshiriladigan nomzod video soni


def search(
    query: str,
    channel_id: str | None = None,
    max_videos: int | None = None,
    context_size: int = DEFAULT_CONTEXT_SIZE,
) -> list[dict]:
    """So'z/ibora bo'yicha transkript qidiruvi — asosiy kirish nuqtasi.

    - ``channel_id`` berilsa (xom ``UC...`` ID, ``@handle`` yoki to'liq
      kanal URL'i ham bo'lishi mumkin) — faqat o'sha kanal videolari
      ichida qidiradi. Kanal birinchi chaqiruvda avtomatik indexlanadi
      (SQLite'ga saqlanadi), keyingi qidiruvlar shu saqlangan ma'lumot
      ustida ishlaydi — tezkor, YouTube API'ga qayta murojaat qilmaydi.
    - ``channel_id`` berilmasa — butun YouTube bo'yicha: ``search.list``
      orqali nomzod videolar topiladi, har birining transkripti real
      vaqtda tekshiriladi. Natija saqlanmaydi, faqat 24 soatlik xotira
      keshi ishlatiladi (``cache.py``).

    Qaytaradi: har bir moslik uchun quyidagi kalitlarga ega lug'atlar
    ro'yxati — ``video_id``, ``video_title``, ``channel_name``, ``text``
    (kontekst bilan), ``start_time`` (soniyalarda), ``url`` (vaqt
    belgili to'g'ridan-to'g'ri havola).
    """
    query = (query or "").strip()
    if not query:
        raise ValueError("Qidiruv so'zi bo'sh bo'lishi mumkin emas")

    if channel_id:
        return _search_channel(query, channel_id, max_videos or DEFAULT_INDEX_MAX_VIDEOS, context_size)
    return _search_global(query, max_videos or DEFAULT_SEARCH_MAX_VIDEOS, context_size)


def index_channel(channel_ref: str, max_videos: int = DEFAULT_INDEX_MAX_VIDEOS, force: bool = False) -> dict:
    """Kanalni qidiruv uchun tayyorlaydi: video ro'yxatini oladi, hali
    indexlanmagan har bir video uchun transkriptni olib SQLite'ga saqlaydi
    (topilmasa ham "tekshirilgan" deb belgilanadi — keyingi safar qayta
    urinilmaydi, ``fetch.fetch_transcript``ga qarang).

    Kanal allaqachon indexlangan bo'lsa (``force=False``, standart) hech
    narsa qilmay ``{channel_id, title, uploads_playlist_id}``ni qaytaradi
    — shu orqali ``search()`` har chaqirilganda butun kanalni qayta-qayta
    aylanib chiqmaydi, faqat BIRINCHI qidiruvda (yoki ``force=True`` bilan
    qo'lda) ishlaydi.
    """
    info = fetch.resolve_channel(channel_ref)
    channel_id = info["channel_id"]

    if not force and store.is_channel_indexed(channel_id):
        return info

    videos = fetch.list_channel_videos(info["uploads_playlist_id"], max_results=max_videos)
    any_blocked = False
    for video in videos:
        video_id = video["video_id"]
        if not force and store.is_video_indexed(video_id):
            continue
        try:
            raw = fetch.fetch_transcript(video_id)
        except fetch.TranscriptFetchBlocked:
            # Bu VIDEO haqida emas — YouTube shu daqiqada umuman javob
            # bermayapti (masalan IP bloklangan). "Tekshirilgan" deb
            # belgilamaymiz, aks holda blok tugagandan keyin ham bu video
            # abadiy "subtitri yo'q" bo'lib qolardi.
            any_blocked = True
            continue
        segments = _normalize_segments(raw) if raw else []
        store.save_video_segments(video_id, channel_id, info["title"], video["title"], segments)

    # Bloklangan holatda kanalni ham "to'liq indexlangan" deb belgilamaymiz
    # — aks holda keyingi qidiruv `is_channel_indexed`ga tayanib butunlay
    # qayta urinishni o'tkazib yuborardi, garchi hech narsa saqlanmagan bo'lsa ham.
    if not any_blocked:
        store.mark_channel_indexed(channel_id, len(videos))
    return info


def _search_channel(query: str, channel_ref: str, max_videos: int, context_size: int) -> list[dict]:
    info = index_channel(channel_ref, max_videos=max_videos)
    real_channel_id = info["channel_id"]

    results = []
    for video_id in store.find_matching_video_ids(real_channel_id, query):
        meta = store.get_video_meta(video_id)
        if meta is None:
            continue
        segments = store.get_video_segments(video_id)
        for match in _extract_matches(segments, query, context_size):
            results.append(_build_result(video_id, meta["video_title"], meta["channel_name"], match))
    return results


def _search_global(query: str, max_videos: int, context_size: int) -> list[dict]:
    results = []
    for candidate in fetch.search_videos(query, max_results=max_videos):
        video_id = candidate["video_id"]
        segments = cache.transcript_cache.get(video_id)
        if segments is None:
            try:
                raw = fetch.fetch_transcript(video_id)
            except fetch.TranscriptFetchBlocked:
                # Keshga yozmaymiz — vaqtinchalik bloklanish "bu videoda
                # subtitr yo'q" deb 24 soatga muhrlanib qolmasligi kerak.
                continue
            segments = _normalize_segments(raw) if raw else []
            cache.transcript_cache.set(video_id, segments)
        if not segments:
            continue
        for match in _extract_matches(segments, query, context_size):
            results.append(_build_result(video_id, candidate["title"], candidate["channel_name"], match))
    return results


def _normalize_segments(raw_segments: list[dict]) -> list[dict]:
    """``fetch.fetch_transcript``ning xom natijasini (``{text, start,
    duration}``) ichki qatorlar/ortiqcha bo'shliqlarsiz, ``{text,
    start_time, end_time}`` shakliga keltiradi."""
    normalized = []
    for seg in raw_segments:
        text = " ".join(seg["text"].split())
        if not text:
            continue
        start = seg["start"]
        normalized.append({"text": text, "start_time": start, "end_time": start + seg.get("duration", 0.0)})
    return normalized


def _extract_matches(segments: list[dict], query: str, context_size: int = DEFAULT_CONTEXT_SIZE) -> list[dict]:
    """``segments`` (video ichidagi tartibda, ``{text, start_time, ...}``)
    orasidan ``query``ni katta-kichik harflarga qaramay substring sifatida
    qidiradi; har bir moslikka oldin/keyingi ``context_size`` ta segmentni
    qo'shib kontekst matni quradi. Bitta videoda ``MAX_MATCHES_PER_VIDEO``dan
    ortiq moslik qaytarilmaydi."""
    if not query.strip():
        return []
    needle = query.lower()
    matches = []
    for i, seg in enumerate(segments):
        if needle not in seg["text"].lower():
            continue
        start = max(0, i - context_size)
        end = min(len(segments), i + context_size + 1)
        context_text = " ".join(s["text"] for s in segments[start:end])
        matches.append({"text": context_text, "start_time": seg["start_time"]})
        if len(matches) >= MAX_MATCHES_PER_VIDEO:
            break
    return matches


def _youtube_link(video_id: str, start_time: float) -> str:
    return f"https://youtube.com/watch?v={video_id}&t={int(start_time)}s"


def _build_result(video_id: str, video_title: str, channel_name: str, match: dict) -> dict:
    return {
        "video_id": video_id,
        "video_title": video_title,
        "channel_name": channel_name,
        "text": match["text"],
        "start_time": match["start_time"],
        "url": _youtube_link(video_id, match["start_time"]),
    }
