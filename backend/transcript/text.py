"""Transkript matnini so'zlarga ajratish — ``find_source`` (moslashtirish)
va ``store`` (teskari indeks) uchun UMUMIY.

Ikkalasi bir xil qoidadan foydalanishi SHART: ``store`` qaysi so'zlarni
indeksga yozsa, ``find_source`` aynan o'shalarni qidiradi. Ilgari bu mantiq
faqat ``find_source``da edi va ``store`` xom ``LIKE '%so'z%'`` bilan
qidirardi — natijada "hujjat chastotasi" so'z ichidagi tasodifiy
ustma-tushliklardan ham oshib ketardi.
"""
from __future__ import annotations

import re

_WORD_RE = re.compile(r"[a-z’']+", re.UNICODE)

# Subtitr artefaktlari: "[Music]", "[Applause]", "[musiqa]", "(laughs)" va
# ">>" so'zlovchi belgisi. Bular NUTQ EMAS — deyarli har bir videoda
# uchraydi, ya'ni moslikka hech qanday dalil qo'shmaydi, lekin ballni
# shishiradi (aynan "music" so'zi xato javob bergan edi).
_CAPTION_ARTIFACT_RE = re.compile(r"\[[^\]]*\]|\([^)]*\)|&gt;&gt;|>>")

# Ingliz + o'zbek eng keng tarqalgan so'zlari: bular deyarli har bir
# segmentda uchraydi, shuning uchun moslikni aniqlashda foydasiz (aksincha,
# tasodifiy "shovqin" ball qo'shadi).
STOPWORDS = frozenset("""
a an the and or but if is are was were be been being to of in on at for with that this
these those it its i you he she they we me him her them my your his their our do does
did done have has had not no yes so as by from up out about into over after what why
how when where who whom which there here just got get gonna wanna like bro man oh yo uh
um huh yeah nah ok okay all right well now then can could would should will one two
know think see say said go going come came want need really much many very too
va yoki lekin agar men sen siz biz ular bu shu u bor yoq yo'q ha nima nega qanday
qachon qayerda kim uchun bilan uchun ham emas edi ekan bo'ldi bo'lgan qildi qilgan
men'ga menga senga sizga bizga ularga aka birodar do'stim juda mana ana keyin oldin
""".split())


def terms(text: str) -> list[str]:
    """Matndan ma'noli so'zlar — kichik harf, stop-so'zlarsiz, 3 harfdan
    uzun, subtitr artefaktlarisiz. Tartib va takrorlar saqlanadi (chastota
    ballash uchun kerak)."""
    out = []
    for word in _WORD_RE.findall(_CAPTION_ARTIFACT_RE.sub(" ", text.lower())):
        word = word.strip("'’")
        if len(word) > 2 and word not in STOPWORDS:
            out.append(word)
    return out
