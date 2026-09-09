"""Klip (Shorts/qisqa video) qaysi STREAMdan olinganini topish.

Muammo: YouTube'dagi fan kanallari uzun streamlardan qisqa klip qiladi va
manba havolasini ko'rsatmaydi. Bu modul klipning transkripti bilan
indekslangan streamlar transkriptini solishtirib, manba videoni va ANIQ
soniyani topadi.

Nega aniq ibora qidiruvi YETARLI EMAS: klip va streamning avtomatik
subtitri (ASR) bir xil audio uchun ham har xil chiqadi — montaj, ustiga
qo'yilgan musiqa, olomon shovqini so'zlarni o'zgartiradi. Shuning uchun:

  1. Klipdan MA'NOLI so'zlar to'plami ajratiladi (stop-so'zlar va
     "[Music]" kabi subtitr artefaktlarisiz).
  2. Har bir so'z uchun "qaysi videolarda uchraydi" so'raladi — kam videoda
     uchragan so'z XARAKTERLIROQ (BM25 IDF): "marker" kabi so'z "speed"dan
     ancha qimmatroq, hamma videoda uchraydigani esa ~0 ball beradi.
  3. Eng ko'p IDF ball (chastotaga qarab) to'plagan ``MAX_CANDIDATE_VIDEOS``
     ta video nomzod bo'ladi — bu ARZON, lekin TAXMINIY filtr.
  4. Har bir nomzod ichida sirg'aluvchi vaqt oynasi (default 60s) bo'ylab
     ball hisoblanadi — eng yuqori ballli oyna manba lahzasi.
  5. G'olibning balli qolgan nomzodlar medianasidan yetarlicha
     (MIN_MARGIN barobar) yuqori bo'lsagina natija qaytariladi.

Nega 3-qadam ba'zan YETARLI EMAS: bitta kanalning yuzlab soatlab davom
etgan streamlarida klipning UMUMIY so'zlari (masalan "speed", "back",
"flip") deyarli HAR bir streamda bir necha marta uchraydi — ya'ni 3-qadam
filtri ularning HAMMASINI bab-baravar eng yuqori ballga qo'yib, haqiqiy
manbani ``MAX_CANDIDATE_VIDEOS`` chegarasidan tashqarida tasodifan qoldirib
yuborishi mumkin (2026-09-04, IShowSpeed misolida: 1174 videodan 1061
tasi durrang bo'lib chiqqan). Bunday holatda 3-qadam filtri muvaffaqiyatsiz
bo'lganini aniqlab (natija topilmadi yoki margin/ball yetarli emas),
``_match_against_index`` HAMMA nomzodni (filtrsiz) batafsil tekshirishga
qaytadi — sekinroq (katta indeksda o'n(lab) soniya), lekin faqat shu qiyin
holatda ishga tushadi.

Nega 5-qadam kerak: indeksda manba stream BO'LMASA ham, algoritm baribir
"eng yaxshi" videoni topadi. Bunday holatda g'olib raqiblar guruhidan
deyarli ajralmaydi (margin ~1.2), haqiqiy moslikda esa keskin ajraladi
(margin 2.3+). Bu tekshiruvsiz javob har safar indeksdagi eng uzun
streamga "yopishib" qolardi.

Til masalasi: indeks qaysi tilda saqlangan bo'lsa (ingliz asl ASR yoki
o'zbek avtomatik tarjimasi), klip ham SHU tilda olinishi kerak — tarjima
ustidagi moslik ishonchsiz. Shuning uchun klip transkripti ``languages``
ro'yxatidagi har bir til uchun alohida olinadi va eng yaxshi ball bergani
tanlanadi (2026-09-03 holatiga ko'ra bazada eski o'zbekcha va yangi
inglizcha yozuvlar aralash bo'lishi mumkin — bu shuni ham qamrab oladi).

Asosiy kirish nuqtasi: ``find_source()``.
"""
from __future__ import annotations

import math
import re
import statistics
from collections import Counter

from . import fetch, store, text

DEFAULT_WINDOW_SECONDS = 60.0   # bitta taqqoslash oynasining uzunligi
DEFAULT_STEP_SECONDS = 15.0     # oyna qadami (oynalar ustma-ust tushadi)
MAX_CLIP_TERMS = 40             # klipdan olinadigan eng ko'p uchraydigan so'zlar soni
MAX_CANDIDATE_VIDEOS = 12       # oyna bo'yicha batafsil tekshiriladigan videolar soni
DEFAULT_CLIP_LANGUAGES = ["en", "uz"]

