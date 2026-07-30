from aiogram.filters.callback_data import CallbackData


class MenuVideoCB(CallbackData, prefix="m_v"):
    token: str


class MenuSeparateCB(CallbackData, prefix="m_s"):
    token: str


class MenuBackCB(CallbackData, prefix="m_back"):
    token: str


class PickLanguageCB(CallbackData, prefix="m_lang"):
    token: str


class MenuSubtitleCB(CallbackData, prefix="m_sub"):
    token: str


class DownloadSubtitleCB(CallbackData, prefix="dsub"):
    token: str
    index: int


class SetLanguageCB(CallbackData, prefix="setlang"):
    token: str
    index: int


class DownloadVideoCB(CallbackData, prefix="dv"):
    token: str
    format_id: str


class DownloadAudioCB(CallbackData, prefix="da"):
    token: str


class SeparateCB(CallbackData, prefix="se"):
    token: str
    engine: str
