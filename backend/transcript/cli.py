"""Standalone CLI kirish nuqtasi.

Ishlatish (``backend/`` papkasidan)::

    py -3.14 -m transcript.cli "qidiriladigan ibora" --channel UC... --json
    py -3.14 -m transcript.cli --find-source "https://youtube.com/shorts/..." --json

``--find-source`` — API endpointi (``api.py``dagi ``/find-source``) mavjud
bo'lsa-da, terminaldan tezkor tekshirish uchun ``fetch`` serverini ishga
tushirmasdan ham xuddi shu funksiyaga (``find_source.find_source``)
to'g'ridan-to'g'ri kirish kerak bo'lib qoldi (avval buni har safar bir
martalik ``python -c`` skripti bilan qilardik).

Paket konteksti majburiy emas — faylni to'g'ridan-to'g'ri ham chaqirsa
bo'ladi (``py -3.14 backend/transcript/cli.py ...``); buni pastdagi
``_bootstrap_package`` hal qiladi."""
from __future__ import annotations

import argparse
import json
import os
import sys


def _bootstrap_package() -> None:
    """``py cli.py`` deb chaqirilganda nisbiy importlarni tiklaydi.

    Bunday chaqiruvda modul ``__main__`` bo'ladi va hech qaysi paketga
    tegishli bo'lmaydi, ya'ni quyidagi ``from . import fetch``
    ``ImportError: attempted relative import with no known parent package``
    beradi. ``backend/`` ni ``sys.path``ga qo'yib, modulni ``transcript``
    paketining a'zosi deb belgilaymiz — shundan keyin ``.`` yechiladi va
    CLI qaysi papkadan turib chaqirilishidan qat'i nazar ishlaydi."""
    if __package__:
        return  # `-m transcript.cli` — kontekst allaqachon joyida.
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)
    globals()["__package__"] = "transcript"


_bootstrap_package()

# Importlar `_bootstrap_package()`dan KEYIN turishi shart — yuqoridagi
# chaqiruv aynan shu qatorlar uchun paket kontekstini tayyorlaydi.
from . import fetch  # noqa: E402
from . import find_source as find_source_module  # noqa: E402
from . import search as search_module  # noqa: E402
from . import store  # noqa: E402


def _use_utf8_output() -> None:
    """`print` chiqishini har qanday konsol/quvurda UTF-8'ga o'tkazadi.

    Standart holatda Python stdout uchun lokal kodlashni tanlaydi —
    Windows'da bu cp1252, ayniqsa chiqish faylga yoki quvurga
    yo'naltirilganda. Video sarlavhalarida emoji va lotin bo'lmagan
    harflar odatiy hol, shuning uchun natija topilgan bo'lsa ham
    buyruq oxirgi qadamda `UnicodeEncodeError` bilan yiqilardi.

    ``errors="replace"`` — UTF-8 o'rnatib bo'lmaydigan kamdan-kam holat
    uchun zaxira: belgi o'rniga ``?`` chiqadi, lekin buyruq yiqilmaydi."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue  # Almashtirilgan oqimlar (test'lardagi StringIO kabi).
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass  # Kodlashni o'zgartirib bo'lmadi — bor holicha davom etamiz.


def main(argv: list[str] | None = None) -> int:
    _use_utf8_output()
    parser = argparse.ArgumentParser(description="YouTube transkript qidiruv (CLI)")
    parser.add_argument("query", nargs="?", help="Qidiriladigan so'z yoki ibora")
    parser.add_argument(
        "--rebuild-term-index", dest="rebuild_term_index", action="store_true",
        help="Teskari so'z indeksini mavjud transkriptlardan qayta qurish "
             "(migratsiya — indeks qo'shilishidan oldin indexlangan bazalar uchun)",
    )
    parser.add_argument(
        "--find-source", dest="find_source_clip", default=None, metavar="CLIP_URL",
        help="Klip (Shorts/video) havolasi — qaysi indekslangan streamdan "
             "olinganini topadi (``query`` o'rniga ishlatiladi)",
    )
    parser.add_argument(
        "--channel", dest="channel_id", default=None,
        help="Kanal ID / @handle / URL (berilmasa — butun YouTube bo'yicha qidiradi)",
    )
    parser.add_argument("--max-videos", dest="max_videos", type=int, default=None)
    parser.add_argument(
        "--after", dest="published_after", default=None, metavar="YYYY-MM-DD",
        help="Faqat shu sanadan keyin (qamrab) e'lon qilingan videolar",
    )
    parser.add_argument(
        "--before", dest="published_before", default=None, metavar="YYYY-MM-DD",
        help="Faqat shu sanagacha (qamrab) e'lon qilingan videolar",
    )
    parser.add_argument("--json", action="store_true", help="Natijani JSON sifatida chiqarish")
    args = parser.parse_args(argv)

    if args.rebuild_term_index:
        count = store.rebuild_term_index()
        print(f"{count} ta video uchun teskari so'z indeksi qayta qurildi.")
        return 0

    if args.find_source_clip:
        return _run_find_source(args.find_source_clip, args.channel_id, args.json)

    if not args.query:
        parser.error("qidiruv so'zi kerak (yoki --rebuild-term-index)")

    data = search_module.search(
        args.query, channel_id=args.channel_id, max_videos=args.max_videos,
        published_after=args.published_after, published_before=args.published_before,
    )
    results = data["results"]

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    if not results:
        if data["blocked"]:
            print("Diqqat: YouTube ba'zi videolarni tekshirishni vaqtincha bloklagan — "
                  "natija to'liqsiz bo'lishi mumkin, birozdan keyin qayta urinib ko'ring.")
        else:
            print("Hech narsa topilmadi.")
        return 0

    for r in results:
        print(f"[{r['channel_name']}] {r['video_title']}")
        print(f"  {r['text']}")
        print(f"  {r['url']}")
        print()
    return 0


def _run_find_source(clip_ref: str, channel_id: str | None, as_json: bool) -> int:
    """``--find-source`` uchun — ``api.py``dagi ``/find-source`` marshruti
    bilan bir xil ikki qadam (avval indeksni yangilash, keyin qidirish),
    lekin FastAPI serverini ishga tushirmasdan, terminaldan to'g'ridan-to'g'ri."""
    try:
        search_module.catch_up(channel_id)
    except Exception:
        pass  # Yangilash qulaylik, majburiy shart emas — api.py'dagi kabi.

    try:
        data = find_source_module.find_source(clip_ref, channel_id=channel_id)
    except (fetch.TranscriptFetchBlocked, fetch.ConfigError, ValueError) as e:
        print(f"Xatolik: {e}", file=sys.stderr)
        return 1

    if as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    if not data["match"]:
        print("Manba topilmadi — indeksda ishonchli moslik yo'q.")
        return 0

    m = data["match"]
    confident_label = "ha" if data["confident"] else "yo'q"
    print(f"[{m['channel_name']}] {m['video_title']} ({m['published_at']})")
    print(f"  {m['url']}")
    print(f"  ball: {m['score']:.2f}, margin: {m['margin']:.2f}, ishonchli: {confident_label}")
    print(f"  mos so'zlar: {', '.join(m['matched_terms'])}")
    if not data["confident"]:
        print("  Diqqat: moslik ishonchli emas — sinchiklab tekshiring.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
