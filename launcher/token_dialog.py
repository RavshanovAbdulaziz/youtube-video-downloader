"""Bir martalik (yoki "Sozlamalar" orqali qayta chaqiriladigan) kichik oyna —
ixtiyoriy Telegram bot tokenini so'raydi. Faqat stdlib (tkinter) ishlatadi —
tray ilovasi uchun qo'shimcha bog'liqlik kerak emas.
"""
import tkinter as tk
from tkinter import simpledialog


def ask_bot_token(current: str | None = None) -> str | None:
    """Foydalanuvchidan bot token so'raydi. Bo'sh qoldirilsa yoki bekor
    qilinsa None qaytaradi (Web UI rejimi — bot ishga tushmaydi)."""
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        result = simpledialog.askstring(
            "YouTube Downloader — Telegram bot (ixtiyoriy)",
            "Telegram bot tokeningizni kiriting (@BotFather'dan olinadi).\n\n"
            "Bo'sh qoldirsangiz, dastur faqat brauzer (Web UI) orqali ishlaydi —\n"
            "buni istalgan payt tray menyusidagi \"Sozlamalar\"dan o'zgartirish mumkin.",
            initialvalue=current or "",
            parent=root,
        )
    finally:
        root.destroy()
    result = (result or "").strip()
    return result or None
