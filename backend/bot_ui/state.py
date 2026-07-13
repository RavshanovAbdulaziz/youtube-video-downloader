import threading
import time
import uuid


class VideoContext:
    """Bitta yuborilgan YouTube havolasi uchun holat: video ma'lumotlari va
    hozirda tanlangan audio trek (til)."""

    __slots__ = (
        "url", "title", "duration", "thumbnail",
        "resolutions", "audio_tracks", "audio_index", "busy", "created_at",
    )

    def __init__(
        self,
        url: str,
        title: str | None,
        duration: float | None,
        thumbnail: str | None,
        resolutions: list[dict],
        audio_tracks: list[dict],
    ) -> None:
        self.url = url
        self.title = title
        self.duration = duration
        self.thumbnail = thumbnail
        self.resolutions = resolutions
        self.audio_tracks = audio_tracks
        self.audio_index = 0
        for i, track in enumerate(audio_tracks):
            if track.get("is_original"):
                self.audio_index = i
                break
        self.busy = False
        self.created_at = time.monotonic()

    @property
    def audio_format_id(self) -> str | None:
        if not self.audio_tracks:
            return None
        return self.audio_tracks[self.audio_index]["format_id"]

    @property
    def audio_label(self) -> str | None:
        if not self.audio_tracks:
            return None
        return self.audio_tracks[self.audio_index].get("label")


class ContextStore:
    """Token -> VideoContext, eskirgan yozuvlar avtomatik tozalanadi (bot
    uzoq vaqt ishlaganda xotira sizib chiqmasligi uchun)."""

    TTL_SECONDS = 2 * 3600

    def __init__(self) -> None:
        self._data: dict[str, VideoContext] = {}
        self._lock = threading.Lock()

    def create(self, **kwargs) -> str:
        self._purge_expired()
        token = uuid.uuid4().hex[:8]
        with self._lock:
            self._data[token] = VideoContext(**kwargs)
        return token

    def get(self, token: str) -> VideoContext | None:
        return self._data.get(token)

    def _purge_expired(self) -> None:
        now = time.monotonic()
        with self._lock:
            expired = [k for k, v in self._data.items() if now - v.created_at > self.TTL_SECONDS]
            for k in expired:
                del self._data[k]
