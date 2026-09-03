"""Global (kanalsiz) qidiruv uchun vaqtinchalik in-memory TTL keshi.

SQLite'ga saqlanmaydi (spetsifikatsiyaga ko'ra global rejim uchun saqlash
shart emas) — faqat bitta process ichida, 24 soatgacha, videoni qayta-qayta
qidirilganda transkriptni takror olib kelmaslik uchun. Process qayta
ishga tushsa (server reload/restart) kesh ham bo'shab ketadi — bu qasddan,
Redis kabi tashqi bog'liqlik qo'shmaslik uchun (spetsifikatsiyada "oddiy
dict bilan ham bo'ladi" deyilgan).
"""
from __future__ import annotations

import threading
import time

DEFAULT_TTL_SECONDS = 24 * 60 * 60


class TTLCache:
    def __init__(self, ttl_seconds: float = DEFAULT_TTL_SECONDS):
        self._ttl = ttl_seconds
        self._store: dict[str, tuple[float, object]] = {}
        self._lock = threading.Lock()

    def get(self, key: str):
        """Muddati o'tmagan qiymatni qaytaradi, aks holda ``None``."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if expires_at < time.time():
                del self._store[key]
                return None
            return value

    def set(self, key: str, value) -> None:
        with self._lock:
            self._store[key] = (time.time() + self._ttl, value)

    def __len__(self) -> int:
        return len(self._store)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


transcript_cache = TTLCache()