# Bitta so'zning takrorlanishidan olinadigan eng katta hissa. Cheklovsiz,
# klipda 8 marta takrorlangan bitta so'z butun ballni egallab olardi.
MAX_TERM_REPEAT = 3

# --- Qaror mezonlari (2026-09-03 da HAQIQIY ma'lumotda kalibrlangan) -------
# Eng muhim mezon — MARGIN: g'olib ballining qolgan nomzodlar MEDIANASIGA
# nisbati. O'lchov (IShowSpeed, 320 ta indekslangan video):
#     to'g'ri moslik (B4uytxWGWEk -> VoL8U_UF0do): 45.01 / 19.28 = 2.33
#     xato mosliklar (3 xil holat):               1.19 / 1.22 / 1.39
#
# Nega 2-o'rin emas, MEDIANA: 2-o'ringa nisbat indeks o'sishi bilan
# beqaror. Xuddi shu to'g'ri javobning 2-o'ringa nisbati 68 videolik
# indeksda 3.31 edi, 320 videolikda 2.02 ga tushdi — kattaroq bazada
# doim biror "birmuncha o'xshash" video topiladi va u 2-o'rinni egallaydi.
# Butun raqiblar guruhining medianasi esa barqaror qoladi, ustiga-ustak
# bitta haqiqiy dublikat (masalan "Day 18 of 35" turkumidagi qo'shni
# stream) natijani buzib yubormaydi.
#
# Xom ball bu ishni bajara olmaydi (xato javob 28.47, to'g'ri javob 23.20
# bo'lishi mumkin), "coverage" ham ajratmadi (0.279 vs 0.272).
MIN_SCORE = 1.0             # bundan past — umuman jiddiy ustma-tushlik yo'q
MIN_MARGIN = 1.7            # bundan past — "eng yaxshi axlat", moslik emas
MIN_CONFIDENT_SCORE = 12.0
MIN_CONFIDENT_MARGIN = 2.0
MIN_CONFIDENT_TERMS = 5     # bitta-ikkita nodir so'z tasodifan mos kelishi mumkin

# Sahna boshini aniqlashda eng yuqori ballli oynadan qancha orqaga
# qaraladi (klipdagi suhbat oynadan uzun bo'lishi mumkin).
SCENE_LOOKBACK_SECONDS = 120.0

_VIDEO_ID_RE = re.compile(r"[A-Za-z0-9_-]{11}")
_URL_ID_RE = re.compile(
    r"(?:youtu\.be/|/shorts/|/live/|/embed/|[?&]v=)([A-Za-z0-9_-]{11})"
)
# So'zlarga ajratish ``text.py``da — ``store`` teskari indeksni AYNAN
# shu qoida bilan quradi, ikkalasi ajralib qolmasligi kerak.
_terms = text.terms
STOPWORDS = text.STOPWORDS


def parse_video_id(ref: str) -> str:
    """Klip havolasidan (Shorts / youtu.be / watch?v= / xom ID) video ID.

    ``https://youtube.com/shorts/B4uytxWGWEk?si=...`` kabi shakllar ham
    qo'llab-quvvatlanadi."""
    ref = (ref or "").strip()
    if not ref:
        raise ValueError("Klip havolasi bo'sh")
    m = _URL_ID_RE.search(ref)
    if m:
        return m.group(1)
    if "/" not in ref and _VIDEO_ID_RE.fullmatch(ref):
        return ref
    raise ValueError(f"Video ID aniqlanmadi: {ref!r}")


def _resolve_channel_id(channel_ref: str | None) -> str | None:
    """Kanal havolasini indeksda saqlangan xom ``UC...`` ID'ga aylantiradi.

    Kerak, chunki UI'da kanal maydoni qidiruv bloki bilan UMUMIY va u yerga
    ``@handle`` yoki kanal URL'i kiritish tabiiy (qidiruv yo'li buni
    ``index_channel`` ichida o'zi hal qiladi). Indeks esa faqat ID bo'yicha
    filtrlanadi — aylantirmasak, filtr hech nimaga mos kelmay, natija
    aldamchi "manba topilmadi" bo'lib chiqardi.

    Xom ID berilganda tarmoqqa umuman chiqilmaydi (kvota sarflanmaydi)."""
    channel_ref = (channel_ref or "").strip()
    if not channel_ref:
        return None
    if fetch._CHANNEL_ID_RE.match(channel_ref):
        return channel_ref
    return fetch.resolve_channel(channel_ref)["channel_id"]


