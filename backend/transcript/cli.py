"""Standalone CLI kirish nuqtasi.

Ishlatish (``backend/`` papkasidan)::

    py -3.14 -m transcript.cli "qidiriladigan ibora" --channel UC... --json
"""
from __future__ import annotations

import argparse
import json
import sys

from . import search as search_module


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="YouTube transkript qidiruv (CLI)")
    parser.add_argument("query", help="Qidiriladigan so'z yoki ibora")
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


if __name__ == "__main__":
    sys.exit(main())
