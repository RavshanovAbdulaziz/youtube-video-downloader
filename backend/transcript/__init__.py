"""YouTube video transkriptlari ichidan so'z/ibora qidiruv moduli.

Bitta kanal ichida (`channel_id` berilsa, SQLite'da indexlanib qidiriladi)
yoki butun YouTube bo'yicha (hybrid: `search.list` + real-time transkript
tekshiruv, saqlashsiz) ishlaydi. Asosiy kirish nuqtasi: `transcript.search.search`.
"""