def _idf(total_videos: int, doc_frequency: int) -> float:
    """BM25 uslubidagi IDF — so'z qancha kam videoda uchrasa, shuncha qimmat.

    Avvalgi ``log(1 + N/(1+df))`` formulasi HECH QACHON nolga tushmasdi:
    hamma videoda uchraydigan so'z ham (masalan "hey", "music") ~0.7 ball
    berardi, o'nlab shunday so'z esa yig'ilib, hech qanday haqiqiy moslik
    bo'lmagan videoni g'olib qilardi. Bu formulada ``df -> N`` bo'lganda
    natija ~0 ga intiladi, ya'ni ommaviy so'zlar ballga umuman ta'sir
    qilmaydi."""
    return math.log(1 + (total_videos - doc_frequency + 0.5) / (doc_frequency + 0.5))


def _clip_terms(raw_segments: list[dict]) -> Counter:
    counts: Counter = Counter()
    for seg in raw_segments:
        counts.update(_terms(seg.get("text", "")))
    return counts


def _score_windows(
    segments: list[dict],
    clip_counts: Counter,
    idf: dict[str, float],
    window: float,
    step: float,
) -> tuple[float, float, list[str]]:
    """Bitta videoning segmentlari ustidan sirg'aluvchi oyna bo'ylab eng
    yaxshi ballni topadi. Qaytaradi: ``(ball, oyna boshlanish vaqti, umumiy so'zlar)``."""
    if not segments:
        return 0.0, 0.0, []

    # Faqat klipda bor va vazni musbat so'zlar qiziq — qolgani ballga
    # umuman ta'sir qilmaydi. Oldindan filtrlash oyna sanog'ini kichik
    # tutadi (uzun streamda segmentlarning aksariyati bo'sh bo'lib qoladi).
    relevant = {term for term in clip_counts if idf.get(term, 0.0) > 0}
    prepared = [
        (seg["start_time"], [w for w in _terms(seg["text"]) if w in relevant])
        for seg in segments
    ]
    end = prepared[-1][0]

    # Sirg'aluvchi oyna IKKI KO'RSATKICH bilan: segmentlar vaqt bo'yicha
    # tartiblangani uchun har bir oyna uchun butun ro'yxatni qayta ko'rib
    # chiqish shart emas — oynaga kirganlari qo'shiladi, chiqqanlari
    # ayriladi. Avvalgi to'liq qayta ko'rib chiqish 6 soatlik streamda
    # ~23 million iteratsiya berardi (bitta so'rov o'nlab soniya).
    windows: list[tuple[float, float, list[str]]] = []  # (boshlanish, ball, umumiy so'zlar)
    counts: Counter = Counter()
    lo = hi = 0
    start = prepared[0][0]
    while start <= end:
        stop = start + window
        while hi < len(prepared) and prepared[hi][0] < stop:
            counts.update(prepared[hi][1])
            hi += 1
        while lo < len(prepared) and prepared[lo][0] < start:
            for word in prepared[lo][1]:
                if counts[word] <= 1:
                    del counts[word]
                else:
                    counts[word] -= 1
            lo += 1

        score = 0.0
        shared = []
        for term, found in counts.items():
            score += idf[term] * min(clip_counts[term], found, MAX_TERM_REPEAT)
            shared.append(term)
        windows.append((start, score, shared))
        start += step

    best_i = max(range(len(windows)), key=lambda i: windows[i][1])
    best_start, best_score, best_shared = windows[best_i]
    if best_score <= 0:
        return 0.0, 0.0, []

    # Sahna BOSHINI topish. Eng yuqori ballli oynaning boshlanishi sahna
    # boshi EMAS: oyna sahna o'rtasiga tushishi mumkin (klipdagi suhbat
    # 60s oynadan uzun bo'lsa shunday bo'ladi) va havola sahna boshlangandan
    # keyin ochilib, foydalanuvchi boshini o'tkazib yuborardi.
    #
    # Shuning uchun oynadan biroz oldinroqdan boshlab, MOS KELGAN so'zlar
    # birinchi marta uchraydigan segment izlanadi — aynan shu joyda klipdagi
    # suhbat boshlanadi. Oyna ballini nisbat bo'yicha orqaga surishdan
    # aniqroq: ball butun oyna bo'yicha o'rtachalashadi, bu esa konkret
    # segmentni ko'rsatadi.
    #
    # Lekin FAQAT "birinchi uchragan joy"ga qarash yetarli emas: uzoq
    # (soatlab davom etuvchi) streamda ``SCENE_LOOKBACK_SECONDS`` (120s)
    # ichida klipning UMUMIY (kam xarakterli) so'zlaridan biri sahnaga
    # umuman aloqasi bo'lmagan holda tasodifan uchrab qolishi mumkin — va
    # o'sha yolg'iz uchrash havolani haqiqiy sahnadan ancha oldinga
    # "sirg'anib" yuboradi (2026-09-09, IShowSpeed "Ronaldo kit" klipida
    # kuzatilgan: haqiqiy sahna 3399.8s da boshlangan — "why this girl got
    # a messy shirt put on a Ronaldo kit" — lekin oynadan 118s oldinroqda,
    # 3280.6s atrofida, "take a picture" haqidagi BUTUNLAY boshqa suhbatda
    # "take" so'zi tasodifan uchrab, havola o'sha yerga ochilgan edi).
    #
    # Shuning uchun mos kelgan segmentlar orasidagi BO'SHLIQQA qaraymiz:
    # ular bir-biridan yarim oynadan (``window / 2``) uzoqroqda bo'lsa,
    # bu ikkita ALOHIDA voqea (avvalgisi tasodifiy, keyingisi haqiqiy
    # sahna) deb hisoblanadi va sanoq qaytadan boshlanadi — natijada eng
    # yuqori ballli oynaga ULANGAN (uzilishsiz) so'nggi to'plam boshlanishi
    # qaytariladi, undan OLDINGI izolyatsiyalangan tasodifiy uchrashuv emas.
    # Yagona (uzilishsiz) uchrashuvlar to'plamida esa xatti-harakat
    # o'zgarmaydi — birinchi uchragan joy baribir tanlanadi (pastdagi
    # testlarga qarang).
    shared_terms = set(best_shared)
    earliest = best_start - SCENE_LOOKBACK_SECONDS
    cluster_start = best_start
    prev_match: float | None = None
    for seg_start, words in prepared:
        if seg_start < earliest:
            continue
        if seg_start >= best_start + window:
            break
        if not shared_terms.intersection(words):
            continue
        if prev_match is None or seg_start - prev_match > window / 2:
            cluster_start = seg_start
        prev_match = seg_start
        if seg_start >= best_start:
            break
    return best_score, cluster_start, best_shared


def _best_match(
    video_terms: dict[str, Counter],
    clip_counts: Counter,
    idf: dict[str, float],
    window: float,
    step: float,
    limit: int | None,
) -> tuple[float, str, float, list[str], float] | None:
    """``video_terms``dagi nomzodlarni ballaydi va g'olibni qaytaradi:
    ``(ball, video_id, boshlanish, umumiy so'zlar, margin)``.

    ``limit`` berilsa, avval eng ko'p (chastotaga qarab) idf to'plagan
    ``limit`` ta nomzodgina batafsil (sirg'aluvchi oyna) tekshiriladi — bu
    tez, lekin taxminiy filtr. ``limit=None`` — HAMMA nomzod batafsil
    tekshiriladi (sekin, lekin filtr hech narsani noto'g'ri kesib
    tashlamaydi); qachon ishlatilishi haqida ``_match_against_index``ga
    qarang."""
    candidates = video_terms.items()
    if limit is not None:
        candidates = sorted(
            candidates,
            key=lambda item: sum(
                idf[t] * min(clip_counts[t], c, MAX_TERM_REPEAT) for t, c in item[1].items()
            ),
            reverse=True,
        )[:limit]

    scored = []
    for video_id, _ in candidates:
        segments = store.get_video_segments(video_id)
        score, start_time, shared = _score_windows(segments, clip_counts, idf, window, step)
        scored.append((score, video_id, start_time, sorted(set(shared))))
    if not scored:
        return None
    scored.sort(key=lambda row: row[0], reverse=True)

    score, video_id, start_time, shared = scored[0]
    if score <= 0:
        return None

    # Yagona nomzod bo'lsa taqqoslash uchun raqib yo'q — margin cheksiz.
    others = [row[0] for row in scored[1:]]
    baseline = statistics.median(others) if others else 0.0
    margin = score / baseline if baseline > 0 else float("inf")
    return score, video_id, start_time, shared, margin


def _match_against_index(
    clip_raw: list[dict],
    channel_id: str | None,
    window: float,
    step: float,
) -> dict | None:
    """Klip transkriptini indeksdagi videolar bilan solishtiradi.

    Qaytgan lug'atda ``score``dan tashqari ``margin`` ham bor — g'olibning
    balli qolgan nomzodlar medianasidan necha barobar yuqoriligi. Aynan
    shu qiymat "haqiqiy moslik"ni "eng yaxshi axlat"dan ajratadi (yuqoridagi
    mezonlar izohiga qarang)."""
    clip_counts = _clip_terms(clip_raw)
    if not clip_counts:
        return None

    terms = [term for term, _ in clip_counts.most_common(MAX_CLIP_TERMS)]
    total_videos = max(store.count_indexed_videos(channel_id), 1)

    # Har bir so'z uchun "qaysi videolarda NECHA MARTA bor" — bu ham
    # nomzodlarni beradi, ham IDF (hujjat chastotasi) ni. Chastota (shunchaki
    # "bor/yo'q" emas) foydali, lekin YAKKA O'ZI YETARLI EMAS: soatlab davom
    # etgan streamda deyarli HAR QANDAY so'z ``MAX_TERM_REPEAT`` (3) marta ham
    # osongina uchraydi, ya'ni chastota ham tezda TO'YINIB (barcha nomzodda
    # bir xil chegaraga yetib) qoladi — pastdagi ikki bosqichli tekshiruvga
    # qarang.
    video_terms: dict[str, Counter] = {}
    idf: dict[str, float] = {}
    for term in terms:
        counts_by_video = store.find_videos_with_term_counts(term, channel_id=channel_id)
        idf[term] = _idf(total_videos, len(counts_by_video))
        for video_id, count in counts_by_video.items():
            video_terms.setdefault(video_id, Counter())[term] = count

    if not video_terms:
        return None

    result = _best_match(video_terms, clip_counts, idf, window, step, MAX_CANDIDATE_VIDEOS)

    # IKKINCHI BOSQICH — TO'LIQ TEKSHIRUV: klipning so'zlari juda umumiy
    # bo'lsa (masalan "speed", "back", "flip" — IShowSpeed kabi bitta
    # kanalning YUZLAB soatlab davom etgan streamlarida barchasida uchraydi),
    # yuqoridagi tez (arzon) filtr HAQIQIY manbani ham "durrang"ning ichiga
    # qo'shib, MAX_CANDIDATE_VIDEOS chegarasidan tashqarida tasodifan qoldirib
    # yuborishi mumkin (2026-09-04, IShowSpeed klipida kuzatilgan: 1174
    # videodan 1061 tasi klipning BARCHA so'zlarini bir necha martadan o'z
    # ichiga olgan — chastota ham ularni ajrata olmagan).
    #
    # Bunday holatda YAGONA ishonchli yo'l — HAR BIR nomzodni batafsil
    # (sirg'aluvchi oyna bilan) tekshirish, chunki faqat shu bosqich so'zlar
    # bir joyga TO'PLANGANMI (haqiqiy sahna) yoki butun video bo'ylab
    # SOCHILGANMI (tasodifiy) ekanini bilib beradi. Buni FAQAT tez yo'l
    # muvaffaqiyatsiz bo'lganda (va haqiqatan ham kesish sodir bo'lganda)
    # ishlatamiz — katta indeksda bu bir necha o'n soniya olishi mumkin,
    # lekin faqat shu qiyin holatlarda, har bir so'rovda emas.
    was_truncated = len(video_terms) > MAX_CANDIDATE_VIDEOS
    if was_truncated and (result is None or result[0] < MIN_SCORE or result[4] < MIN_MARGIN):
        full_result = _best_match(video_terms, clip_counts, idf, window, step, limit=None)
        if full_result is not None and (result is None or full_result[0] > result[0]):
            result = full_result

    if result is None:
        return None
    score, video_id, start_time, shared, margin = result

    meta = store.get_video_meta(video_id) or {}
    return {
        "video_id": video_id,
        "video_title": meta.get("video_title", ""),
        "channel_name": meta.get("channel_name", ""),
        "published_at": meta.get("published_at"),
        "start_time": start_time,
        "score": score,
        "margin": margin,
        "matched_terms": shared,
        "url": f"https://youtube.com/watch?v={video_id}&t={int(start_time)}s",
    }


def find_source(
    clip_ref: str,
    channel_id: str | None = None,
    languages: list[str] | None = None,
    window: float = DEFAULT_WINDOW_SECONDS,
    step: float = DEFAULT_STEP_SECONDS,
) -> dict:
    """Klip qaysi indekslangan streamdan olinganini topadi.

    - ``clip_ref`` — Shorts/video havolasi yoki xom ID.
    - ``channel_id`` — berilsa faqat shu kanal videolari ichidan qidiradi
      (tezroq va aniqroq); berilmasa butun indeks bo'yicha. Xom ``UC...``
      ID, ``@handle`` yoki kanal URL'i bo'lishi mumkin.
    - ``languages`` — klip transkripti qaysi tillarda sinab ko'rilishi
      (indeks tili bilan mos kelishi kerak, yuqoridagi izohga qarang).

    Qaytaradi::

        {"found": bool, "confident": bool, "clip_id": str,
         "clip_language": str | None, "match": {...} | None}

    ``match`` ichida: ``video_id``, ``video_title``, ``channel_name``,
    ``published_at``, ``start_time`` (soniya), ``url`` (vaqt belgili),
    ``score``, ``margin``, ``matched_terms``.

    Ishonchli moslik bo'lmasa ``match`` ``None`` bo'ladi — eng yaxshi
    nomzod "shunchaki bo'lsin" deb qaytarilmaydi.

    ``fetch.TranscriptFetchBlocked`` ko'tarilishi mumkin — klipning o'z
    transkriptini olishda YouTube bloklasa (chaqiruvchi buni "topilmadi"dan
    farqlab ko'rsatishi kerak)."""
    clip_id = parse_video_id(clip_ref)
    channel_id = _resolve_channel_id(channel_id)
    languages = languages or DEFAULT_CLIP_LANGUAGES

    candidates: list[tuple[dict, str]] = []
    blocked_errors = 0

    for language in languages:
        try:
            clip_raw = fetch.fetch_transcript(clip_id, languages=[language])
        except fetch.TranscriptFetchBlocked:
            blocked_errors += 1
            continue
        if not clip_raw:
            continue
        match = _match_against_index(clip_raw, channel_id, window, step)
        if match:
            candidates.append((match, language))
            # Ishonchli javob topildi — qolgan tillarni so'rash shart emas
            # (har bir til uchun klip transkriptini olish ~10 soniya).
            # Faqat ISHONCHLI natijada to'xtaymiz: zaif moslikda boshqa
            # til to'g'riroq javob berishi mumkin, va aynan shunday holat
            # kuzatilgan ham (inglizcha yo'l xato, o'zbekchasi to'g'ri).
            if _is_confident(match):
                break

    if not candidates and blocked_errors == len(languages):
        raise fetch.TranscriptFetchBlocked(
            "Klip transkriptini olishda YouTube so'rovni bloklandi"
        )
    if not candidates:
        return _no_match(clip_id)

    # Tillar orasidan tanlashda ham MARGIN birinchi o'rinda: har xil tildagi
    # xom ballar bir-biri bilan taqqoslanmaydi (indeksda qaysi til ko'proq
    # bo'lsa, o'sha tilning balli tabiiy ravishda kattaroq chiqadi), margin
    # esa nisbiy kattalik — shuning uchun tillararo adolatli.
    candidates.sort(key=lambda item: (item[0]["margin"], item[0]["score"]), reverse=True)
    best, best_language = candidates[0]

    if best["score"] < MIN_SCORE or best["margin"] < MIN_MARGIN:
        return _no_match(clip_id)

    return {
        "found": True,
        "confident": _is_confident(best),
        "clip_id": clip_id,
        "clip_language": best_language,
        "match": best,
    }


def _is_confident(match: dict) -> bool:
    """Moslik "ishonchli" darajaga yetdimi — uchala mezon ham bajarilishi
    kerak (mezonlar izohi yuqorida)."""
    return (
        match["score"] >= MIN_CONFIDENT_SCORE
        and match["margin"] >= MIN_CONFIDENT_MARGIN
        and len(match["matched_terms"]) >= MIN_CONFIDENT_TERMS
    )


def _no_match(clip_id: str) -> dict:
    """Ishonchli moslik topilmadi. Eng yaxshi nomzod ATAYLAB qaytarilmaydi:
    manba stream indekslanmagan bo'lsa, "eng yaxshi axlat" har doim topiladi
    va uni ko'rsatish foydalanuvchini chalg'itadi (aynan shu sabab bir xil
    uzun stream har safar javob bo'lib chiqardi)."""
    return {
        "found": False,
        "confident": False,
        "clip_id": clip_id,
        "clip_language": None,
        "match": None,
    }
